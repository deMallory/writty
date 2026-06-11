---
name: skill-to-writ
description: Convert a Claude Code skill (SKILL.md) into Writ methodology nodes (bible/ YAML-frontmatter files). Use when importing authored skills into the Writ knowledge graph, converting skill prose into enforceable rules, or expanding the bible corpus from skill sources.
argument-hint: "path to skill directory (e.g., ~/.agents/skills/gsap-core)"
---

# Skill-to-Writ translator

Claude-assisted pipeline for decomposing a Claude Code skill into typed Writ nodes. You read the skill prose, identify discrete rules, anti-patterns, techniques, playbooks, and forbidden responses, then generate valid YAML-frontmatter markdown files for human review.

## When to use

- User wants to import an authored skill into the Writ bible
- User says "convert skill to writ", "ingest skill", "translate skill to rules"
- User points at a SKILL.md and wants it decomposed into graph nodes

## Five-phase workflow

Run each phase to completion. Do not skip phases. Wait for human approval at gates.

---

### Phase 1: Intake and analysis

1. Read every file in the source skill directory (SKILL.md plus any bundled resources).
2. Produce:

**Domain inference**: Propose a `domain` value for the target `bible/<domain>/` subdirectory. Check if that directory already exists. If not, you will create it.

**Source attribution prefix**: Derive from skill name. Pattern: `"<family>:<skill-name>"`. Examples:
- `gsap-core` in `~/.agents/skills/` -> `"gsap-skills:gsap-core"`
- `editorial-grid` in a custom repo -> `"editorial-claude-skills:editorial-grid"`

**Content inventory**: Numbered list of every discrete instruction, prohibition, best practice, workflow, or failure mode found in the prose. For each item, note the candidate node type:
- **Rule**: An enforceable do-this or don't-do-that with a clear violation case
- **AntiPattern**: A named failure mode with identifiable symptoms
- **Technique**: A practice or method that demonstrates a skill
- **Playbook**: A multi-step workflow with ordered phases
- **ForbiddenResponse**: A phrase or behavior explicitly prohibited
- **Skill (Writ)**: A high-level capability or constraint (rare; only when a skill instruction is itself a meta-skill)

Present the inventory. **Gate: human approves, removes, or reclassifies items before proceeding.**

---

### Phase 2: Node plan (dry run)

For each approved inventory item, propose a node in compressed format:

```
 1. ANIM-GSAP-CAMELCASE-001 (Rule, high)
    trigger: "When writing gsap.to/from/fromTo property objects..."
    statement: "Use camelCase property names, not CSS kebab-case..."
    edges: [DEPENDS_ON ANIM-GSAP-CORE-001]

 2. ANT-ANIM-OVERWRITE-001 (AntiPattern, medium)
    trigger: "When multiple tweens target the same property..."
    statement: "Unmanaged tween overwriting: two tweens on the same property..."
    edges: [COUNTERS ANIM-GSAP-OVERWRITE-001]
```

Rules for ID construction:
- Pattern: `^[A-Z][A-Z0-9]*(-[A-Z][A-Z0-9]*)+(-\d{3}|(-[A-Z][A-Z0-9]*))$`
- Minimum two segments before numeric suffix: `ANIM-GSAP-001` valid, `ANIM-001` not
- Prefix must match node type: `SKL-`, `PBK-`, `TEC-`, `ANT-`, `FRB-`, `PHA-`
- Rules use domain prefix (no type prefix): `ANIM-GSAP-CAMELCASE-001`
- Sequence numbers are 3-digit zero-padded: `-001`, `-002`

Cap at 30 nodes per batch. If more, split into logical groups (rules, then anti-patterns, then playbooks) with a gate between each.

**Gate: human approves, drops items, renames IDs, adjusts severity, adds edges.**

---

### Phase 3: Cross-edge discovery

Before generating files, find connections to existing corpus nodes.

1. Grep `bible/` for nodes by keyword:
```bash
grep -rl "<relevant-keyword>" bible/ --include="*.md" | head -15
```

2. Read frontmatter of candidate files (trigger, statement, domain, node type).

3. Propose cross-corpus edges:
```
ANIM-GSAP-PERF-001 SUPPLEMENTS PERF-GPU-COMPOSIT-001
ANT-ANIM-JANK-001 COUNTERS PERF-REFLOW-001
```

Read at most 15 existing files. Present cross-edges as a separate list.

**Gate: human approves cross-edges.**

---

### Phase 4: File generation

Generate one YAML-frontmatter markdown file per node. Write to `bible/<domain>/`.

See [SCHEMA-REFERENCE.md](SCHEMA-REFERENCE.md) for required fields per node type.
See [EXEMPLARS.md](EXEMPLARS.md) for gold-standard format and tone.
See [EDGE-CATALOG.md](EDGE-CATALOG.md) for edge type semantics.

#### Generation rules (all node types)

- `authority: "ai-provisional"` (never `"human"` for generated nodes)
- `confidence: peer-reviewed`
- `last_validated:` today's date (YYYY-MM-DD)
- `source_attribution: "<family>:<skill>"` from Phase 1
- `source_commit: null`
- `tags:` lowercase, sorted, deduplicated
- `scope:` must match `^[a-z][a-z0-9_-]*$`
- `edges:` list of `{ target: ID, type: EDGE_TYPE }`
- Body markdown after closing `---`: short, concrete, no filler

#### Node-type-specific rules

**Rule**: Requires `violation` (concrete bad example), `pass_example` (concrete good example), `enforcement` (how to check). Synthesize from skill prose. Use code blocks for examples when the skill is technical.

**AntiPattern**: Requires `counter_nodes` (list of IDs that fix the anti-pattern). Body should have "Why this is broken" and "Counter" sections.

**Playbook**: Requires `phase_ids` (list of companion Phase IDs), `preconditions` (list of strings). Generate companion Phase files. Body lists phases and output.

**Phase**: Requires `position` (int), `name`, `description`, `parent_playbook_id`. Non-retrievable. Body is brief with advance criterion.

**Technique**: Body describes what the technique does, what it binds to, and its grid/archetype logic.

**ForbiddenResponse**: Requires `forbidden_phrases` (list), `what_to_say_instead`, `always_on: true`.

**Skill (Writ node)**: Same base fields. Only create when the source skill contains a meta-capability (rare).

---

### Phase 5: Validate and confirm

Run Pydantic validation on all generated files:

```bash
cd "$(git rev-parse --show-toplevel)"
.venv/bin/python -c "
import sys
from pathlib import Path
from writ.graph.ingest import parse_nodes_from_file, validate_parsed_node

domain = '<domain>'
errors = []
count = 0
for f in sorted(Path(f'bible/{domain}').glob('*.md')):
    try:
        nodes = parse_nodes_from_file(f)
        for n in nodes:
            validate_parsed_node(n)
            count += 1
    except Exception as e:
        errors.append((f.name, str(e)))

for name, err in errors:
    print(f'FAIL: {name}: {err}')
if not errors:
    print(f'{count} nodes valid.')
else:
    sys.exit(1)
"
```

Fix any validation failures. Re-run until clean.

Then dry-run ingest:
```bash
.venv/bin/python -m writ.graph.methodology_ingest bible/<domain> --dry-run
```

Report results. Human decides whether to commit and ingest into Neo4j.

---

## Node-type decision tree

Use this to classify each instruction from the source skill:

```
Is it a multi-step ordered workflow?
  YES -> Playbook (+ companion Phases)
  NO  ->
    Is it a named failure mode with symptoms?
      YES -> AntiPattern
      NO  ->
        Is it a phrase or behavior explicitly prohibited?
          YES -> ForbiddenResponse
          NO  ->
            Is it a practice that demonstrates how to do something?
              YES ->
                Does it have a clear violation case?
                  YES -> Rule
                  NO  -> Technique
              NO  ->
                Is it a meta-capability or constraint on the agent itself?
                  YES -> Skill (Writ node)
                  NO  -> Rule (default; most instructions are rules)
```

## Idempotency

When re-running on an already-converted skill:

1. Read existing `bible/<domain>/` files
2. Match by `source_attribution` value
3. For existing nodes: show `[EXISTS] NODE-ID -- skip or update?`
4. For new content without a corresponding node: propose as new
5. For changed source content: show proposed diff

`source_attribution` is the idempotency key.

## Quality standard

Match the editorial corpus gold standard. Every node should read as if a domain expert authored it. Rationale sections should cite the relevant tradition, not just restate the rule. Triggers should be specific enough that the retrieval pipeline can match them. Statements should be self-contained (readable without the body).
