# 11 — Evolution and Authority (full extraction)

## A. Authority Model

### The three values
Defined in `writ/graph/schema.py:24`:
```python
VALID_AUTHORITIES = ("human", "ai-provisional", "ai-promoted")
```

`Rule.authority` defaults to `"human"` (`schema.py:112`). Validated via `validate_authority` field validator (`schema.py:165-172`). Same constant reused for methodology nodes via `_MethodologyNodeBase._validate_authority` (`schema.py:324-329`).

### Where each authority is assigned

| Authority | Assigned where | Mechanism |
|---|---|---|
| `human` | Default for `Rule` and `_MethodologyNodeBase` | Pydantic field default (`schema.py:112`, `schema.py:290`) |
| `ai-provisional` | `propose_rule` (`gate.py:240`) | Hard-overwrites `candidate["authority"] = "ai-provisional"` before gate check; cannot be bypassed by caller |
| `ai-promoted` | `cli.py:989` (`writ review --promote`) | Calls `db.update_rule_authority(rule_id, "ai-promoted")` after operator confirmation |

### Promotion ladder
1. AI calls `writ propose ...` → `propose_rule()` forces `authority="ai-provisional"`, `confidence="speculative"` (`gate.py:240-241`).
2. Rule passes structural gate → ingested into Neo4j (`gate.py:244-260`).
3. Origin context written to SQLite (`gate.py:262-274`).
4. Human runs `writ review <rule_id> --promote` → `update_rule_authority(rule_id, "ai-promoted")` + `update_rule_confidence(rule_id, "peer-reviewed")` (`cli.py:989-990`). Requires `typer.confirm` (`cli.py:985`).
5. Frequency-driven graduation: `compute_confidence_weight` substitutes the empirical `ratio` for the static `CONFIDENCE_WEIGHTS` lookup once `n >= threshold` and `ratio >= ratio_min` (`ranking.py:128-133`). This is a *runtime weight override*, not a stored authority change.

### Demotion paths
1. **Reject (full delete):** `writ review <rule_id> --reject` calls `db.delete_rule(rule_id)` (`cli.py:1002`). Only allowed when `authority == "ai-provisional"`. `delete_rule` issues `MATCH (r:Rule {rule_id}) DETACH DELETE r`.
2. **Downweight:** `writ review <rule_id> --downweight` calls `db.update_rule_confidence(rule_id, "speculative")` (`cli.py:1011`). Authority is *not* changed. Available for any rule.
3. **Frequency flag:** `evaluate_graduation` returns `flagged=True` when `n >= threshold` but `ratio < ratio_min` (`frequency.py:53`). This is a signal for human review, not a state change.

### API surface (`Neo4jConnection` methods, `db.py`)
- `get_rules_by_authority(authority: str) -> list[dict]` — `db.py:354-364`.
- `update_rule_authority(rule_id: str, authority: str) -> bool` — `db.py:366-376`.
- `update_rule_confidence(rule_id: str, confidence: str) -> bool` — `db.py:378-388`.
- `count_by_authority() -> dict[str, int]` — `db.py:428-437`.
- `delete_rule(rule_id: str) -> bool` — `db.py:416-426`.
- `increment_positive(rule_id) -> bool` / `increment_negative(rule_id) -> bool` — `db.py:390-414`.

## B. Structural Gate (`writ/gate.py`)

### Constants (`gate.py:22-42`)
```python
NOVELTY_THRESHOLD = 0.85
REDUNDANCY_THRESHOLD = 0.95

VAGUE_DISQUALIFIERS = (
    r"\bconsider\b",
    r"\bbe aware\b",
    r"\bwhere appropriate\b",
    r"\bwhen possible\b",
    r"\bif necessary\b",
    r"\bas needed\b",
    r"\btry to\b",
    r"\bshould generally\b",
    r"\bmay want to\b",
    r"\bkeep in mind\b",
)
_VAGUE_PATTERNS = [re.compile(p, re.IGNORECASE) for p in VAGUE_DISQUALIFIERS]
```

### `GateResult` dataclass (`gate.py:45-51`)
```python
@dataclass
class GateResult:
    accepted: bool
    reasons: list[str] = field(default_factory=list)
    similar_rules: list[str] = field(default_factory=list)
```

### `structural_gate` — five named checks plus a sub-check 1b

Signature (`gate.py:54-60`):
```python
def structural_gate(
    candidate: dict,
    pipeline: RetrievalPipeline,
    *,
    novelty_threshold: float = NOVELTY_THRESHOLD,
    redundancy_threshold: float = REDUNDANCY_THRESHOLD,
) -> GateResult:
```

**1. Schema validation** (`_check_schema`, `gate.py:109-116`)
- Strips underscore-prefixed keys, instantiates `Rule(**clean)`.
- Rejection format: `f"Schema validation failed: {e}"`.

**1b. Mechanical enforcement path** (`_check_mechanical_enforcement`, `gate.py:119-141`)
- Only runs when `candidate.get("mandatory", False)` is True.
- Rejects if `mechanical_enforcement_path` is None or whitespace.
- Literal rejection text:
  ```
  Mechanical-enforcement policy (plan Section 2.1): rule '<rid>' is mandatory but has no mechanical_enforcement_path. Either name a hook + matcher + deny condition, or demote to mandatory=false (advisory).
  ```

**2. Specificity** (`_check_specificity`, `gate.py:144-158`)
- Concatenates `trigger + " " + statement`.
- Searches for any `_VAGUE_PATTERNS` match (case-insensitive).
- Rejection format: `f"Specificity: vague language detected: {', '.join(found)}"`.

**3 & 4. Redundancy + Novelty** (`_check_similarity`, `gate.py:161-193`)
- Encodes `trigger + " " + statement` via `pipeline._model.encode(...)`.
- Calls `pipeline._vector.search(query_vector, k=10)`.
- Excludes self by `rule_id`.
- For each result `r`:
  - If `r.score >= redundancy_threshold` (default 0.95): `f"Redundancy: cosine {r.score:.4f} with {r.rule_id} (threshold: {redundancy_threshold})"`
  - Elif `r.score >= novelty_threshold` (default 0.85): `f"Novelty: cosine {r.score:.4f} with {r.rule_id} (threshold: {novelty_threshold})"`
- Both branches append the offending `rule_id` to `similar_rules`.

**5. Conflict** (`_check_conflicts`, `gate.py:196-221`)
- Skips if `rule_id` not in `pipeline._metadata` (new candidates with no existing graph presence pass automatically).
- Otherwise looks at `pipeline._cache.get_neighbors(candidate_id)` and flags any `edge_type == "CONFLICTS_WITH"`.
- Rejection format: `f"Conflict: CONFLICTS_WITH edge to {n['rule_id']}"`.

### `propose_rule` orchestrator (`gate.py:224-282`)
```python
async def propose_rule(
    candidate: dict,
    pipeline: RetrievalPipeline,
    db: object,
    *,
    origin_db_path: object | None = None,
    task_description: str = "",
    query_that_triggered: str | None = None,
    novelty_threshold: float = NOVELTY_THRESHOLD,
    redundancy_threshold: float = REDUNDANCY_THRESHOLD,
) -> dict:
```

Order of operations:
1. **Force-set** `candidate["authority"] = "ai-provisional"` and `candidate["confidence"] = "speculative"` (`gate.py:240-241`). Cannot be overridden by caller.
2. Run `structural_gate(...)`.
3. If rejected, return `{"accepted": False, "rule_id", "reasons", "similar_rules"}` — no DB write.
4. If accepted, strip underscore-prefixed keys and `await db.create_rule(clean)` (`gate.py:258-260`).
5. If `origin_db_path` given, instantiate `OriginContextStore(origin_db_path)`, write `(rule_id, task_description, query_that_triggered, _consulted_rules)`, then close (`gate.py:262-274`).
6. Return `{"accepted": True, "rule_id", "authority": "ai-provisional", "confidence": "speculative", "reasons": []}`.

## C. Origin Context Store (`writ/origin_context.py`)

### Default DB path (`origin_context.py:18`)
```python
DEFAULT_DB_PATH = Path.home() / ".cache" / "writ" / "origin_context.db"
```

### Schema (`origin_context.py:20-28`)
```sql
CREATE TABLE IF NOT EXISTS origin_context (
    rule_id TEXT PRIMARY KEY,
    task_description TEXT NOT NULL,
    query_that_triggered TEXT,
    existing_rules_consulted TEXT,
    created_at TEXT NOT NULL
)
```
- `rule_id` is PK → write-once via `INSERT OR IGNORE`.
- `existing_rules_consulted` is JSON-encoded list of strings.
- `created_at` is ISO-8601 UTC timestamp.

### `OriginContextStore` class (`origin_context.py:31-87`)

- `__init__(self, db_path: Path = DEFAULT_DB_PATH)` (34-39): creates parent dir if missing, opens sqlite3, runs `_CREATE_TABLE`, commits.
- `write(rule_id, task_description, query_that_triggered, existing_rules_consulted) -> None` (41-64): uses `INSERT OR IGNORE`. Serializes `existing_rules_consulted` via `json.dumps`. `created_at = datetime.now(timezone.utc).isoformat()`.
- `get(rule_id: str) -> dict | None` (66-83): returns `None` if no row; otherwise parsed dict.
- `close() -> None` (85-87).

### Notes
- `propose` CLI command does NOT currently forward `query_that_triggered` — it's always None from CLI (`cli.py:918-924`).
- `existing_rules_consulted` is read from `candidate["_consulted_rules"]` (underscore-prefixed transient field stripped before Neo4j write).

## D. Frequency Tracking (`writ/frequency.py`)

### Constants (`frequency.py:14-15`)
```python
DEFAULT_GRADUATION_THRESHOLD = 50
DEFAULT_GRADUATION_RATIO_MIN = 0.75
```

### `GraduationResult` dataclass (`frequency.py:18-25`)
```python
@dataclass
class GraduationResult:
    graduated: bool
    flagged: bool
    ratio: float
    n: int
```

### `evaluate_graduation` — full body (`frequency.py:28-53`)
```python
def evaluate_graduation(
    times_positive: int,
    times_negative: int,
    threshold: int = DEFAULT_GRADUATION_THRESHOLD,
    ratio_min: float = DEFAULT_GRADUATION_RATIO_MIN,
) -> GraduationResult:
    n = times_positive + times_negative
    if n == 0:
        return GraduationResult(graduated=False, flagged=False, ratio=0.0, n=0)

    ratio = times_positive / n

    if n < threshold:
        return GraduationResult(graduated=False, flagged=False, ratio=ratio, n=n)

    if ratio >= ratio_min:
        return GraduationResult(graduated=True, flagged=False, ratio=ratio, n=n)

    return GraduationResult(graduated=False, flagged=True, ratio=ratio, n=n)
```

### Wilson confidence interval — **NOT IMPLEMENTED**
A grep for `wilson|Wilson|1.96|z_score|confidence_interval` across the codebase returns **zero matches**. The graduation logic uses a **plain ratio** (`times_positive / (times_positive + times_negative)`) with a fixed sample-size threshold (`n >= 50`). There is no statistical confidence interval, no z-score, no smoothing — just `ratio >= 0.75` after enough samples. **The handbook's reference to "Wilson confidence interval" does not match the code.**

### Mapping graduation → confidence weight (`ranking.py:115-133`)
```python
def compute_confidence_weight(
    static_confidence: str,
    times_positive: int,
    times_negative: int,
    threshold: int = 50,
    ratio_min: float = 0.75,
) -> float:
    from writ.frequency import evaluate_graduation
    grad = evaluate_graduation(times_positive, times_negative, threshold, ratio_min)
    if grad.graduated:
        return grad.ratio
    return CONFIDENCE_WEIGHTS.get(static_confidence, 0.8)
```
When `graduated=True`, the empirical `ratio` (e.g., 0.93) **replaces** the enum-driven weight.

`CONFIDENCE_WEIGHTS` (`ranking.py:57-62`):
- `"battle-tested": 1.0`
- `"production-validated": 0.8`
- `"peer-reviewed": 0.6`
- `"speculative": 0.3`

## E. Authoring Helpers (`writ/authoring.py`)

### Module constants (`authoring.py:19-21`)
```python
from writ.graph.schema import REDUNDANCY_SIMILARITY_THRESHOLD as REDUNDANCY_THRESHOLD
SUGGESTION_LIMIT = 5
```
`REDUNDANCY_SIMILARITY_THRESHOLD = 0.95` is defined in `schema.py:21`.

### `RuleIdCollisionError` (`authoring.py:24-35`)
```python
class RuleIdCollisionError(Exception):
    def __init__(self, rule_id: str, existing: dict) -> None:
        super().__init__(f"rule_id already exists in graph: {rule_id}")
        self.rule_id = rule_id
        self.existing = existing
```

### `check_id_collision` (`authoring.py:38-50`)
```python
async def check_id_collision(rule_id: str, db: Neo4jConnection) -> None:
```
Calls `await db.get_rule(rule_id)`; if non-None, raises `RuleIdCollisionError(rule_id, existing)`.

### `suggest_relationships` (`authoring.py:53-74`)
```python
def suggest_relationships(rule_data: dict, pipeline: RetrievalPipeline) -> list[dict]:
```
Builds query as `f"{trigger} {statement}"`. Excludes self. Calls `pipeline.query(query_text, exclude_rule_ids=exclude)`. Returns top `SUGGESTION_LIMIT` (5).

### `check_redundancy` (`authoring.py:77-104`)
```python
def check_redundancy(rule_data: dict, pipeline: RetrievalPipeline,
                    threshold: float = REDUNDANCY_THRESHOLD) -> list[dict]:
```
Encodes via `pipeline._model.encode(query_text).tolist()`. Calls `pipeline._vector.search(query_vector, k=10)`. Returns rules with `r.score >= threshold` (cosine similarity, INV-5 — independent of RRF score).

### `check_conflicts` (`authoring.py:107-125`)
```python
def check_conflicts(rule_id: str, cache: AdjacencyCache) -> list[dict]:
```
Calls `cache.get_neighbors(rule_id)`. Filters where `n["edge_type"] == "CONFLICTS_WITH"`.

`gate.py` duplicates the redundancy logic in `_check_similarity` rather than reusing `authoring.check_redundancy` — the gate version handles both 0.95 redundancy *and* 0.85 novelty in a single pass.

## F. Confidence Enum Integration

### How `SPECULATIVE` interacts with downweight
- `propose_rule` forces `confidence="speculative"` for every AI proposal (`gate.py:241`).
- `writ review --downweight` calls `update_rule_confidence(rule_id, "speculative")` (`cli.py:1011`) — manual demotion, no authority gate.
- `"speculative": 0.3` (`ranking.py:61`) — the lowest weight.

### How `peer-reviewed` is assigned on promotion
`writ review --promote` calls **two** updates back-to-back (`cli.py:989-990`):
```python
await db.update_rule_authority(rule_id, "ai-promoted")
await db.update_rule_confidence(rule_id, "peer-reviewed")
```
Promotion thus moves the rule from `(authority=ai-provisional, confidence=speculative)` → `(authority=ai-promoted, confidence=peer-reviewed)`.

### Confidence weight tiers create a deliberate gap
AI promotion gives `peer-reviewed = 0.6`, but `production-validated = 0.8` and `battle-tested = 1.0` are reserved — only reachable via empirical graduation (which substitutes the ratio directly, not the enum). There is no manual command to set those higher confidence tiers; they emerge from frequency data only.

## G. Workflow Trace: `writ propose` → graduation

1. **User invokes `writ propose ...`** (`cli.py:876-935`). Builds candidate with `last_validated=date.today().isoformat()`.
2. **Pipeline init** (`cli.py:912-916`): opens `Neo4jConnection`, calls `await build_pipeline(db)`.
3. **`propose_rule(...)` invoked** (`cli.py:918-924`). `origin_db_path=DEFAULT_DB_PATH`. `task_description` forwarded; `query_that_triggered` defaults to None.
4. **Authority + confidence forced** (`gate.py:240-241`).
5. **`structural_gate(...)` runs**: schema → mechanical-enforcement (if mandatory) → specificity → similarity → conflicts.
6a. **Reject path** (`gate.py:250-256`): no DB write, no origin context. CLI prints `Rejected: <rule_id>` + reasons.
6b. **Accept path** (`gate.py:258-274`): strip `_*` keys, `db.create_rule(clean)`, write origin context to SQLite. CLI prints `Accepted: <rule_id> (authority: ai-provisional)`.
7. **Human review queue**: `writ review --stats`, `writ review` (lists all ai-provisional), `writ review <rule_id>` (inspects + origin context).
8. **Promote** (`writ review <rule_id> --promote`): guard, confirm, two updates.
9. **Frequency accumulation (out-of-band)**: `db.increment_positive`/`increment_negative` bump counters and `last_seen=datetime()`.
10. **Graduation (read-time)**: during ranking, `compute_confidence_weight(...)` checks `n >= 50` and `pos/n >= 0.75`. If graduated, weight becomes empirical ratio. If `flagged`, surfaces in integrity report.

## H. Files Read

| File | Lines |
|---|---|
| `writ/gate.py` | 282 |
| `writ/authoring.py` | 125 |
| `writ/origin_context.py` | 86 |
| `writ/frequency.py` | 53 |
| `writ/graph/schema.py` | 524 (context skim) |
| `writ/cli.py` | 876-1045 (propose/review only) |
| `writ/graph/db.py` | 350-437 (authority/confidence/delete) |
| `writ/retrieval/ranking.py` | 1-180 (`compute_confidence_weight`) |

## I. Cross-References Noted

- **`Rule.authority` validation** uses `VALID_AUTHORITIES` (`schema.py:24`) at the Pydantic boundary.
- **`ai-provisional`/`speculative` enforcement** is *not* a schema constraint — it's a runtime override in `propose_rule`. The schema would happily accept `authority="human"` from a malicious caller; the gate prevents it.
- **`REDUNDANCY_SIMILARITY_THRESHOLD = 0.95`** is exported from `schema.py:21` and re-imported by `authoring.py:19`. `gate.py:25` defines its own `REDUNDANCY_THRESHOLD = 0.95` — same value, two definitions.
- **Hard-coded `threshold=50` and `ratio_min=0.75` in `compute_confidence_weight`** (`ranking.py:119-120`) duplicate the `DEFAULT_GRADUATION_*` constants in `frequency.py:14-15`. `writ.toml` overrides do not reach this call site.
- **`_check_conflicts` is a near-no-op for new candidates** because `candidate_id not in pipeline._metadata` short-circuits.
- **`writ propose` CLI does not forward `query_that_triggered`** — always passes None.
- **No Wilson interval / no statistical confidence** exists in the codebase — graduation is a plain ratio threshold. **Discrepancy with prior handbook framing.**
- **Methodology node types** inherit `authority`, `confidence`, `times_seen_*`, `last_seen` from `_MethodologyNodeBase` — evolution machinery is structurally compatible, but `propose_rule` only handles `Rule` today.
- **`mechanical_enforcement_path` requirement** ties to "plan Section 2.1" and `docs/mandatory-rule-audit.md`.
