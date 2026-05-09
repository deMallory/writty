# Phase 6: Methodology absorption -- schema, ingest, content, wiring

_Master roadmap. Multi-session. Each sub-phase is independently shippable._

## Context

Phase 5 ("Measurement + graduation + trim") shipped on 2026-05-03 (commit
`1d8799b`, PSR-005b verified `53c4d03`). PSR-005b's diagnostic revealed
that two of Phase 5's six analyzers (`--skill-usage`,
`--playbook-compliance`) return empty rows because the source data does
not exist:

- The graph contains 80 `Rule` nodes and **zero** Skill / Playbook /
  Technique / Role / AntiPattern / Forbidden nodes.
- `docs/phase-0-schema-proposal.md` (signed off 2026-04-21) designs the
  10 new node types but the schema was never implemented.
- `bible/playbooks/` has only `api-endpoint.md` and `queue-feature.md`,
  both Magento technical playbooks -- no methodology playbooks.
- Nothing in production POSTs `/session/{id}/active-playbook`, so the
  `playbook_step_complete` event never fires from real workflows.

Phase 6 closes this gap. It implements the Phase 0 schema proposal,
authors the methodology content (self-contained, not a runtime
dependency on `~/workspaces/methodology` per
`feedback_methodology_absorption_no_dependency.md`), and wires the
playbook state machine to the existing `/writ-approve` advance flow.

The original 15-week absorption plan budgeted Phase 1 at 3 weeks for
this. Phase 6 is that work, executed against the now-stable Phase 5
measurement surface.

## Scope (in)

- 10 new Pydantic node models in `writ/graph/schema.py`, matching the
  contract in `docs/phase-0-schema-proposal.md`
- 7 new edge types and graph-traversal updates
- Ingest parser extension for `<!-- NODE START type=X id=Y -->` markers
  with backwards compatibility for `<!-- RULE START -->`
- Neo4j migration script (idempotent MERGE for new labels and indexes)
- Self-authored methodology content for Skills, Playbooks, Techniques,
  Roles, AntiPatterns, Forbiddens, MetaAuth nodes -- enough volume to
  exercise the analyzers
- Retrieval pipeline updates so the new node types appear in
  `rag_query` bundles
- Wiring `/active-playbook` POSTs from the existing `/writ-approve`
  advance flow so `playbook_step_complete` events accumulate
- Integration test: re-run monthly review and confirm
  `--skill-usage` and `--playbook-compliance` produce non-empty
  output

## Scope (out)

- Migrating the existing 80 Rule nodes -- they stay Rule, no
  re-classification.
- Verbatim transcription from any external content source. All
  Phase 6 methodology content is authored fresh inside Writ.
- Replacing the `Rule` node type or its retrieval path. Phase 6 adds
  alongside, never replaces.
- Reflowing Phase 5 analyzer math. The analyzers are correct; they
  just need data.

## Sub-phases

Each sub-phase is one session. Each ships behind tests. Each commits
independently. Sub-phases 6a-6d (mechanical schema/ingest/migration)
are prerequisites; 6e-6g (content authoring) consume the schema;
6h-6j (retrieval / wiring / verification) consume the content.

| ID | Title | Files touched | Acceptance | Status |
|----|-------|---------------|------------|--------|
| 6a | Pydantic node models | `writ/graph/schema.py`, `tests/test_phase6a_*` | All 10 models instantiate, validate per the proposal's required-field rules, and round-trip through `model_dump_json` | shipped (`08adb6c`) |
| 6b | Edge schema and traversal updates | `writ/graph/schema.py`, `writ/retrieval/traversal.py`, tests | 7 new edge types defined; graph-traversal queries surface them | verified-shipped (consolidated commit; existing tests `tests/test_schema_roundtrip.py::TestNewEdgeTypes` 24/24 + `tests/test_phase6bcd_verification.py::TestPhase6bEdgeContract` 11/11) |
| 6c | Ingest parser extension | `writ/graph/ingest.py`, tests | `<!-- NODE START type=Skill id=SKL-X-001 -->` markers parse to the right Pydantic model; `<!-- RULE START -->` still works | verified-shipped (consolidated commit; existing tests `tests/test_multi_node_ingest.py` 16/16 + `tests/test_phase6bcd_verification.py::TestPhase6cIngestContract` 3/3) |
| 6d | Neo4j migration | `scripts/migrate.py`, tests | Idempotent MERGE for the 10 new labels and 7 new edge types; running twice is a no-op | verified-shipped (consolidated commit; `tests/test_phase6bcd_verification.py::TestPhase6dMigrationContract` 2/2 -- script imports cleanly, audit confirms MERGE-only no `CREATE (n:Label)`. Live-Neo4j idempotency is an integration concern out of scope for this commit.) |
| 6e | Author 6 methodology playbooks | `bible/playbooks/PBK-PROC-*.md` | PBK-PROC-PLAN-001, SDD-001, DEBUG-001, TDD-001, FINISH-001, REVREQ-001 -- each ingests cleanly, has at least 3 step nodes, and references the existing Writ workflow |
| 6f | Author 6 methodology skills | `bible/skills/SKL-PROC-*.md` | SKL-PROC-BRAIN-001, VISUAL-001, EXEC-001, VERIFY-001, REVRECV-001, PARALLEL-001 |
| 6g | Author roles, antipatterns, forbiddens, techniques, meta-auth | `bible/roles/*.md`, `bible/antipatterns/*.md`, etc. | At least one node of each remaining type, ingest-clean |
| 6h | Retrieval pipeline updates | `writ/retrieval/pipeline.py`, `writ/retrieval/keyword.py`, `writ/retrieval/ranking.py`, tests | A `rag_query` for "writing a plan" returns at least one Playbook and one Skill in the bundle |
| 6i | Wire `/active-playbook` from `/writ-approve` | `templates/commands/writ-approve.md`, `.claude/hooks/*` if needed, tests | When `/writ-approve` advances phase planning -> testing, a POST to `/active-playbook` fires for `PBK-PROC-SDD-001` step `phase-a` -> `phase-b` |
| 6j | Integration verification | `docs/monthly-reviews/2026-06.md` (next-month review run), `docs/pressure-runs/2026-04-22/PSR-006/` | `--skill-usage --since 60` and `--playbook-compliance --since 30` both return non-empty rows |

## Sequencing rules

- **6a -> 6b -> 6c -> 6d** must land in order (each depends on the
  previous's contract).
- **6e/6f/6g** can interleave with 6c/6d (content can be written
  before parser exists; ingest gates it).
- **6h** depends on 6a-6g (retrieval needs both schema and content).
- **6i** depends on 6e (playbook nodes must exist).
- **6j** depends on everything; it is the green-light pass.

## Acceptance for "Phase 6 done"

All of:
- Graph contains at least one node of each new type (Skill, Playbook,
  Technique, Role, AntiPattern, Forbidden, MetaAuth, Rationalization,
  Abstraction, Fixture).
- `writ analyze-friction --skill-usage --since 60` returns non-empty
  rows in a session that exercised at least one Skill.
- `writ analyze-friction --playbook-compliance --since 30` returns
  non-empty rows after at least one `/writ-approve` advance.
- All Phase 6 tests pass; no Phase 5 regression in
  `tests/test_phase5_*.py`.
- Each sub-phase's commit message references the relevant sub-phase ID.

## Why this is independent of the broader Track B

Track B (referenced in the post-Phase-5 conversation) included
"Stage 2 architecture: LanceDB parasite" and "Section 18 open
decisions" alongside the Phase 0 schema design. Phase 6 covers
**only** the Phase 0 schema design + ingestion + wiring needed to
unblock Phase 5 measurement. The other Track B items (storage
backends, open architectural decisions) are deliberately scoped
out and can land in any order after Phase 6 ships.

## Failure modes and rollback

- **Sub-phase 6a-6d schema drift:** if any sub-phase needs to revise
  the contract, update `docs/phase-0-schema-proposal.md` first, get
  signoff, then patch the affected sub-phase. Don't drift in code.
- **Content authoring takes longer than budgeted:** ship 6a-6d as
  unblocking infrastructure; let content authoring (6e-6g) span
  multiple weeks at lower urgency. The schema is the load-bearing
  piece; content can accrue.
- **Migration error on production graph:** the migration is
  idempotent MERGE-only, so re-running is safe. If a label was
  added wrong, drop it via Cypher and re-migrate.

## What this session does

This session ships **sub-phase 6a only** (Pydantic models). The
master plan above is committed first so subsequent sessions can
resume from a stable contract. 6b onward happens in subsequent
sessions, picking up from this document.
