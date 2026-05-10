# 10 — Compression and Abstractions

## Public API: `writ.compression`

`writ/compression/__init__.py` is **empty** (0 lines). Public surface is reached by importing modules directly. There is no `__all__` re-export.

Effective public functions/classes:

From `writ.compression.clusters`:
- `ClusterResult` (dataclass)
- `ComparisonResult` (dataclass)
- `cluster_hdbscan(rule_ids, embeddings) -> ClusterResult`
- `cluster_kmeans(rule_ids, embeddings, k=None) -> ClusterResult`
- `evaluate_both(rule_ids, embeddings) -> ComparisonResult`
- `_build_result`, `_find_centroid_nearest` (internal helpers)

From `writ.compression.abstractions`:
- `generate_abstractions(cluster_result, rules) -> list[dict]`
- `write_abstractions_to_graph(db, abstractions) -> int` (async)
- `_derive_domain`, `_compute_compression_ratio` (internal helpers)

## Clustering implementation (`clusters.py`)

### Constants

```
HDBSCAN_MIN_CLUSTER_SIZE = 2
HDBSCAN_MIN_SAMPLES = 1
KMEANS_DEFAULT_K = 8
KMEANS_MAX_K = 15
KMEANS_RANDOM_STATE = 42
```

### `ClusterResult` dataclass fields
- `clusters: dict[int, list[str]]` — cluster_id -> rule_ids
- `ungrouped: list[str]` — unassigned (noise / singleton)
- `centroid_indices: dict[int, int]` — cluster_id -> index in original `rule_ids` list of the centroid-nearest rule
- `algorithm: str` — `"hdbscan"` or `"kmeans"`
- `silhouette: float` — silhouette score, `-1.0` if not computable

### `ComparisonResult` dataclass fields
- `hdbscan: ClusterResult`
- `kmeans: ClusterResult`
- `chosen: str` — `"hdbscan"` or `"kmeans"`
- `reason: str`

### HDBSCAN config

```python
HDBSCAN(
    min_cluster_size=HDBSCAN_MIN_CLUSTER_SIZE,  # 2
    min_samples=HDBSCAN_MIN_SAMPLES,            # 1
    metric="euclidean",
)
```

Guard: if `len(rule_ids) < HDBSCAN_MIN_CLUSTER_SIZE` (i.e. < 2), returns empty ClusterResult with silhouette `-1.0`. HDBSCAN auto-discovers cluster count; label `-1` indicates noise.

Per the module docstring: HDBSCAN preferred because it auto-discovers cluster count, but is `O(n^2)` worst case (PERF-BIGO-001). Bounded by domain rule count (~45).

### k-means config

```python
KMeans(n_clusters=k, random_state=42, n_init=10)
```

k selection logic:
```python
max_k = min(KMEANS_MAX_K, len(rule_ids) - 1)   # cap at 15 or n-1
if k is None:
    k = min(KMEANS_DEFAULT_K, max_k)            # default 8 or max_k
k = max(2, min(k, max_k))                       # clamp to [2, max_k]
```

Guard: if `len(rule_ids) < 2`, returns empty ClusterResult.

### Singleton handling (`_build_result`)

After labels assigned:
1. Label `-1` -> `ungrouped`.
2. Singleton clusters (size < 2) are removed and their members moved to `ungrouped` (invariant `INV-SINGLETON`).
3. `ungrouped` is sorted before return.

### Centroid-nearest computation (`_find_centroid_nearest`)

For each cluster:
1. Compute mean of member embeddings (`centroid = member_embeds.mean(axis=0)`).
2. Compute Euclidean distances `np.linalg.norm(member_embeds - centroid, axis=1)`.
3. Pick `argmin` -> store the cluster member's index in the original `rule_ids` list.

**Comment-vs-code discrepancy (cosmetic, no behavioral impact)**: the inline comment at `clusters.py:193` says "Find member closest to centroid via cosine distance", but the formula on line 194 is the L2 / Euclidean norm. Because `OnnxEmbeddingModel.encode` produces L2-normalized vectors (`embeddings.py:114-121`, mean-pool + L2 normalize), Euclidean distance and cosine distance on unit vectors are monotonically related: `||a − b||² = 2·(1 − a·b) = 2·cosine_distance`. Therefore `argmin(Euclidean) == argmin(cosine_distance)` exactly, and the centroid-nearest selection produces the same rule whichever metric is named. The comment is imprecise but the behavior matches its intent. Fix the comment to say "Euclidean (equivalent to cosine on L2-normalized vectors)" if the discrepancy needs to be eliminated.

### Silhouette evaluation

Computed only when `len(clusters) >= 2`:
```python
sil_labels, sil_embeddings = ...   # only members of non-singleton clusters
if len(set(sil_labels)) >= 2:
    sil = float(silhouette_score(sil_embeddings, sil_labels))
```
If fewer than 2 clusters survive (or fewer than 2 distinct labels), `silhouette = -1.0`.

### `evaluate_both` selection logic

```python
if not hdbscan_result.clusters:
    chosen, reason = "kmeans", "HDBSCAN produced no clusters (all noise)"
elif hdbscan_result.silhouette >= kmeans_result.silhouette:
    chosen = "hdbscan"
    reason = f"HDBSCAN silhouette {h:.3f} >= k-means {k:.3f}"
else:
    chosen = "kmeans"
    reason = f"k-means silhouette {k:.3f} > HDBSCAN {h:.3f}"
```

There is no fixed silhouette threshold; selection is purely relative (HDBSCAN wins ties via `>=`). Fallback to k-means only when HDBSCAN produces no clusters.

## Abstraction generation (`abstractions.py`)

### Constants

```
ABSTRACTION_ID_PREFIX = "ABS"
APPROX_TOKENS_PER_CHAR = 0.25   # conservative English-text estimate
```

### `generate_abstractions(cluster_result, rules)` algorithm

Inputs: `cluster_result: ClusterResult`, `rules: list[dict]` with `rule_id, statement, trigger, domain`.

Steps:
1. Build `rid_to_rule` map and `rule_ids_list` (preserves index alignment used by `centroid_indices`).
2. Iterate clusters in **sorted order by cluster_id** (deterministic output).
3. For each cluster `cid` with member `member_ids`:
   - Look up `centroid_idx = cluster_result.centroid_indices.get(cid)`.
   - Skip if `centroid_idx is None` or out of range.
   - `centroid_rule_id = rule_ids_list[centroid_idx]`.
   - `summary = centroid_rule.get("statement", "")` — **INV-SUMMARY**: summary is verbatim the statement of the rule nearest to the centroid (no LLM call, deterministic, offline).
4. Derive `domain` via `_derive_domain` — most common domain among member rules (`Counter.most_common`); defaults to `"Unknown"`.
5. Compute `compression_ratio` via `_compute_compression_ratio`.
6. Build `abstraction_id = f"ABS-{domain.upper().replace(' ', '-')}-{cid:03d}"` (e.g. `ABS-PYTHON-001`).
7. Append dict:
```python
{
    "abstraction_id": abs_id,
    "summary": summary,
    "rule_ids": sorted(member_ids),
    "domain": domain,
    "compression_ratio": round(compression_ratio, 2),
}
```

These dicts are not Pydantic models; the file uses plain dicts. The `Abstraction` Pydantic model exists in `schema.py` but is not used by this generator.

### Compression ratio formula

```python
member_tokens = sum(
    len(f"{rule['statement']} {rule['trigger']}") * APPROX_TOKENS_PER_CHAR
    for rule in member_rules
)
summary_tokens = max(len(summary) * APPROX_TOKENS_PER_CHAR, 1)
compression_ratio = member_tokens / summary_tokens
```
Numerator sums `(statement + " " + trigger)` text length across all cluster members; denominator is centroid summary length. Result rounded to 2 decimals. The `max(..., 1)` guard prevents divide-by-zero.

### `write_abstractions_to_graph(db, abstractions)` (async)

1. `await db.delete_abstractions()` — wipe existing abstractions for clean recompression (invariant `INV-IDEMPOTENT`).
2. For each abstraction dict, build node payload:
```python
node_data = {
    "abstraction_id": ...,
    "summary": ...,
    "domain": ...,
    "compression_ratio": ...,
    "rule_count": len(rule_ids),
}
await db.create_abstraction(node_data)
```
3. For each member `rid`: `await db.create_abstracts_edge(abstraction_id, rid)`.
4. Returns `len(abstractions)`.

The actual Cypher strings live in `writ.graph.db.Neo4jConnection`; this module only orchestrates them.

## `summary` mode integration

The retrieval-pipeline `summary` mode uses `_summary_with_abstractions` in `writ/retrieval/ranking.py` (see doc 03). The function swaps low-ranked rules for their parent Abstraction summaries when budget < 2000 tokens. **Pipeline does not currently pass `abstractions=` to `apply_context_budget`** (`pipeline.py:401`), so this code path is currently inert.

## `writ/shared/budget.json` (verbatim)

```json
{
  "default_budget": 8000,
  "rule_cost_full": 200,
  "rule_cost_standard": 120,
  "rule_cost_summary": 40,
  "subagent_budget": null,
  "always_on_cap": 5000
}
```

`writ/shared/__init__.py` is empty (0 lines). The JSON is the canonical SSOT loaded by both `writ/retrieval/session.py` (server / client tracker) and `bin/lib/writ-session.py` (hooks) per ARCH-DRY-001.

## Files Read

- `writ/compression/clusters.py` — 199 lines
- `writ/compression/abstractions.py` — 108 lines
- `writ/compression/__init__.py` — 0 lines (empty)
- `writ/shared/__init__.py` — 0 lines (empty)
- `writ/shared/budget.json` — 8 lines

## Cross-References Noted

- `_summary_with_abstractions` lives in `writ/retrieval/ranking.py` — see doc 03.
- Abstraction node + `ABSTRACTS` edge schema is owned by `writ/graph/db.py` `Neo4jConnection` — see doc 02.
- `budget.json` is consumed by both `writ/retrieval/session.py` and `bin/lib/writ-session.py` — see doc 12.
- `INV-SUMMARY` (centroid statement) and `INV-SINGLETON` (singletons go to ungrouped) are referenced inline.
