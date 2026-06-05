# Schema reference

Condensed from `writ/graph/schema.py`. Use this to generate valid node files.

## ID pattern

All node IDs must match: `^[A-Z][A-Z0-9]*(-[A-Z][A-Z0-9]*)+(-\d{3}|(-[A-Z][A-Z0-9]*))$`

Examples: `ANIM-GSAP-CORE-001`, `ANT-EDIT-SYMMETRY-001`, `SKL-PROC-BRAIN-001`, `ENF-GATE-FINAL`

## Enums

**Severity**: `critical`, `high`, `medium`, `low`
**Confidence**: `battle-tested`, `production-validated`, `peer-reviewed`, `speculative`
**Authority**: `human`, `ai-provisional`, `ai-promoted` (use `ai-provisional` for generated nodes)

## Scope

Must match `^[a-z][a-z0-9_-]*$`. Examples: `layout`, `component`, `task`, `session`, `design-phase`

## Base fields (all methodology nodes)

| Field | Type | Required | Default |
|-------|------|----------|---------|
| `node_type` | string | yes | -- |
| `domain` | string | yes | -- |
| `scope` | string | yes | -- |
| `trigger` | string | yes | -- |
| `statement` | string | yes | -- |
| `rationale` | string | yes | -- |
| `tags` | list[string] | no | [] |
| `confidence` | enum | no | `production-validated` |
| `authority` | string | no | `human` |
| `last_validated` | date (YYYY-MM-DD) | yes | -- |
| `staleness_window` | int | no | 365 |
| `evidence` | string | no | `doc:original-bible` |
| `source_attribution` | string | no | null |
| `source_commit` | string | no | null |
| `body` | string | no | "" (parsed from markdown body) |

## Per-type fields

### Rule

ID field: `rule_id` (no type prefix; uses domain prefix like `ANIM-GSAP-*`, `EDIT-GRID-*`)

| Field | Type | Required | Default |
|-------|------|----------|---------|
| `rule_id` | string | yes | -- |
| `violation` | string | yes | -- |
| `pass_example` | string | yes | -- |
| `enforcement` | string | yes | -- |
| `mandatory` | bool | no | false |
| `always_on` | bool | no | false |
| `rationalization_counters` | list[{thought, counter}] | no | [] |
| `red_flag_thoughts` | list[string] | no | [] |
| `mechanical_enforcement_path` | string | no | null |

### Skill (Writ node type, prefix: `SKL-`)

ID field: `skill_id`

No extra fields beyond base. ID must start with `SKL-`.

### Playbook (prefix: `PBK-`)

ID field: `playbook_id`

| Field | Type | Required | Default |
|-------|------|----------|---------|
| `playbook_id` | string | yes | -- |
| `phase_ids` | list[string] | yes | -- |
| `preconditions` | list[string] | no | [] |
| `dispatched_roles` | list[string] | no | [] |

### Technique (prefix: `TEC-`)

ID field: `technique_id`

No extra fields beyond base.

### AntiPattern (prefix: `ANT-`)

ID field: `antipattern_id`

| Field | Type | Required | Default |
|-------|------|----------|---------|
| `antipattern_id` | string | yes | -- |
| `counter_nodes` | list[string] | yes | -- |
| `named_in` | string | no | null |

### ForbiddenResponse (prefix: `FRB-`)

ID field: `forbidden_id`

| Field | Type | Required | Default |
|-------|------|----------|---------|
| `forbidden_id` | string | yes | -- |
| `forbidden_phrases` | list[string] | yes | -- |
| `what_to_say_instead` | string | yes | -- |
| `always_on` | bool | no | true |

### Phase (prefix: `PHA-`, non-retrievable)

ID field: `phase_id`

| Field | Type | Required | Default |
|-------|------|----------|---------|
| `phase_id` | string | yes | -- |
| `position` | int | yes | -- |
| `name` | string | yes | -- |
| `description` | string | yes | -- |
| `parent_playbook_id` | string | yes | -- |

Severity is optional for non-retrievable types.

### Rationalization (prefix: `RAT-`, non-retrievable)

ID field: `rationalization_id`

| Field | Type | Required | Default |
|-------|------|----------|---------|
| `rationalization_id` | string | yes | -- |
| `thought` | string | yes | -- |
| `counter` | string | yes | -- |
| `attached_to` | string | yes | -- |

### PressureScenario (prefix: `PSC-`, non-retrievable)

ID field: `scenario_id`

| Field | Type | Required | Default |
|-------|------|----------|---------|
| `scenario_id` | string | yes | -- |
| `prompt` | string | yes | -- |
| `expected_compliance` | string | yes | -- |
| `failure_patterns` | list[string] | yes | -- |
| `rule_under_test` | string | yes | -- |
| `difficulty` | string | yes | -- |

### WorkedExample (prefix: `EXM-`, non-retrievable)

ID field: `example_id`

| Field | Type | Required | Default |
|-------|------|----------|---------|
| `example_id` | string | yes | -- |
| `title` | string | yes | -- |
| `before` | string | yes | -- |
| `applied_skill` | string | yes | -- |
| `result` | string | yes | -- |
| `linked_skill` | string | yes | -- |

### SubagentRole (prefix: `ROL-`, non-retrievable)

ID field: `role_id`

| Field | Type | Required | Default |
|-------|------|----------|---------|
| `role_id` | string | yes | -- |
| `name` | string | yes | -- |
| `prompt_template` | string | yes | -- |
| `dispatched_by` | list[string] | no | [] |
| `model_preference` | string | no | null |
| `tools` | string | no | null |
| `description` | string | no | null |

## Edge declaration

In the YAML frontmatter `edges` field:

```yaml
edges:
  - { target: NODE-ID, type: EDGE_TYPE }
  - { target: NODE-ID, type: EDGE_TYPE }
```

Valid edge types: `DEPENDS_ON`, `PRECEDES`, `CONFLICTS_WITH`, `SUPPLEMENTS`, `SUPERSEDES`, `RELATED_TO`, `TEACHES`, `COUNTERS`, `DEMONSTRATES`, `DISPATCHES`, `GATES`, `PRESSURE_TESTS`, `CONTAINS`, `ATTACHED_TO`
