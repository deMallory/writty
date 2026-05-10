# 07 — Rule Schema and Validation

This document focuses on the rule data model, every validator, and the validation gate stack. Schema and gate facts come from docs 02 (graph) and 11 (evolution-and-authority). This doc consolidates them through the lens of "what does Writ accept as a valid rule?"

## 1. Where rules are defined

Pydantic models live in `writ/graph/schema.py`. The `Rule` class (`schema.py:94-172`) is the canonical model.

Mandatory module-level constants (`schema.py:13-34`):
```python
RULE_ID_PATTERN = re.compile(r"^[A-Z][A-Z0-9]*(-[A-Z][A-Z0-9]*)+(-\d{3}|(-[A-Z][A-Z0-9]*))$")
SCOPE_PATTERN = re.compile(r"^[a-z][a-z0-9_-]*$")
STALENESS_WINDOW_DEFAULT = 365
EVIDENCE_DEFAULT = "doc:original-bible"
REDUNDANCY_SIMILARITY_THRESHOLD = 0.95
VALID_AUTHORITIES = ("human", "ai-provisional", "ai-promoted")
ENFORCEMENT_CONVENTIONS = ("human-review", "judgment-gate", "training-feedback", "audit-log", "advisory-only")  # documented but NOT enforced in code
```

ID pattern matches: `ARCH-ORG-001`, `FW-M2-RT-003`, `ENF-GATE-FINAL`, `DB-SQL-001`, `SEC-UNI-001`.

## 2. `Rule` Pydantic model — required fields

Per docstring `schema.py:96-99`: "Per PY-PYDANTIC-001: validates all fields at the data boundary."

| Field | Type | Required? | Default | Validator |
|---|---|---|---|---|
| `rule_id` | `str` | yes | — | `validate_rule_id` (lines 129-139): non-empty, matches `RULE_ID_PATTERN` |
| `domain` | `str` | yes | — | `validate_domain` (148-153): non-empty |
| `severity` | `Severity` enum | yes | — | enum coercion |
| `scope` | `str` | yes | — | `validate_scope` (155-163): matches `SCOPE_PATTERN` |
| `trigger` | `str` | yes | — | `validate_non_empty_text` (141-146) |
| `statement` | `str` | yes | — | `validate_non_empty_text` |
| `violation` | `str` | yes | — | `validate_non_empty_text` |
| `pass_example` | `str` | yes | — | `validate_non_empty_text` |
| `enforcement` | `str` | yes | — | `validate_non_empty_text` |
| `rationale` | `str` | yes | — | `validate_non_empty_text` |
| `last_validated` | `date` | yes | — | Pydantic coercion to `datetime.date` |

## 3. `Rule` Pydantic model — optional fields

| Field | Type | Default |
|---|---|---|
| `mandatory` | `bool` | `False` |
| `confidence` | `Confidence` enum | `Confidence.PRODUCTION_VALIDATED` |
| `authority` | `str` | `"human"` (validated against `VALID_AUTHORITIES`, lines 165-172) |
| `times_seen_positive` | `int` | `0` |
| `times_seen_negative` | `int` | `0` |
| `last_seen` | `str \| None` | `None` |
| `evidence` | `str` | `EVIDENCE_DEFAULT` (`"doc:original-bible"`) |
| `staleness_window` | `int` | `STALENESS_WINDOW_DEFAULT` (`365`) |
| `rationalization_counters` | `list[dict[str, str]]` | `Field(default_factory=list)` |
| `red_flag_thoughts` | `list[str]` | `Field(default_factory=list)` |
| `always_on` | `bool` | `False` |
| `mechanical_enforcement_path` | `str \| None` | `None` |
| `body` | `str` | `""` |
| `source_attribution` | `str \| None` | `None` |
| `source_commit` | `str \| None` | `None` |

## 4. Enums

```python
# schema.py:40-44
class Severity(str, Enum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"

# schema.py:47-51
class Confidence(str, Enum):
    BATTLE_TESTED = "battle-tested"
    PRODUCTION_VALIDATED = "production-validated"
    PEER_REVIEWED = "peer-reviewed"
    SPECULATIVE = "speculative"

# schema.py:54-58
class EvidenceType(str, Enum):
    INCIDENT = "incident"
    PR = "pr"
    DOC = "doc"
    ADR = "adr"
```

## 5. Methodology node schemas

`_MethodologyNodeBase` (alias `MethodologyNode`, `schema.py:275-334`) is the base for 10 methodology node types. Same authority/confidence/frequency fields as `Rule`. Differs in:
- `evidence` defaults to `"peer-reviewed"` (vs `"doc:original-bible"` for Rule).
- `severity` is `Severity | None` for non-retrievable types (Phase, Rationalization, etc.).
- `tags: list[str]` field with `_normalize_tags` validator that lowercases + sorts (per docs/phase-0-schema-proposal.md decision 6).

Per-type prefixes (validated by `_validate_node_id` factory at `schema.py:355-380`):
| Type | Prefix |
|---|---|
| Skill | `SKL-` |
| Playbook | `PBK-` |
| Technique | `TEC-` |
| AntiPattern | `ANT-` |
| ForbiddenResponse | `FRB-` |
| Phase | `PHA-` |
| Rationalization | `RAT-` |
| PressureScenario | `PSC-` |
| WorkedExample | `EXM-` |
| SubagentRole | `ROL-` |

## 6. Authority model

`VALID_AUTHORITIES = ("human", "ai-provisional", "ai-promoted")` (`schema.py:24`).

| Authority | Assigned where | Mechanism |
|---|---|---|
| `human` | Default for `Rule` and `_MethodologyNodeBase` | Pydantic field default |
| `ai-provisional` | `propose_rule` (`gate.py:240`) | Hard-overwrites `candidate["authority"] = "ai-provisional"` before gate check |
| `ai-promoted` | `cli.py:989` (`writ review --promote`) | Calls `db.update_rule_authority(rule_id, "ai-promoted")` |

The schema would happily accept `authority="human"` from any caller — the runtime forcing in `propose_rule` is the only enforcement.

## 7. The 5-check structural gate (`writ/gate.py`)

`structural_gate(candidate, pipeline, *, novelty_threshold=0.85, redundancy_threshold=0.95)` runs these checks in order. Any failure adds a reason to `GateResult.reasons`.

### Check 1: Schema validation (`_check_schema`, gate.py:109-116)
```python
clean = {k: v for k, v in candidate.items() if not k.startswith("_")}
try:
    Rule(**clean)
except ValidationError as e:
    result.reasons.append(f"Schema validation failed: {e}")
```

### Check 1b: Mechanical enforcement path (`_check_mechanical_enforcement`, gate.py:119-141)
Runs only when `candidate.get("mandatory", False)` is True. Rejects if `mechanical_enforcement_path` is None or whitespace.

Literal rejection text:
```
Mechanical-enforcement policy (plan Section 2.1): rule '<rid>' is mandatory but has no mechanical_enforcement_path. Either name a hook + matcher + deny condition, or demote to mandatory=false (advisory).
```

### Check 2: Specificity (`_check_specificity`, gate.py:144-158)
Concatenates `trigger + " " + statement` and matches against `_VAGUE_PATTERNS`:
```python
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
```

Rejection format: `f"Specificity: vague language detected: {', '.join(found)}"`.

### Check 3 & 4: Redundancy + Novelty (`_check_similarity`, gate.py:161-193)
Encodes `trigger + " " + statement` via `pipeline._model.encode(...)`. Calls `pipeline._vector.search(query_vector, k=10)`. Excludes self by `rule_id`.

For each result `r`:
- If `r.score >= redundancy_threshold` (0.95): `f"Redundancy: cosine {r.score:.4f} with {r.rule_id} (threshold: {redundancy_threshold})"`
- Elif `r.score >= novelty_threshold` (0.85): `f"Novelty: cosine {r.score:.4f} with {r.rule_id} (threshold: {novelty_threshold})"`

### Check 5: Conflict (`_check_conflicts`, gate.py:196-221)
Skips if `rule_id` not in `pipeline._metadata` (new candidates pass automatically). Otherwise looks at `pipeline._cache.get_neighbors(candidate_id)` and flags any `edge_type == "CONFLICTS_WITH"`.

Rejection format: `f"Conflict: CONFLICTS_WITH edge to {n['rule_id']}"`.

## 8. `propose_rule` orchestrator (gate.py:224-282)

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

Order:
1. `candidate["authority"] = "ai-provisional"` (force)
2. `candidate["confidence"] = "speculative"` (force)
3. Run `structural_gate`
4. If rejected → return `{"accepted": False, "rule_id", "reasons", "similar_rules"}` — no DB write
5. If accepted → `await db.create_rule(clean)` + write origin context to SQLite
6. Return `{"accepted": True, "rule_id", "authority": "ai-provisional", "confidence": "speculative", "reasons": []}`

## 9. The enforceability standard

A rule is "enforceable" when it has:
1. A non-empty `trigger` (validated by `validate_non_empty_text`).
2. A non-empty `statement` (validated by `validate_non_empty_text`).
3. A `violation` example and a `pass_example` (both validated non-empty).
4. An `enforcement` field (free-text but non-empty) — describes how the rule is enforced (human-review, judgment-gate, training-feedback, audit-log, advisory-only — though `ENFORCEMENT_CONVENTIONS` is documented but not enforced).
5. A `rationale` (non-empty) explaining why.
6. If `mandatory=True`, a `mechanical_enforcement_path` is required (gate check 1b).
7. Specificity: no vague language from the 10-pattern blocklist.

## 10. Confidence weight enforceability

`CONFIDENCE_WEIGHTS` (`ranking.py:57-62`):
- `"battle-tested": 1.0`
- `"production-validated": 0.8`
- `"peer-reviewed": 0.6`
- `"speculative": 0.3`

Higher tiers (`production-validated`, `battle-tested`) are reserved — only reachable via empirical graduation through `evaluate_graduation` (`frequency.py:28-53`):
- Threshold `n >= 50` (positive + negative observations).
- Ratio `pos/n >= 0.75`.
- Below 50 observations → static enum weight is used.
- At or above 50 observations and ratio passing → empirical ratio replaces enum weight at read time.
- At or above 50 observations and ratio failing → `flagged=True` (surfaces in integrity report; no automatic state change).

**No Wilson confidence interval** is implemented — the handbook's claim is incorrect. See doc 11.

## 11. Validation surfaces in the codebase

| Surface | What validates |
|---|---|
| `Rule(**dict)` (Pydantic) | All field-level validators on construction |
| `validate_parsed_rule` (`writ/graph/ingest.py:196-209`) | Strips `_*` keys, calls `Rule(**clean)`, wraps errors per ARCH-ERR-001 |
| `validate_parsed_node` (`writ/graph/ingest.py:362-382`) | Methodology node Pydantic construction |
| `structural_gate` (`writ/gate.py:54-106`) | The 5-check gate for AI proposals |
| `IntegrityChecker` (`writ/graph/integrity.py`) | Post-ingest checks: conflicts, orphans, stale, redundant, frequency-stale, graduation-flags |
| `_validate_phase_a` (`bin/lib/writ-session.py:1223-1291`) | plan.md sections + rule IDs in `## Rules Applied` validated against session's loaded_rule_ids (logs `hallucinated_rule_ids` event) |

## 12. Integrity check thresholds (recap)

From `writ/graph/integrity.py`:
- Redundancy: cosine ≥ 0.95 on `trigger + " " + statement` embeddings (mandatory rules excluded).
- Stale: `last_validated + staleness_window >= today`. Default `staleness_window = 365` days.
- Frequency-stale: `pos + neg == 0` AND `last_seen` is None or older than `window_days = 90`.
- Graduation: `pos + neg >= 50` AND `ratio >= 0.75` (default thresholds).
- Unreviewed: `unreviewed < max(warning_floor=5, warning_percentage=0.10 * total)`.
- Query-rule ratio: `query_count * 10 >= rule_count` (advisory).

## 13. Files Read

- `writ/graph/schema.py` — see doc 02.
- `writ/gate.py` — see doc 11.
- `writ/authoring.py` — see doc 11.
- `writ/origin_context.py` — see doc 11.
- `writ/frequency.py` — see doc 11.
- `writ/graph/integrity.py` — see doc 02.
- `writ/graph/ingest.py` — see doc 02.

## Cross-References Noted

- This document re-uses extraction content from docs 02 (schema, integrity), 11 (gate, propose, frequency, origin context), and 03 (confidence weights).
- The "enforceability standard" was historically tracked in `RAG_arch_handbook.md`; see doc 01 for the design rationale.
- `_validate_phase_a`'s rule-ID-hallucination check is the runtime equivalent of schema validation for AI-asserted rule references in plans — see doc 06.
