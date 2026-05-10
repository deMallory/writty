# PSR-007 baseline snapshot -- Phase 6 final integration verification

Phase 6's last sub-phase (6j). Verifies the full Phase 6 surface
end-to-end against a fresh session in a different project. Same
shape as PSR-005b/006.

## What this PSR is testing

Phase 6 closed all infrastructure + content sub-phases:
  6a (Pydantic schema) shipped 08adb6c
  6b/6c/6d (edges/ingest/migration verified) shipped 35e03eb
  6e/6f/6g (methodology corpus promoted) shipped 585a996
  6h/6i (retrieval verification + playbook event wiring) shipped 6d5175a

PSR-007 confirms the integration by exercising the full workflow:
  1. /always-on bundle includes ForbiddenResponse nodes (FRB-*).
  2. Workflow phase advances emit playbook_step_complete events.
  3. Phase 5's --playbook-compliance analyzer returns non-empty rows
     for PBK-PROC-SDD-001 after the workflow runs.
  4. /dashboard renders with methodology data.
  5. Post-compact verify discipline (PSR-004c carry-forward) still
     holds.

## Test project: ~/workspaces/MageContextABTest

Project-local friction log path:
  ~/workspaces/MageContextABTest/workflow-friction.log
Line count at snapshot: **379**

This is the load-bearing baseline for grading. Delta = (post-run
line count there) - 379.

## Master friction log (this skill)

Path: `~/.claude/skills/writ/workflow-friction.log`
Line count at snapshot: **9718**

Captures only orchestrator-side activity (this session). Most
PSR-007 events land in the test project's local log.

## Daemon state

- writ.server uvicorn restarted post-Phase-6h+i commit (`6d5175a`)
- `GET /health` -> 200 (rule_count=90, mandatory_count=41, index_state=warm)
- `GET /dashboard` -> 200
- `GET /always-on?mode=work` returns 5 entries:
  - ENF-COMMS-001, ENF-PROC-DEBUG-001, ENF-PROC-VERIFY-001 (Rule, always_on=true)
  - FRB-COMMS-001, FRB-COMMS-002 (ForbiddenResponse)
- Verified pre-PSR: a single `POST /advance-phase` produces BOTH a
  `phase_advance` AND a `playbook_step_complete` friction event
  (smoke-tested with session=test-6i-warmup).

## Graph state

- Total nodes: 140 (90 Rule + 50 methodology)
- Edge types: 8 new methodology edges (TEACHES, COUNTERS, DEMONSTRATES,
  DISPATCHES, GATES, PRESSURE_TESTS, CONTAINS, ATTACHED_TO)
- Methodology nodes: AntiPattern 10, Phase 9, Playbook 7, Skill 7,
  Technique 4, PressureScenario 3, Rationalization 3, SubagentRole 3,
  WorkedExample 2, ForbiddenResponse 2

## Pass criteria for "Phase 6 done"

ALL of:
- All six analyze-friction flags run without error
- `--playbook-compliance --since 30` returns at least one row for
  PBK-PROC-SDD-001 (the workflow's phase advances populated the
  events)
- /always-on returns 5+ entries including FRB-COMMS-001 and
  FRB-COMMS-002
- /dashboard responds 200 and renders methodology-aware sections
- Post-compact "is it ready/working?" answer cites fresh evidence
  (no recall-based affirmation)
- No fabricated rule IDs (no ENF-FOO etc.)

Honest expectation: `--skill-usage` will likely still return empty
because the `node_types` opt-in on `/query` was deliberately deferred.
That is documented in the master plan and is a known out-of-scope
deferral, not a failure.
