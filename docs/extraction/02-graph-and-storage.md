# 02 — Graph and Storage Layer (full extraction)

Source paths read in full:
- `writ/graph/schema.py` (523 lines)
- `writ/graph/db.py` (446 lines)
- `writ/graph/ingest.py` (382 lines)
- `writ/graph/integrity.py` (273 lines)
- `writ/graph/__init__.py` (0 bytes, empty package marker)

## 1. Module-level constants and patterns (`schema.py`)

`schema.py:13` — rule/node ID format:
```python
RULE_ID_PATTERN = re.compile(r"^[A-Z][A-Z0-9]*(-[A-Z][A-Z0-9]*)+(-\d{3}|(-[A-Z][A-Z0-9]*))$")
```
Comment `schema.py:11-12`: matches `ARCH-ORG-001`, `FW-M2-RT-003`, `ENF-GATE-FINAL`, `DB-SQL-001`, `SEC-UNI-001`.

`schema.py:17` — scope format (Phase 1c, format-not-membership):
```python
SCOPE_PATTERN = re.compile(r"^[a-z][a-z0-9_-]*$")
```

`schema.py:19-21`:
```python
STALENESS_WINDOW_DEFAULT = 365
EVIDENCE_DEFAULT = "doc:original-bible"
REDUNDANCY_SIMILARITY_THRESHOLD = 0.95
```

`schema.py:24`:
```python
VALID_AUTHORITIES = ("human", "ai-provisional", "ai-promoted")
```

`schema.py:28-34` — documented but NOT enforced in code:
```python
ENFORCEMENT_CONVENTIONS = ("human-review", "judgment-gate", "training-feedback", "audit-log", "advisory-only")
```

## 2. Enums (`schema.py`)

- `Severity(str, Enum)` `schema.py:40-44`: `CRITICAL="critical"`, `HIGH="high"`, `MEDIUM="medium"`, `LOW="low"`.
- `Confidence(str, Enum)` `schema.py:47-51`: `BATTLE_TESTED="battle-tested"`, `PRODUCTION_VALIDATED="production-validated"`, `PEER_REVIEWED="peer-reviewed"`, `SPECULATIVE="speculative"`.
- `EvidenceType(str, Enum)` `schema.py:54-58`: `INCIDENT="incident"`, `PR="pr"`, `DOC="doc"`, `ADR="adr"`.
- `NodeType(str, Enum)` `schema.py:61-77`: `RULE="Rule"`, `ABSTRACTION="Abstraction"`, retrievable: `SKILL="Skill"`, `PLAYBOOK="Playbook"`, `TECHNIQUE="Technique"`, `ANTIPATTERN="AntiPattern"`, `FORBIDDEN_RESPONSE="ForbiddenResponse"`; non-retrievable: `PHASE="Phase"`, `RATIONALIZATION="Rationalization"`, `PRESSURE_SCENARIO="PressureScenario"`, `WORKED_EXAMPLE="WorkedExample"`, `SUBAGENT_ROLE="SubagentRole"`.
- `RETRIEVABLE_NODE_TYPES` `schema.py:80-88`: frozenset of `{RULE, ABSTRACTION, SKILL, PLAYBOOK, TECHNIQUE, ANTIPATTERN, FORBIDDEN_RESPONSE}`.

## 3. Pydantic node-type models

### Inheritance tree

```
BaseModel
├── Rule                                       (schema.py:94)
├── Abstraction                                (schema.py:175)
├── Domain                                     (schema.py:183)
├── Evidence                                   (schema.py:189)
├── Tag                                        (schema.py:196)
├── _DirectedEdge                              (schema.py:204)
│   ├── DependsOn / Precedes / ConflictsWith / Supplements / Supersedes / RelatedTo  (218-239)
│   ├── Teaches / Counters / Demonstrates / Dispatches / Gates / PressureTests       (494-515)
│   └── Contains / AttachedTo                                                        (518-523)
├── AppliesTo                                  (schema.py:242)
├── Abstracts                                  (schema.py:248)
├── JustifiedBy                                (schema.py:253)
└── _MethodologyNodeBase  (alias MethodologyNode)  (schema.py:275, alias 352)
    ├── _RetrievableBase                       (schema.py:337) — adds severity: Severity (required)
    │   ├── Skill                              (schema.py:386)
    │   ├── Playbook                           (schema.py:392)
    │   ├── Technique                          (schema.py:401)
    │   ├── AntiPattern                        (schema.py:407)
    │   └── ForbiddenResponse                  (schema.py:415)
    └── _NonRetrievableBase                    (schema.py:343) — severity: Severity | None = None
        ├── Phase                              (schema.py:434)
        ├── Rationalization                    (schema.py:444)
        ├── PressureScenario                   (schema.py:453)
        ├── WorkedExample                      (schema.py:464)
        └── SubagentRole                       (schema.py:475)
```

### 3.1 `Rule` — `schema.py:94-172`

Docstring: "A single enforceable rule in the knowledge graph. Per PY-PYDANTIC-001: validates all fields at the data boundary."

| Field | Type | Default | Line |
|---|---|---|---|
| `rule_id` | `str` | required | 100 |
| `domain` | `str` | required | 101 |
| `severity` | `Severity` | required | 102 |
| `scope` | `str` | required | 103 |
| `trigger` | `str` | required | 104 |
| `statement` | `str` | required | 105 |
| `violation` | `str` | required | 106 |
| `pass_example` | `str` | required | 107 |
| `enforcement` | `str` | required | 108 |
| `rationale` | `str` | required | 109 |
| `mandatory` | `bool` | `False` | 110 |
| `confidence` | `Confidence` | `Confidence.PRODUCTION_VALIDATED` | 111 |
| `authority` | `str` | `"human"` | 112 |
| `times_seen_positive` | `int` | `0` | 113 |
| `times_seen_negative` | `int` | `0` | 114 |
| `last_seen` | `str \| None` | `None` | 115 |
| `evidence` | `str` | `EVIDENCE_DEFAULT` (`"doc:original-bible"`) | 116 |
| `staleness_window` | `int` | `STALENESS_WINDOW_DEFAULT` (`365`) | 117 |
| `last_validated` | `date` | required | 118 |
| `rationalization_counters` | `list[dict[str, str]]` | `Field(default_factory=list)` | 121 |
| `red_flag_thoughts` | `list[str]` | `Field(default_factory=list)` | 122 |
| `always_on` | `bool` | `False` | 123 |
| `mechanical_enforcement_path` | `str \| None` | `None` | 124 |
| `body` | `str` | `""` | 125 |
| `source_attribution` | `str \| None` | `None` | 126 |
| `source_commit` | `str \| None` | `None` | 127 |

Validators:
- `validate_rule_id` (`129-139`): non-empty, must match `RULE_ID_PATTERN`.
- `validate_non_empty_text` (`141-146`): applied to `trigger`, `statement`, `violation`, `pass_example`, `enforcement`, `rationale`. Rejects empty/whitespace.
- `validate_domain` (`148-153`): non-empty.
- `validate_scope` (`155-163`): must match `SCOPE_PATTERN`.
- `validate_authority` (`165-172`): in `VALID_AUTHORITIES`.

### 3.2-3.5 Plain BaseModels

- `Abstraction` (175-180): `abstraction_id, summary, rule_ids: list[str], domain, compression_ratio: float`. No validators.
- `Domain` (183-186): `name, rule_count, last_updated: datetime`.
- `Evidence` (189-193): `evidence_id, type: EvidenceType, reference, date`.
- `Tag` (196-198): `name, rule_count`.

### 3.6 `_MethodologyNodeBase` (alias `MethodologyNode`) — `schema.py:275-334`

| Field | Type | Default |
|---|---|---|
| `domain` | `str` | required |
| `scope` | `str` | required |
| `trigger` | `str` | required |
| `statement` | `str` | required |
| `rationale` | `str` | required |
| `tags` | `list[str]` | `default_factory=list` |
| `confidence` | `Confidence` | `PRODUCTION_VALIDATED` |
| `authority` | `str` | `"human"` |
| `last_validated` | `date` | required |
| `staleness_window` | `int` | `STALENESS_WINDOW_DEFAULT` |
| `evidence` | `str` | `"peer-reviewed"` |
| `times_seen_positive` | `int` | `0` |
| `times_seen_negative` | `int` | `0` |
| `last_seen` | `str \| None` | `None` |
| `source_attribution` | `str \| None` | `None` |
| `source_commit` | `str \| None` | `None` |
| `body` | `str` | `""` |

Validators (underscore-prefixed): `_validate_domain`, `_validate_scope`, `_validate_non_empty_text` (on `trigger`, `statement`, `rationale`), `_validate_authority`, `_normalize_tags`.

`_normalize_tags(v)` (`schema.py:265-272`):
```python
def _normalize_tags(v: list[str]) -> list[str]:
    return sorted({t.lower() for t in v})
```
"Per docs/phase-0-schema-proposal.md resolved-decision 6: prevents BM25 index inconsistency ('TDD' vs 'tdd' as distinct terms)."

### 3.7 ID-prefix factory `_validate_node_id` — `schema.py:355-380`

Returns a validator: rejects empty, must match `RULE_ID_PATTERN`, if `expected_prefix` set must start with it.

Per-type prefixes (docstring `360-363`): Skill `SKL-`, Playbook `PBK-`, Technique `TEC-`, AntiPattern `ANT-`, ForbiddenResponse `FRB-`, Phase `PHA-`, Rationalization `RAT-`, PressureScenario `PSC-`, WorkedExample `EXM-`, SubagentRole `ROL-`.

### 3.8 Retrievable methodology nodes
- `Skill` (386): `skill_id` (SKL-).
- `Playbook` (392): `playbook_id` (PBK-); `phase_ids: list[str]`; `preconditions: list[str]=[]`; `dispatched_roles: list[str]=[]`.
- `Technique` (401): `technique_id` (TEC-).
- `AntiPattern` (407): `antipattern_id` (ANT-); `counter_nodes: list[str]`; `named_in: str|None=None`.
- `ForbiddenResponse` (415): `forbidden_id` (FRB-); `forbidden_phrases: list[str]`; `what_to_say_instead: str` (validated non-empty); `always_on: bool=True`.

### 3.9 Non-retrievable methodology nodes
- `Phase` (434): `phase_id` (PHA-), `position`, `name`, `description`, `parent_playbook_id`.
- `Rationalization` (444): `rationalization_id` (RAT-), `thought`, `counter`, `attached_to`.
- `PressureScenario` (453): `scenario_id` (PSC-), `prompt`, `expected_compliance`, `failure_patterns: list[str]`, `rule_under_test`, `difficulty`.
- `WorkedExample` (464): `example_id` (EXM-), `title`, `before`, `applied_skill`, `result`, `linked_skill`.
- `SubagentRole` (475): `role_id` (ROL-), `name`, `prompt_template`, `dispatched_by: list[str]=[]`, `model_preference: str|None=None`, `tools: str|None=None`, `description: str|None=None`.

## 4. Edge models

### 4.1 `_DirectedEdge` — `schema.py:204-215`
`source_id: str`, `target_id: str`. Validator `validate_non_empty` rejects empty endpoints. **No edge properties on any subclass.**

### 4.2 Pre-existing directed edges (schema.py:218-239)

| Class | Line | Cypher rel type |
|---|---|---|
| `DependsOn` | 218 | `DEPENDS_ON` |
| `Precedes` | 222 | `PRECEDES` |
| `ConflictsWith` | 226 | `CONFLICTS_WITH` |
| `Supplements` | 230 | `SUPPLEMENTS` |
| `Supersedes` | 234 | `SUPERSEDES` |
| `RelatedTo` | 238 | `RELATED_TO` |

### 4.3 Phase 1 directed edges (schema.py:494-523)

| Class | Line | Rel type | Source labels | Target labels | Semantic |
|---|---|---|---|---|---|
| `Teaches` | 494 | `TEACHES` | Skill, Playbook | Rule, Technique | "teaches the enforcement target" |
| `Counters` | 498 | `COUNTERS` | AntiPattern, Rationalization | Skill, Playbook, Rule | "countered by the target" |
| `Demonstrates` | 502 | `DEMONSTRATES` | WorkedExample, ForbiddenResponse | Skill, Rule | "demonstrates the target's discipline" |
| `Dispatches` | 506 | `DISPATCHES` | Playbook, Skill | SubagentRole, Technique | "dispatched as sub-invocation" |
| `Gates` | 510 | `GATES` | Rule | Skill, Playbook | "mechanical enforcement" |
| `PressureTests` | 514 | `PRESSURE_TESTS` | PressureScenario | Rule, Skill, Playbook | "scenario tests compliance" |
| `Contains` | 518 | `CONTAINS` | Playbook | Phase | "phase is structural member" |
| `AttachedTo` | 522 | `ATTACHED_TO` | Rationalization | Skill, Playbook, Rule | "rationalization attached to parent" |

### 4.4 Non-`_DirectedEdge` edge models
- `AppliesTo` (242-245): `rule_id`, `target_name`, `target_type`.
- `Abstracts` (248-250): `abstraction_id: str`, `rule_ids: list[str]`.
- `JustifiedBy` (253-255): `rule_id: str`, `evidence_id: str`.

`ABSTRACTS` is realised in Cypher (see §7.5) but not via the Pydantic model.

### 4.5 Driver-level allowlist (db.py:40-47)
```python
ALLOWED_EDGE_TYPES: frozenset[str] = frozenset({
    "DEPENDS_ON", "PRECEDES", "CONFLICTS_WITH", "SUPPLEMENTS",
    "SUPERSEDES", "RELATED_TO", "APPLIES_TO", "ABSTRACTS", "JUSTIFIED_BY",
    "TEACHES", "COUNTERS", "DEMONSTRATES", "DISPATCHES",
    "GATES", "PRESSURE_TESTS", "CONTAINS", "ATTACHED_TO",
})
```
17 types total. `create_edge` rejects unknown types with `ValueError("Unknown edge type: {edge_type}")` at `db.py:127-128`.

## 5. Driver label/id maps (db.py)

`db.py:22-25`:
```python
METHODOLOGY_NODE_LABELS: frozenset[str] = frozenset({
    "Skill", "Playbook", "Technique", "AntiPattern", "ForbiddenResponse",
    "Phase", "Rationalization", "PressureScenario", "WorkedExample", "SubagentRole",
})
```

`db.py:27-38`:
```python
METHODOLOGY_NODE_ID_FIELDS: dict[str, str] = {
    "Skill": "skill_id", "Playbook": "playbook_id", "Technique": "technique_id",
    "AntiPattern": "antipattern_id", "ForbiddenResponse": "forbidden_id",
    "Phase": "phase_id", "Rationalization": "rationalization_id",
    "PressureScenario": "scenario_id", "WorkedExample": "example_id",
    "SubagentRole": "role_id",
}
```
`Rule` is NOT in either map; it has its own dedicated `create_rule` method.

## 6. Database connection

### 6.1 `Neo4jConnection.__init__` (db.py:86-88)
```python
def __init__(self, uri: str, user: str, password: str, database: str = "neo4j") -> None:
    self._driver: AsyncDriver = AsyncGraphDatabase.driver(uri, auth=(user, password))
    self._database = database
```
Driver: `neo4j.AsyncGraphDatabase`. Database defaults to `"neo4j"`. URI/auth resolution at call sites (`writ.config.get_neo4j_uri/_user/_password`); not in this layer.

### 6.2 Module docstring (db.py:1-7)
"Neo4j connection layer — bolt protocol, connection pool, async session management. Per PY-ASYNC-001: all Neo4j operations use AsyncSession (neo4j.AsyncGraphDatabase). Sync drivers must never be used in async call chains. Per PERF-IO-001: no sync I/O in the hot path."

### 6.3 Session pattern
Every method opens a fresh session:
```python
async with self._driver.session(database=self._database) as session:
    result = await session.run(query, ...)
```
NO explicit transactions. Every statement runs in implicit auto-commit. NO batching: one statement per session.

### 6.4 `GraphConnection` Protocol (db.py:66-76)
```python
class GraphConnection(Protocol):
    async def get_rule(self, rule_id: str) -> dict | None: ...
    async def create_rule(self, rule_data: dict) -> str: ...
    async def create_edge(self, edge_type: str, source_id: str, target_id: str) -> None: ...
    async def traverse_neighbors(self, rule_id: str, hops: int) -> list[dict]: ...
    async def close(self) -> None: ...
```

### 6.5 Close (db.py:444-446)
```python
async def close(self) -> None:
    await self._driver.close()
```

### 6.6 Value coercion `_coerce_neo4j_value` (db.py:50-63)
```python
def _coerce_neo4j_value(v):
    import json
    if hasattr(v, "isoformat"):
        return v.isoformat()
    if isinstance(v, dict):
        return json.dumps(v)
    if isinstance(v, list) and v and isinstance(v[0], dict):
        return json.dumps(v)
    return v
```
Used by `create_rule` and `create_methodology_node` (NOT by `create_abstraction`).

## 7. All Cypher queries

### 7.1 Read — single-node fetches

`get_rule(rule_id)` (db.py:90-98):
```cypher
MATCH (r:Rule {rule_id: $rule_id}) RETURN r
```

`get_rule_abstraction(rule_id)` (db.py:294-314):
```cypher
MATCH (a:Abstraction)-[:ABSTRACTS]->(r:Rule {rule_id: $rule_id})
OPTIONAL MATCH (a)-[:ABSTRACTS]->(sibling:Rule)
WHERE sibling.rule_id <> $rule_id
RETURN a.abstraction_id AS abstraction_id, collect(sibling.rule_id) AS sibling_rule_ids
```

`get_abstraction(abstraction_id)` (db.py:270-284):
```cypher
MATCH (a:Abstraction {abstraction_id: $abstraction_id})
OPTIONAL MATCH (a)-[:ABSTRACTS]->(r:Rule)
RETURN a, collect(r {.*}) AS members
```

### 7.2 Read — list fetches

`count_rules()` (db.py:199-205):
```cypher
MATCH (r:Rule) RETURN count(r) AS count
```

`get_all_rules()` (db.py:207-212):
```cypher
MATCH (r:Rule) RETURN r ORDER BY r.rule_id
```

`get_all_edges()` (db.py:214-226) — only Rule→Rule edges:
```cypher
MATCH (a:Rule)-[rel]->(b:Rule)
RETURN a.rule_id AS from_id, b.rule_id AS to_id, type(rel) AS edge_type
ORDER BY a.rule_id, b.rule_id
```

`get_all_abstractions()` (db.py:253-268):
```cypher
MATCH (a:Abstraction)
OPTIONAL MATCH (a)-[:ABSTRACTS]->(r:Rule)
RETURN a, collect(r.rule_id) AS member_ids
ORDER BY a.abstraction_id
```

`get_rules_by_authority(authority)` (db.py:354-364):
```cypher
MATCH (r:Rule) WHERE r.authority = $authority
RETURN r ORDER BY r.last_validated DESC
```

`count_by_authority()` (db.py:428-437):
```cypher
MATCH (r:Rule)
RETURN coalesce(r.authority, 'human') AS authority, count(r) AS count
ORDER BY authority
```

### 7.3 Read — traversal

`traverse_neighbors(rule_id, hops=1)` (db.py:174-197). `hops` validated `1..3`; literal-interpolated:
```cypher
MATCH (start:Rule {rule_id: $rule_id})-[rel*1..{hops}]-(neighbor:Rule)
WITH neighbor, rel
UNWIND rel AS r
RETURN DISTINCT
    neighbor.rule_id AS rule_id,
    type(r) AS edge_type,
    startNode(r).rule_id AS from_id,
    endNode(r).rule_id AS to_id
```
Bidirectional pattern.

### 7.4 Write — node upserts

`create_rule(rule_data)` (db.py:100-118):
```cypher
MERGE (r:Rule {rule_id: $rule_id})
SET r += $props
RETURN r.rule_id AS rule_id
```

`create_methodology_node(node_type, data)` (db.py:150-172):
```cypher
MERGE (n:{node_type} {{{id_field}: $node_id}})
SET n += $props
RETURN n.{id_field} AS id
```
`{node_type}` and `{id_field}` literal-interpolated (validated via frozenset).

`create_abstraction(data)` (db.py:228-241) — does NOT use `_coerce_neo4j_value`:
```cypher
MERGE (a:Abstraction {abstraction_id: $abstraction_id})
SET a += $props
RETURN a.abstraction_id AS abstraction_id
```

### 7.5 Write — edges

`create_edge(edge_type, source_id, target_id)` (db.py:120-148). Endpoints matched by ANY known *_id property (label-agnostic):
```cypher
MATCH (a) WHERE a.rule_id = $source_id
    OR a.skill_id = $source_id OR a.playbook_id = $source_id
    OR a.technique_id = $source_id OR a.antipattern_id = $source_id
    OR a.forbidden_id = $source_id OR a.phase_id = $source_id
    OR a.rationalization_id = $source_id OR a.scenario_id = $source_id
    OR a.example_id = $source_id OR a.role_id = $source_id
MATCH (b) WHERE b.rule_id = $target_id
    OR b.skill_id = $target_id OR b.playbook_id = $target_id
    OR b.technique_id = $target_id OR b.antipattern_id = $target_id
    OR b.forbidden_id = $target_id OR b.phase_id = $target_id
    OR b.rationalization_id = $target_id OR b.scenario_id = $target_id
    OR b.example_id = $target_id OR b.role_id = $target_id
MERGE (a)-[:{edge_type}]->(b)
```

`create_abstracts_edge(abstraction_id, rule_id)` (db.py:243-251):
```cypher
MATCH (a:Abstraction {abstraction_id: $abstraction_id})
MATCH (r:Rule {rule_id: $rule_id})
MERGE (a)-[:ABSTRACTS]->(r)
```

### 7.6 Update

```cypher
-- update_rule_authority (db.py:366-376)
MATCH (r:Rule {rule_id: $rule_id})
SET r.authority = $authority
RETURN r.rule_id AS rule_id

-- update_rule_confidence (db.py:378-388)
MATCH (r:Rule {rule_id: $rule_id})
SET r.confidence = $confidence
RETURN r.rule_id AS rule_id

-- increment_positive (db.py:390-401)
MATCH (r:Rule {rule_id: $rule_id})
SET r.times_seen_positive = coalesce(r.times_seen_positive, 0) + 1,
    r.last_seen = datetime()
RETURN r.rule_id AS rule_id

-- increment_negative (db.py:403-414)
MATCH (r:Rule {rule_id: $rule_id})
SET r.times_seen_negative = coalesce(r.times_seen_negative, 0) + 1,
    r.last_seen = datetime()
RETURN r.rule_id AS rule_id
```

### 7.7 Delete

```cypher
-- delete_rule (db.py:416-426)
MATCH (r:Rule {rule_id: $rule_id})
DETACH DELETE r
RETURN count(r) AS deleted

-- delete_abstractions (db.py:286-292)
MATCH (a:Abstraction) DETACH DELETE a RETURN count(a) AS deleted

-- clear_all (db.py:439-442) — for test cleanup only
MATCH (n) DETACH DELETE n
```

### 7.8 Schema management — `apply_constraints()` (db.py:316-340)

Static statements:
```cypher
CREATE CONSTRAINT rule_id_unique IF NOT EXISTS FOR (r:Rule) REQUIRE r.rule_id IS UNIQUE
CREATE INDEX rule_domain IF NOT EXISTS FOR (r:Rule) ON (r.domain)
CREATE INDEX rule_mandatory IF NOT EXISTS FOR (r:Rule) ON (r.mandatory)
```

Then for each (label, id_field) in `METHODOLOGY_NODE_ID_FIELDS`:
```cypher
CREATE CONSTRAINT {label_lower}_{id_field}_unique IF NOT EXISTS
    FOR (n:{label}) REQUIRE n.{id_field} IS UNIQUE
CREATE INDEX {label_lower}_domain IF NOT EXISTS
    FOR (n:{label}) ON (n.domain)
```

Total after a complete apply: 23 constraint/index objects across 11 node types.

**Gap**: NO uniqueness constraint on `Abstraction.abstraction_id` despite `create_abstraction` using `MERGE` on it.

`list_constraints()` (db.py:342-346): `SHOW CONSTRAINTS`.
`list_indexes()` (db.py:348-352): `SHOW INDEXES`.

### 7.9 Cypher in `integrity.py`

`detect_conflicts` (integrity.py:26-36):
```cypher
MATCH (a:Rule)-[:CONFLICTS_WITH]->(b:Rule)
WHERE a.rule_id < b.rule_id
RETURN a.rule_id AS rule_a, b.rule_id AS rule_b
ORDER BY rule_a
```

`detect_orphans` (integrity.py:38-48):
```cypher
MATCH (r:Rule) WHERE NOT (r)--()
RETURN r.rule_id AS rule_id ORDER BY rule_id
```

`detect_stale` (integrity.py:50-78):
```cypher
MATCH (r:Rule)
WHERE r.last_validated IS NOT NULL AND r.staleness_window IS NOT NULL
RETURN r.rule_id AS rule_id, r.last_validated AS last_validated, r.staleness_window AS staleness_window
```
Python post-processing parses `last_validated` ISO date and filters where `expiry = last_val + timedelta(days=window) < today`.

`detect_redundant` (integrity.py:80-118):
```cypher
MATCH (r:Rule)
WHERE r.mandatory IS NULL OR r.mandatory = false
RETURN r.rule_id AS rule_id, r.trigger AS trigger, r.statement AS statement
```
Embeddings: `SentenceTransformer("all-MiniLM-L6-v2")`, normalized, O(n²) cosine pairs, threshold 0.95. Mandatory rules excluded.

`detect_confidence_defaults` (integrity.py:120-130):
```cypher
MATCH (r:Rule) WHERE r.confidence = 'production-validated'
RETURN r.rule_id AS rule_id ORDER BY rule_id
```

`detect_frequency_stale(window_days=90)` (integrity.py:190-207):
```cypher
MATCH (r:Rule)
WHERE (coalesce(r.times_seen_positive, 0) + coalesce(r.times_seen_negative, 0)) = 0
  AND (r.last_seen IS NULL OR r.last_seen < datetime() - duration({days: $window_days}))
RETURN r.rule_id AS rule_id, r.last_seen AS last_seen
ORDER BY rule_id
```

`detect_graduation_flags` (integrity.py:209-247):
```cypher
MATCH (r:Rule)
WHERE (coalesce(r.times_seen_positive, 0) + coalesce(r.times_seen_negative, 0)) >= $threshold
RETURN r.rule_id AS rule_id,
       coalesce(r.times_seen_positive, 0) AS pos,
       coalesce(r.times_seen_negative, 0) AS neg
```

## 8. Ingest pipeline (`ingest.py`)

Module docstring (1-17): "bible/*.md is the exported view of the canonical Neo4j graph, not the source of truth. Use `writ import-markdown` only for initial bootstrap."

Three formats: legacy `<!-- RULE START: id -->`, Phase 1 `<!-- NODE START type=X id=Y -->`, YAML front-matter (preferred).

### 8.1 Patterns (ingest.py:45-51)
```python
RULE_START_PATTERN = re.compile(r"<!--\s*RULE START:\s*(\S+)\s*-->")
RULE_END_PATTERN = re.compile(r"<!--\s*RULE END:\s*(\S+)\s*-->")
NODE_START_PATTERN = re.compile(r"<!--\s*NODE START\s+type=(\S+)\s+id=(\S+)\s*-->")
NODE_END_PATTERN = re.compile(r"<!--\s*NODE END:\s*(\S+)\s*-->")
METADATA_PATTERN = re.compile(r"\*\*(\w+)\*\*:\s*(.+)")
CROSS_REF_PATTERN = re.compile(r"\b([A-Z][A-Z0-9]*(?:-[A-Z][A-Z0-9]*)+(?:-\d{3}|-[A-Z][A-Z0-9]*))\b")
FRONT_MATTER_PATTERN = re.compile(r"^---\n(.*?)\n---\n(.*)", re.DOTALL)
```

### 8.2 Functions

- `parse_rules_from_file(filepath)` (94-116): UTF-8 read; iterates RULE_START matches, extracts block.
- `_parse_rule_block(rule_id, block)` (119-169): metadata + sections. Mandatory default: `False`. Comment 145-148: "The earlier rule_id.startswith('ENF-') convention was removed 2026-05-09."
- `_extract_section(block, heading_prefix)` (172-193): captures lines after `### Heading` until next `### `.
- `validate_parsed_rule(rule_data)` (196-209): strips `_*` keys; `Rule(**clean)`. Wraps errors per ARCH-ERR-001.
- `discover_rule_files(bible_dir)` (212-214): `sorted(bible_dir.rglob("*.md"))`.
- `parse_nodes_from_file(filepath)` (220-277) — Phase 1 multi-format dispatcher. Precedence: YAML front-matter → NODE START markers → legacy RULE START.
- `_parse_node_block(node_type, node_id, block)` (280-314): for Rule, mandatory falls back to `node_id.startswith("ENF-")` if not declared. **DIVERGES** from `_parse_rule_block`.
- `parse_edges_from_file(filepath)` (326-359): YAML `edges:` list only. Inline edge markers reserved for future.
- `validate_parsed_node(node_data)` (362-382): looks up `NODE_TYPE_MODELS`; unknown types raise.

### 8.3 End-to-end flow

These four files implement only **parse + validate**. Upsert is performed by `writ/cli.py` (`import-markdown`/`import-rules`) wiring `parse_*` → `validate_*` → `Neo4jConnection.create_rule`/`create_methodology_node`/`create_edge`.

- **Idempotency**: every node and edge write uses `MERGE` keyed on the primary id. Re-running ingest is safe.
- **Conflict resolution**: `SET n += $props` is last-write-wins.
- **Batching**: NONE. Every node upserted in its own session/auto-commit transaction.

## 9. Integrity checks (integrity.py)

### 9.1 `IntegrityChecker.__init__` (22-24)
Takes a raw `AsyncDriver` (NOT a `Neo4jConnection`!) and database name.
```python
def __init__(self, driver: AsyncDriver, database: str = "neo4j") -> None:
    self._driver = driver
    self._database = database
```

### 9.2 Per-check assertions and failure behaviour

| Method | Asserts | Returns | On failure |
|---|---|---|---|
| `detect_conflicts` | No two rules linked by `CONFLICTS_WITH` | list `{rule_a, rule_b}` | flips `exit_code` |
| `detect_orphans` | Every Rule has ≥1 edge | list of `rule_id` | flips `exit_code` |
| `detect_stale` | `last_validated + staleness_window >= today` | `[{rule_id, last_validated, expired_on}]` | flips `exit_code` |
| `detect_redundant` | Non-mandatory rules cosine < 0.95 on `trigger + " " + statement` | `[{rule_a, rule_b, similarity}]` | returns `[]` if < 2 rules or sentence_transformers missing; else flips `exit_code` |
| `detect_confidence_defaults` | No rule still at default `production-validated` | list of `rule_id` | advisory; not in `run_all_checks` |
| `check_query_rule_ratio(query_count)` | `query_count*10 >= rule_count` | warning dict or None | advisory |
| `check_unreviewed_count(warning_percentage=0.10, warning_floor=5)` | `unreviewed < max(warning_floor, warning_percentage*total)` | warning dict | reported but not in exit code |
| `detect_frequency_stale(window_days=90)` | Each rule has pos+neg observations | `[{rule_id, last_seen}]` | advisory |
| `detect_graduation_flags` | Rules at threshold meet ratio min | `[{rule_id, ratio, n}]` | advisory |

### 9.3 `run_all_checks(skip_redundancy=False)` (249-273)

Order: conflicts, orphans, stale, redundant, unreviewed, frequency_stale, graduation_flags.
```python
has_issues = any(findings[k] for k in ("conflicts", "orphans", "stale", "redundant"))
findings["exit_code"] = 1 if has_issues else 0
```

## 10. Adjacency cache

Lives in `writ/retrieval/traversal.py` (class `AdjacencyCache`). Touch-points:
- `db.py:get_all_edges()` and `get_all_rules()` — what cache builds from.
- `writ/retrieval/pipeline.py:591-598` instantiates and calls `await adjacency_cache.build_from_db(db)` at startup.
- **Invalidation**: NOTHING in `db.py` or `ingest.py` triggers cache rebuilds. Built once at server startup; never invalidated mid-process. Any ingest/update mutations through the running server's `Neo4jConnection` will not be reflected in `AdjacencyCache` until process restart. **GAP**: write paths do not notify any cache.

## 11. Schema-vs-ingest gaps and unwired surfaces

### 11.1 Schema models with no driver write path
- `Domain` (183): no `:Domain` MERGE in `db.py`. Domain lives only as a property on Rule/methodology nodes.
- `Evidence` (189): no `:Evidence` MERGE; `evidence` field on Rule is a string.
- `Tag` (196): never persisted. `tags` is a list[str] property on methodology nodes only.
- `AppliesTo` (242): no `APPLIES_TO` MERGE despite being in `ALLOWED_EDGE_TYPES`.
- `Abstracts` (248): model exists but actual edge created by `create_abstracts_edge`, which doesn't use the Pydantic model.
- `JustifiedBy` (253): no `JUSTIFIED_BY` MERGE despite being in `ALLOWED_EDGE_TYPES`.

### 11.2 Allowed edge types with no dedicated write method
17 in allowlist; only `ABSTRACTS` has a dedicated method. All others go through generic `create_edge`.

### 11.3 Constraint gap
`apply_constraints()` does NOT create an `Abstraction.abstraction_id` uniqueness constraint despite `create_abstraction` MERGEing on it.

### 11.4 ENF-prefix mandatory inconsistency
- `_parse_rule_block` legacy path (149): defaults `mandatory=False`.
- `_parse_node_block` Phase 1 path (300-301): defaults `mandatory = node_id.startswith("ENF-")`.

These two paths **disagree**. Legacy path was updated 2026-05-09; Phase 1 path retains old convention.

### 11.5 Evidence default disagreement (intentional)
- `Rule.evidence` defaults to `"doc:original-bible"`.
- `_MethodologyNodeBase.evidence` defaults to `"peer-reviewed"`.

## 12. Driver `coalesce` patterns

Driver consistently uses `coalesce(<prop>, 0)` for counters and `coalesce(<prop>, 'human')` for authority (db.py:394, 407, 432; integrity.py:134, 199, 222-225). Protects against rules ingested before counter fields existed.

## Files Read

| File | Lines |
|---|---|
| `writ/graph/schema.py` | 523 |
| `writ/graph/db.py` | 446 |
| `writ/graph/ingest.py` | 382 |
| `writ/graph/integrity.py` | 273 |
| `writ/graph/__init__.py` | 0 (empty) |

Total: 1624 source lines.

## Cross-References Noted

- `writ.frequency.DEFAULT_GRADUATION_RATIO_MIN`, `DEFAULT_GRADUATION_THRESHOLD`, `evaluate_graduation` — lazy import at `integrity.py:214-218`.
- `neo4j.AsyncGraphDatabase`, `AsyncDriver`, `AsyncSession` — third-party.
- `pydantic.BaseModel`, `Field`, `field_validator` — third-party.
- `yaml.safe_load`, `yaml.YAMLError` — third-party.
- `sentence_transformers.SentenceTransformer` — lazy at `integrity.py:100`.

External callers:
- `writ.config.get_neo4j_uri/_user/_password` — consumed by `cli.py` and `server.py:99`.
- `writ.retrieval.traversal.AdjacencyCache` — consumes `db.get_all_edges/_all_rules`.
- `writ.gate` — imports `Rule` from `writ.graph.schema`.
- `writ.authoring`, `writ.export`, `writ.compression.abstractions` — instantiate or accept `Neo4jConnection`.
- `writ.server` — module-level `_db: Neo4jConnection | None`.

External docs referenced:
- `docs/phase-0-schema-proposal.md` — schema.py:259-263, 327, 360-363.
- `writ-evolution.md §2.2` — ingest.py:145-148.
