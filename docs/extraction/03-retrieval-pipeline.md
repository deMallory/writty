# 03 — Retrieval Pipeline (full extraction)

Source root: `/home/lucio.saldivar/.claude/skills/writ/writ/retrieval/`

## 1. Module layout

| File | Lines | Role |
|---|---|---|
| `pipeline.py` | 602 | Orchestrator: `RetrievalPipeline.query()` + `build_pipeline()` |
| `keyword.py` | 117 | `KeywordIndex` (Tantivy BM25, Stage 2) |
| `embeddings.py` | 368 | `OnnxEmbeddingModel`, `CachedEncoder`, `HnswlibStore`, `ScoredResult`, `HnswSidecar` (Stage 3) |
| `traversal.py` | 147 | `AdjacencyCache`, `GraphTraverser` (Stage 4) |
| `ranking.py` | 340 | `RankingWeights`, `compute_score`, `normalize_ranks`, `apply_authority_preference`, `filter_proximity_seeds`, `apply_context_budget` (Stage 5) |
| `__init__.py` | 0 | Empty (no re-exports) |

## 2. The five stages, in order

Module docstring (`pipeline.py:1-16`) defines:
```
Stage 1: Domain Filter -- pre-filter to relevant domain subgraph.
Stage 2: BM25 Keyword Filter -- Tantivy sparse retrieval on trigger, statement, tags.
Stage 3: ANN Vector Search -- hnswlib in-process ANN on pre-computed embeddings.
Stage 4: Graph Traversal -- adjacency cache lookup from top-K results.
Stage 5a: First-pass ranking -- RRF + metadata weighting (no graph proximity).
Stage 5b: Graph proximity -- compute proximity scores from top-3 first-pass results.
Stage 5c: Final ranking -- re-score with graph proximity, context budget applied.
```

Mandatory rules excluded **before** Stage 1: skipped at index-build time (`keyword.py:69-70`) and excluded by Cypher (`pipeline.py:471-475`: `WHERE r.mandatory IS NULL OR r.mandatory = false`).

Orchestrator entry point: `RetrievalPipeline.query()` at `pipeline.py:198-409`.

Order of operations inside `query()`:
1. `start = time.perf_counter()` (`pipeline.py:223`).
2. `exclude = set(exclude_rule_ids or []) | set(loaded_rule_ids or [])` (`pipeline.py:224`).
3. Pick `active_weights = RankingWeights.literal()` if `retrieval_mode=="literal"` else `self._weights` (`pipeline.py:226-229`).
4. Resolve `allowed_types` and `methodology_domain_exclude` (`pipeline.py:236-244`):
   - explicit `node_types` → that set, no methodology exclude.
   - `literal` mode → `allowed_types=None`, no methodology exclude.
   - default semantic → `allowed_types={"Rule"}`, `methodology_domain_exclude=True`.
5. Stage 2 BM25: `self._keyword.search(query_text, limit=BM25_CANDIDATE_LIMIT)` (`pipeline.py:251`), then post-filter for exclude / domain / allowed_types / methodology-domain set (`pipeline.py:252-267`). Methodology domain blacklist: `{"process", "communication", "meta-authoring"}`.
6. Stage 3 ANN: `query_vector = self._model.encode(query_text).tolist()`, `self._vector.search(query_vector, k=VECTOR_CANDIDATE_LIMIT)` (`pipeline.py:270-271`), same post-filters (`pipeline.py:272-287`).
7. Merge: union by rule_id, both raw scores stored (`pipeline.py:290-299`).
8. `normalize_ranks` on each list to produce `bm25_norm`/`vector_norm` (`pipeline.py:302-310`).
9. Stage 4: `enrichment = self._cache.get_enrichment(list(candidate_ids.keys()))` (`pipeline.py:313`).
10. Stage 5a: `first_pass_weights = RankingWeights(w_bm25=fp_bm25, w_vector=fp_vec, w_severity=fp_sev, w_confidence=fp_conf, w_graph=0.0, w_bundle_cohesion=0.0)` (`pipeline.py:316-320`); score every candidate with `compute_score` (`pipeline.py:321-333`).
11. `top3_ids = filter_proximity_seeds(first_pass_with_auth, FIRST_PASS_TOP_N)` -- excludes ai-provisional (`pipeline.py:336-340`).
12. Stage 5b: `proximity = compute_graph_proximity(all_candidate_list, top3_ids, self._cache)` (`pipeline.py:343-344`).
13. Stage 5b' bundle cohesion: per candidate, fraction of 1-hop neighbors that are in top-N first-pass set (`pipeline.py:349-357`).
14. Stage 5c: full `compute_score` (with graph + bundle) per candidate, build full result dicts (`pipeline.py:360-384`).
15. Sort desc by score (`pipeline.py:387`).
16. `apply_authority_preference(scored_rules, self._authority_preference_threshold)` (`pipeline.py:390-392`).
17. Sticky tiebreak via `_apply_sticky_tiebreak` if `prefer_rule_ids` (`pipeline.py:397-398`).
18. `trimmed, mode = apply_context_budget(scored_rules, budget_tokens)` (`pipeline.py:401`).
19. Return `{"rules": trimmed, "mode": mode, "total_candidates": len(candidate_ids), "latency_ms": round(elapsed_ms, 3)}` (`pipeline.py:404-409`).

## 3. Stage 1 — Domain / type filter

No dedicated function. Applied as **post-filter** on Stage 2/3 (`pipeline.py:246-248`):
```
# Stage 1: Domain filter.
# Applied as post-filter on BM25/vector results since indexes
# contain all non-mandatory rules.
```
- `domain` compared `.lower()` against `metadata["domain"].lower()` (`pipeline.py:253-257`, `273-277`).
- `allowed_types` whitelist on `metadata["node_type"]` defaulting to `"Rule"` (`pipeline.py:258-262`, `278-282`).
- `methodology_domain_exclude` drops rows where `domain` is in `{"process", "communication", "meta-authoring"}` (`pipeline.py:263-267`, `283-287`).
- `exclude` set applied identically (`pipeline.py:252`, `272`).

## 4. Stage 2 — BM25 (Tantivy)

Class: `KeywordIndex` (`keyword.py:28-117`).

**Schema** (`keyword.py:42-51`):
```
schema_builder.add_text_field("rule_id", stored=True)
schema_builder.add_text_field("trigger", stored=True)
schema_builder.add_text_field("statement", stored=True)
schema_builder.add_text_field("tags", stored=True)
schema_builder.add_text_field("body", stored=True)
```

**On-disk**: constructor takes optional `index_dir` (`keyword.py:35-58`); `pipeline.py:526-527` calls `KeywordIndex()` with no args, so the index is **in-memory** (no path).

**Boosts/dilution** (`keyword.py:60-90`):
- `TRIGGER_BOOST = 2.0` (`keyword.py:19`); applied by string-repetition: `boosted_trigger = " ".join([trigger_text] * int(self._trigger_boost))`.
- `body` 0.5x via every-other-token dilution: `body_halved = " ".join(body_tokens[::2])`.
- Mandatory rules skipped: `if rule.get("mandatory", False): continue`.
- Build flow: `writer = self._index.writer()` → `writer.add_document(...)` per rule → `writer.commit()` → `self._index.reload()`.

**Sanitization** (`keyword.py:22-25`):
```
_TANTIVY_SPECIAL = re.compile(r"""['":\\\/\(\)\[\]\{\}\!\?\~\^\+\-\&\|]""")
_TANTIVY_RESERVED = re.compile(r"\b(AND|OR|NOT|IN|TO)\b")
```
Special chars stripped to spaces; uppercase reserved words lowercased (neutralizes operator semantics).

**Query** (`keyword.py:92-117`):
```
query = self._index.parse_query(sanitized, ["trigger", "statement", "tags", "body"])
results = searcher.search(query, limit).hits
```
Returns `[{"rule_id": ..., "score": ...}]`. On empty input or `ValueError` from `parse_query`: returns `[]` (vector still runs).

`BM25_CANDIDATE_LIMIT = 50` (`pipeline.py:53`).

Auxiliary text folding for methodology nodes: `_fold_auxiliary_text_into_body` (`pipeline.py:419-448`) appends `forbidden_phrases` + `what_to_say_instead` (ForbiddenResponse) or `named_in` (AntiPattern) into `body` so BM25 can match.

## 5. Stage 3 — ANN (hnswlib)

Class: `HnswlibStore` (`embeddings.py:197-368`).

**Constants** (`embeddings.py:25-35`):
```
DEFAULT_EF_CONSTRUCTION = 200
DEFAULT_M = 16
DEFAULT_EF_SEARCH = 50
DEFAULT_HNSW_CACHE_DIR = str(Path.home() / ".cache" / "writ" / "hnsw")
EMBEDDING_CACHE_SIZE = 1024
DEFAULT_ONNX_DIR = Path.home() / ".cache" / "writ" / "models" / "onnx"
```
`VECTOR_CANDIDATE_LIMIT = 10` (`pipeline.py:54`).

**Build** (`embeddings.py:220-236`):
```
self._index = hnswlib.Index(space="cosine", dim=self._dimensions)
self._index.init_index(max_elements=count, ef_construction=self._ef_construction, M=self._m)
self._index.set_ef(self._ef_search)
self._id_to_rule = {i: rid for i, rid in enumerate(rule_ids)}
self._index.add_items(vectors, list(range(count)))
```
Distance: cosine. M=16, ef_construction=200, ef_search=50.

**Search** (`embeddings.py:238-250`):
```
labels, distances = self._index.knn_query([vector], k=actual_k)
...
score = 1.0 - float(distance)   # cosine sim from cosine distance
```
Returns `list[ScoredResult]` where `ScoredResult(BaseModel)` has `rule_id: str, score: float` (`embeddings.py:38-40`).

**Persistence**: files `writ_hnsw.bin` + `writ_hnsw.json` in `cache_dir` (default `~/.cache/writ/hnsw`).

Sidecar Pydantic model (`embeddings.py:43-56`):
```
class HnswSidecar(BaseModel):
    model_config = {"populate_by_name": True}
    corpus_hash: str
    rule_count: int
    dims: int
    ef_construction: int
    M: int
    id_to_rule: dict[str, str] = Field(alias="_id_to_rule")
```

`save_index(corpus_hash)` (`embeddings.py:252-302`): atomic write via `tempfile.mkstemp` + `os.rename` for both sidecar JSON and binary.

`load_index(corpus_hash)` (`embeddings.py:304-368`): validates sidecar via Pydantic, verifies hash match (raises `ValueError`, sets `self._index = None` on mismatch), loads index, calls `idx.set_ef(self._ef_search)`, then `new_max = max(int(rule_count * 1.2), rule_count + 1); idx.resize_index(new_max)` for growth headroom.

**Corpus hash** (`pipeline.py:412-416`):
```
def _compute_corpus_hash(rule_ids, vectors):
    pairs = sorted(zip(rule_ids, [str(v) for v in vectors]))
    digest_input = "|".join(f"{rid}:{vec}" for rid, vec in pairs)
    return hashlib.sha256(digest_input.encode()).hexdigest()
```

`build_pipeline` cache flow (`pipeline.py:567-589`): try `load_index(corpus_hash)`; on any exception, `_logger.debug("HNSW cache miss: %s", exc)`, then `build_index` + `save_index` (warning logged on save failure).

## 6. Embedding model loading

Protocol (`embeddings.py:59-67`):
```
class EmbeddingModel(Protocol):
    def encode(self, text: str) -> np.ndarray: ...
```

### ONNX (preferred) — `OnnxEmbeddingModel` (`embeddings.py:70-142`)

- `MAX_LENGTH = 128`.
- `model_dir` defaults to `DEFAULT_ONNX_DIR = Path.home() / ".cache" / "writ" / "models" / "onnx"`.
- Model name: `DEFAULT_EMBEDDING_MODEL = "all-MiniLM-L6-v2"` (`pipeline.py:55`) — only used by SentenceTransformer fallback.
- Files required: `model.onnx`, `tokenizer.json` (FileNotFoundError if missing).
- Tokenizer: `tokenizers.Tokenizer.from_file(...)` with `enable_truncation(max_length=128)`, `enable_padding(length=128)` (no transformers/PyTorch import).
- Session: `ort.InferenceSession(str(model_path), providers=["CPUExecutionProvider"])`.
- Tokenize produces `input_ids`, `attention_mask`, `token_type_ids` as int64 numpy arrays.
- **Pooling: mean pooling + L2 normalization** (`embeddings.py:114-121`):
  ```
  mask = attention_mask[..., np.newaxis].astype(np.float32)
  pooled = (token_embeddings * mask).sum(axis=1) / mask.sum(axis=1)
  norm = np.linalg.norm(pooled, axis=1, keepdims=True)
  return pooled / np.maximum(norm, 1e-12)
  ```
- `encode_batch(texts, batch_size=64)` — chunks of 64.

### SentenceTransformer fallback (`pipeline.py:559-565`)

Only triggered when ONNX `FileNotFoundError`/`ImportError` AND no `embedding_model` passed:
```
from sentence_transformers import SentenceTransformer
model = SentenceTransformer(model_name)
embeddings = model.encode(texts).tolist()
query_encoder = CachedEncoder(model)
```

### Selection logic (`pipeline.py:533-565`)

Auto-detect path:
```
if embedding_model is None:
    try:
        onnx_model = OnnxEmbeddingModel(_ONNX_DIR)
    except (FileNotFoundError, ImportError):
        pass

if onnx_model is not None:
    embeddings = onnx_model.encode_batch(texts)
    query_encoder = CachedEncoder(onnx_model)
elif embedding_model is not None:
    raw_model = embedding_model
    if isinstance(embedding_model, CachedEncoder):
        raw_model = embedding_model._model
    if isinstance(raw_model, OnnxEmbeddingModel):
        embeddings = raw_model.encode_batch(texts)
    else:
        embeddings = raw_model.encode(texts).tolist()
    query_encoder = (embedding_model if isinstance(embedding_model, CachedEncoder)
                     else CachedEncoder(embedding_model))
else:
    # SentenceTransformer fallback (above)
```

**Eager loading**: model loaded and `encode_batch(texts)` called over the whole corpus inside `build_pipeline`. Query path only calls `self._model.encode(query_text)` — no I/O.

Default dimensionality (`pipeline.py:568`): `dims = len(embeddings[0]) if embeddings else 384`.

### `CachedEncoder` LRU wrapper (`embeddings.py:145-182`)

```
@functools.lru_cache(maxsize=maxsize)   # maxsize=EMBEDDING_CACHE_SIZE=1024
def _cached_encode(text: str) -> np.ndarray:
    result = self._model.encode(text)
    if isinstance(result, np.ndarray):
        return result
    return np.array(result, dtype=np.float32)

def encode(self, text):
    return self._cached_encode(text).copy()   # defensive copy
```

`encode_batch` delegates to underlying model (no cache use). Has `cache_info()` and `cache_clear()` proxies.

## 7. Stage 4 — graph traversal

Class: `AdjacencyCache` (`traversal.py:23-120`).

**Cypher query** (`traversal.py:46-59`):
```
MATCH (a)-[r]->(b)
WITH a, r, b,
     coalesce(a.rule_id, a.skill_id, a.playbook_id, a.technique_id,
              a.antipattern_id, a.forbidden_id, a.phase_id,
              a.rationalization_id, a.scenario_id, a.example_id,
              a.role_id) AS src_id,
     coalesce(b.rule_id, b.skill_id, b.playbook_id, b.technique_id,
              b.antipattern_id, b.forbidden_id, b.phase_id,
              b.rationalization_id, b.scenario_id, b.example_id,
              b.role_id) AS tgt_id
WHERE src_id IS NOT NULL AND tgt_id IS NOT NULL
RETURN src_id AS source, type(r) AS edge_type, tgt_id AS target
```
Matches *any* labeled node; primary id from any of 11 id-fields via `coalesce`. **All edges, all types** — no edge-type filter.

**Build** (`traversal.py:33-82`): each edge stored twice (outgoing + incoming) for undirected lookup:
```
self._neighbors.setdefault(src, []).append({"rule_id": tgt, "edge_type": edge_type, "direction": "outgoing"})
self._neighbors.setdefault(tgt, []).append({"rule_id": src, "edge_type": edge_type, "direction": "incoming"})
```
Returns `len(self._neighbors)`. Tracks `self._build_time_ms`.

**API**:
- `get_neighbors(rule_id)` → `self._neighbors.get(rule_id, [])` (O(1)).
- `get_enrichment(rule_ids)` → `{rid: self.get_neighbors(rid) for rid in rule_ids}`.
- `get_bundle(rule_id, max_depth=2)` — BFS up to `max_depth` hops, returns `set[str]`. Default depth 2 (Playbook→AntiPattern→Skill).

`GraphTraverser` (`traversal.py:123-147`) wraps `db.traverse_neighbors(rule_id, hops=hops)` — live-fetch alternative. **Not used by the pipeline.** Hot path is always `AdjacencyCache`.

### Graph proximity computation (`pipeline.py:59-100`)

```
def compute_graph_proximity(candidate_ids, top3_ids, cache):
    top3_set = set(top3_ids)
    top3_1hop = set()
    top3_2hop = set()
    for tid in top3_ids:
        for neighbor in cache.get_neighbors(tid):
            nid = neighbor["rule_id"]
            if nid not in top3_set:
                top3_1hop.add(nid)
    for nid in top3_1hop:
        for neighbor in cache.get_neighbors(nid):
            n2id = neighbor["rule_id"]
            if n2id not in top3_set and n2id not in top3_1hop:
                top3_2hop.add(n2id)
    proximity = {}
    for rid in candidate_ids:
        if rid in top3_set:
            proximity[rid] = 0.0
        elif rid in top3_1hop:
            proximity[rid] = 1.0
        elif rid in top3_2hop:
            proximity[rid] = 0.5
        else:
            proximity[rid] = 0.0
    return proximity
```
Discrete output `{0.0, 0.5, 1.0}`. Top-3 themselves get 0.0 (INV-4 no self-boost). Max wins.

### Bundle cohesion (`pipeline.py:349-357`)

```
top_n_set = set(rid for rid, _ in first_pass_scores[:FIRST_PASS_TOP_N])
for rid in all_candidate_list:
    neighbors = self._cache.get_neighbors(rid)
    if not neighbors:
        bundle_cohesion[rid] = 0.0
        continue
    overlap = sum(1 for n in neighbors if n["rule_id"] in top_n_set)
    bundle_cohesion[rid] = overlap / len(neighbors)
```

## 8. Stage 5 — ranking

### Default weights (`ranking.py:18-42`)

```
DEFAULT_W_BM25 = 0.198
DEFAULT_W_VECTOR = 0.594
DEFAULT_W_SEVERITY = 0.099
DEFAULT_W_CONFIDENCE = 0.099
DEFAULT_W_GRAPH = 0.01
DEFAULT_W_BUNDLE_COHESION = 0.0

LITERAL_W_BM25 = 0.396
LITERAL_W_VECTOR = 0.396
LITERAL_W_SEVERITY = 0.099
LITERAL_W_CONFIDENCE = 0.099
LITERAL_W_GRAPH = 0.01
```
Sum: 0.198+0.594+0.099+0.099+0.01+0.0 = 1.000.

### Severity / confidence (`ranking.py:50-62`)

```
SEVERITY_WEIGHTS = {"critical": 1.0, "high": 0.75, "medium": 0.5, "low": 0.25}
CONFIDENCE_WEIGHTS = {"battle-tested": 1.0, "production-validated": 0.8,
                      "peer-reviewed": 0.6, "speculative": 0.3}
```
Defaults on miss: severity 0.5, confidence 0.8 (`ranking.py:155-156`).

### `RankingWeights` (`ranking.py:65-112`)

Dataclass. `validate()` raises `ValueError(f"Weights must sum to 1.0, got {total}")` if `abs(total-1.0) > 0.001`. NOT called from `query()`.

`first_pass_weights()` renormalizes w_bm25..w_confidence to sum 1.0 (drops graph + bundle for Stage 5a, INV-4):
```
total = self.w_bm25 + self.w_vector + self.w_severity + self.w_confidence
if total < 0.001:
    return (0.25, 0.25, 0.25, 0.25)
return (self.w_bm25 / total, self.w_vector / total, self.w_severity / total, self.w_confidence / total)
```

### Scoring formula (`ranking.py:136-165`)

```
def compute_score(bm25_norm, vector_norm, severity, confidence,
                  graph_proximity=0.0, bundle_cohesion=0.0, weights=None):
    if weights is None:
        weights = RankingWeights()
    sev_w = SEVERITY_WEIGHTS.get(severity, 0.5)
    conf_w = CONFIDENCE_WEIGHTS.get(confidence, 0.8)
    return (
        weights.w_bm25 * bm25_norm
        + weights.w_vector * vector_norm
        + weights.w_severity * sev_w
        + weights.w_confidence * conf_w
        + weights.w_graph * graph_proximity
        + weights.w_bundle_cohesion * bundle_cohesion
    )
```

### Reciprocal rank normalization (`ranking.py:168-180`)

```
def normalize_ranks(scores):
    if not scores:
        return []
    indexed = sorted(enumerate(scores), key=lambda x: x[1], reverse=True)
    normalized = [0.0] * len(scores)
    for rank, (orig_idx, _score) in enumerate(indexed):
        normalized[orig_idx] = 1.0 / (rank + 1)
    return normalized
```

**Note**: this is plain reciprocal rank `1/(rank+1)`, **not classical RRF** `1/(k+rank)`. There is no `k` constant. Module docstrings call it RRF but the formula is reciprocal rank + weighted linear fusion.

### Authority preference (`ranking.py:183-212`)

```
def apply_authority_preference(scored_rules, threshold):
    if threshold <= 0.0:
        return scored_rules
    result = list(scored_rules)
    changed = True
    while changed:
        changed = False
        for i in range(len(result) - 1):
            upper = result[i]; lower = result[i+1]
            gap = upper.get("score", 0.0) - lower.get("score", 0.0)
            if gap > threshold:
                continue
            upper_auth = upper.get("authority", "human")
            lower_auth = lower.get("authority", "human")
            if upper_auth == "ai-provisional" and lower_auth != "ai-provisional":
                result[i], result[i+1] = result[i+1], result[i]
                changed = True
    return result
```
Default threshold in pipeline ctor: `authority_preference_threshold: float = 0.0` (`pipeline.py:188`) → no-op by default.

### Proximity seed filter (`ranking.py:215-230`)

```
def filter_proximity_seeds(first_pass_scores, top_n=3):
    seeds = []
    for rid, _score, authority in first_pass_scores:
        if authority != "ai-provisional":
            seeds.append(rid)
            if len(seeds) >= top_n:
                break
    return seeds
```
`FIRST_PASS_TOP_N = 3` (`pipeline.py:56`). No backfill with ai-provisional.

### Confidence graduation (`ranking.py:115-133`) — not used by pipeline

```
def compute_confidence_weight(static_confidence, times_positive, times_negative,
                              threshold=50, ratio_min=0.75):
    from writ.frequency import evaluate_graduation
    grad = evaluate_graduation(times_positive, times_negative, threshold, ratio_min)
    if grad.graduated:
        return grad.ratio
    return CONFIDENCE_WEIGHTS.get(static_confidence, 0.8)
```
Not invoked from `RetrievalPipeline.query()`.

### Sticky tiebreak (`pipeline.py:103-171`)

```
STICKY_TIEBREAK_THRESHOLD = 0.02
_TIEBREAK_EPSILON = 1e-9
```

`_apply_sticky_tiebreak(scored_rules, prefer_rule_ids)`: builds groups of consecutive rules where adjacent score gap `<= 0.02 + 1e-9`; within each group, preferred rules (in `prefer_rule_ids`) are ordered by their position in `prefer_rule_ids`, non-preferred keep original relative order. Rules not in result set are never promoted in. Stabilizes injection order across turns for prompt-cache friendliness.

## 9. Context budget (`ranking.py:233-340`)

Constants (`ranking.py:44-48`):
```
SUMMARY_THRESHOLD = 2000
STANDARD_THRESHOLD = 8000
SUMMARY_LIMIT = 10
STANDARD_LIMIT = 5
FULL_LIMIT = 10
```

`apply_context_budget(rules, budget_tokens, abstractions=None)`:
- `budget_tokens is None` → `budget_tokens = STANDARD_THRESHOLD + 1` (defaults to "full").
- `budget_tokens < 2000` → `mode="summary"`, top-10, fields `rule_id, node_type, score, statement, trigger`. If `abstractions` provided, returns abstraction summaries via `_summary_with_abstractions`.
- `2000 <= budget_tokens <= 8000` → `mode="standard"`, top-5, adds `violation, pass_example`.
- `budget_tokens > 8000` → `mode="full"`, top-10, adds `rationale, relationships`.

**No token estimation** — `budget_tokens` is just an integer compared to thresholds. The pipeline does not measure rendered length.

`_summary_with_abstractions` (`ranking.py:300-340`): builds `rid_to_abs` map; for each top rule, replaces with parent abstraction (deduped by `abstraction_id`); ungrouped rules fall back to statement+trigger. **Pipeline does not pass `abstractions=`** (see `pipeline.py:401: apply_context_budget(scored_rules, budget_tokens)`), so this code path is currently inert.

**`exclude_rule_ids` / `loaded_rule_ids` handling**: merged into one set (`pipeline.py:224`), applied as candidate-level filter on BM25 + vector results (`pipeline.py:252`, `272`). Treated identically.

**Mandatory-vs-retrieved split**: there is **no per-query mandatory branch**. Mandatory rules are filtered structurally at index-build time (`keyword.py:69-70`, `pipeline.py:471-475`, methodology nodes forced `node["mandatory"] = False` at `pipeline.py:509`) and never enter retrieval. Mandatory ENF-* injection happens elsewhere, outside this module.

## 10. Public entry points

**`RetrievalPipeline.query()`** is the only public query method (`pipeline.py:198-208`):
```
def query(
    self,
    query_text: str,
    domain: str | None = None,
    budget_tokens: int | None = None,
    exclude_rule_ids: list[str] | None = None,
    loaded_rule_ids: list[str] | None = None,
    prefer_rule_ids: list[str] | None = None,
    retrieval_mode: str = "semantic",
    node_types: list[str] | None = None,
) -> dict:
```

Return: `{"rules": list[dict], "mode": "summary"|"standard"|"full", "total_candidates": int, "latency_ms": float}`.

**There is no `retrieve()` and no `search()` method** on `RetrievalPipeline`. (`KeywordIndex.search` and `HnswlibStore.search` are stage-internal.)

Builder: `async def build_pipeline(db, model_name="all-MiniLM-L6-v2", weights=None, embedding_model=None) -> RetrievalPipeline` (`pipeline.py:451-602`).

Constructor (`pipeline.py:180-196`) takes injected: `keyword_index, vector_store, adjacency_cache, embedding_model, rule_metadata, weights=None, authority_preference_threshold=0.0`.

`__init__.py` is empty (0 bytes) — no re-exports; callers import from submodules.

## 11. Caches / locks / singletons

| Cache | Class | Where | Notes |
|---|---|---|---|
| Adjacency | `AdjacencyCache._neighbors: dict[str, list[dict]]` | `traversal.py:30` | Built once at startup, no locks |
| Embedding LRU | `CachedEncoder._cached_encode` (`functools.lru_cache(maxsize=1024)`) | `embeddings.py:157` | `.copy()` on hit prevents mutation |
| HNSW disk cache | `HnswlibStore` save/load | `embeddings.py:252-368` | `~/.cache/writ/hnsw/{writ_hnsw.bin, writ_hnsw.json}`; SHA-256 corpus hash invalidation |
| Tantivy | `KeywordIndex._index` | `keyword.py:56-58` | In-memory by default |

No `threading.Lock`, no `asyncio.Lock`, no module-level singletons. Build-once / read-only semantics. Only sync points: `writer.commit()` + `index.reload()` at build time.

## 12. Error handling and fallbacks

| Site | Failure | Behavior |
|---|---|---|
| `KeywordIndex.search` | empty after sanitize | return `[]` (`keyword.py:100-101`) |
| `KeywordIndex.search` | `parse_query` `ValueError` | return `[]`; vector still runs (`keyword.py:104-108`) |
| `HnswlibStore.search` | index empty/None | return `[]` (`embeddings.py:240-241`) |
| `HnswlibStore.save_index` | tempfile write fails | unlink temp, re-raise (`embeddings.py:283-302`) |
| `HnswlibStore.load_index` | sidecar missing | `FileNotFoundError` w/ cache_dir context |
| `HnswlibStore.load_index` | JSON corrupt | `ValueError` |
| `HnswlibStore.load_index` | Pydantic schema invalid | `ValueError` |
| `HnswlibStore.load_index` | hash mismatch | `self._index = None`, `ValueError` |
| `HnswlibStore.load_index` | bin missing | `self._index = None`, `FileNotFoundError` |
| `build_pipeline` | ONNX load `FileNotFoundError`/`ImportError` | fall through to caller-supplied or SentenceTransformer fallback (`pipeline.py:537-539`) |
| `build_pipeline` | `vector_store.load_index` raises | `_logger.debug("HNSW cache miss: %s", exc)`, then build + save (`pipeline.py:580-589`) |
| `build_pipeline` | `vector_store.save_index` raises | `_logger.warning(...)`, continue |
| `_fold_auxiliary_text_into_body` | JSON parse of `forbidden_phrases` fails | `phrases = [phrases]` |
| `RankingWeights.first_pass_weights` | sum < 0.001 | return `(0.25, 0.25, 0.25, 0.25)` |
| `RankingWeights.validate` | sum off by > 0.001 | `ValueError` (NOT called from `query()`) |
| `apply_authority_preference` | threshold <= 0.0 | passthrough |
| `compute_score` | severity/confidence missing | defaults 0.5 / 0.8 |

## 13. All constants in one place

```
# pipeline.py
BM25_CANDIDATE_LIMIT = 50          (L53)
VECTOR_CANDIDATE_LIMIT = 10        (L54)
DEFAULT_EMBEDDING_MODEL = "all-MiniLM-L6-v2"  (L55)
FIRST_PASS_TOP_N = 3               (L56)
STICKY_TIEBREAK_THRESHOLD = 0.02   (L103)
_TIEBREAK_EPSILON = 1e-9           (L107)

# keyword.py
TRIGGER_BOOST = 2.0                (L19)

# embeddings.py
DEFAULT_EF_CONSTRUCTION = 200      (L25)
DEFAULT_M = 16                     (L26)
DEFAULT_EF_SEARCH = 50             (L27)
DEFAULT_HNSW_CACHE_DIR = ~/.cache/writ/hnsw    (L29)
EMBEDDING_CACHE_SIZE = 1024        (L32)
DEFAULT_ONNX_DIR = ~/.cache/writ/models/onnx   (L35)
OnnxEmbeddingModel.MAX_LENGTH = 128            (L78)
OnnxEmbeddingModel.encode_batch batch_size = 64 (L130)

# ranking.py
DEFAULT_W_BM25 = 0.198             (L22)
DEFAULT_W_VECTOR = 0.594           (L23)
DEFAULT_W_SEVERITY = 0.099         (L24)
DEFAULT_W_CONFIDENCE = 0.099       (L25)
DEFAULT_W_GRAPH = 0.01             (L26)
LITERAL_W_BM25 = 0.396             (L33)
LITERAL_W_VECTOR = 0.396           (L34)
LITERAL_W_SEVERITY = 0.099         (L35)
LITERAL_W_CONFIDENCE = 0.099       (L36)
LITERAL_W_GRAPH = 0.01             (L37)
DEFAULT_W_BUNDLE_COHESION = 0.0    (L42)
SUMMARY_THRESHOLD = 2000           (L44)
STANDARD_THRESHOLD = 8000          (L45)
SUMMARY_LIMIT = 10                 (L46)
STANDARD_LIMIT = 5                 (L47)
FULL_LIMIT = 10                    (L48)
SEVERITY_WEIGHTS: critical=1.0, high=0.75, medium=0.5, low=0.25
CONFIDENCE_WEIGHTS: battle-tested=1.0, production-validated=0.8,
                    peer-reviewed=0.6, speculative=0.3
compute_confidence_weight defaults: threshold=50, ratio_min=0.75 (NOT used in query path)
```

## 14. Notable non-implementations / caveats

- **No standard RRF `k` constant.** `normalize_ranks` is `1/(rank+1)`, with weighted linear fusion in `compute_score`. Docstrings say "RRF" but the formula is reciprocal-rank + weighted sum.
- **No recency weighting** anywhere.
- **`compute_confidence_weight` (graduation) not wired into `query()`.** Static enum table only.
- **Authority preference disabled by default** (threshold = 0.0).
- **`DEFAULT_W_BUNDLE_COHESION = 0.0`** — bundle cohesion computed but contributes zero unless caller passes non-default `RankingWeights`.
- **`abstractions` parameter unused** — `apply_context_budget` called without third argument (`pipeline.py:401`); Phase 8 abstraction-summary path inert.
- **No token counting.** `budget_tokens` is a raw integer.

## Files Read

| Path | Lines |
|---|---|
| `writ/retrieval/pipeline.py` | 602 |
| `writ/retrieval/keyword.py` | 117 |
| `writ/retrieval/embeddings.py` | 368 |
| `writ/retrieval/traversal.py` | 147 |
| `writ/retrieval/ranking.py` | 340 |
| `writ/retrieval/__init__.py` | 0 (empty) |

Total: 1574 lines.

## Cross-References Noted

Modules imported but not read:
- `writ.config.get_hnsw_cache_dir` — `pipeline.py:25`. Returns disk path for HNSW cache.
- `writ.graph.db.Neo4jConnection` — `pipeline.py:47` (TYPE_CHECKING). Async Neo4j wrapper; uses `db._driver.session(database=db._database)` at `pipeline.py:477, 495`, `traversal.py:60`.
- `writ.graph.db.GraphConnection` — `traversal.py:20` (TYPE_CHECKING).
- `db.traverse_neighbors(rule_id, hops=hops)` — `traversal.py:134, 146`.
- `writ.frequency.evaluate_graduation` — `ranking.py:128`.
- Third-party: `tantivy`, `hnswlib`, `onnxruntime` (lazy), `tokenizers.Tokenizer` (lazy), `sentence_transformers.SentenceTransformer` (lazy fallback), `pydantic`.

Configuration / external referenced in comments:
- `writ.toml` — `ranking.py:5` ("Weights are configurable via writ.toml").
- `ground_truth_proc.json` — `ranking.py:31-32`. Validation corpus for literal-mode tuning.
- "Phase 0 MethodologyIndex" — `pipeline.py:419-422`, `keyword.py:47-49`.
- Rule-IDs referenced but defined in the Writ corpus, not source: `INV-2`, `INV-4`, `ARCH-CONST-001`, `ARCH-DI-001`, `ARCH-TYPE-001`, `ARCH-ERR-001`, `PERF-IO-001`, `PERF-LAZY-001`, `PY-PROTO-001`, `PY-PYDANTIC-001`, `PY-ASYNC-001`.
