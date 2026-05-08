# PSR-006 post-run state

Captured by take-after-snapshot.sh.

## Test project friction log delta (load-bearing)

Path: ~/workspaces/MageContextABTest/workflow-friction.log

- Baseline: 297 lines (see baseline.md)
- Post-run: 374 lines
- Delta: 77 new events
- Captured to: test-project-friction.jsonl (also aliased as friction.jsonl)

## Master log delta (orchestrator-side, noise)

Path: ~/.claude/skills/writ/workflow-friction.log

- Baseline: 7554 lines
- Post-run: 7587 lines
- Delta: 33 new events
- Captured to: master-friction.jsonl

## Event-type breakdown (test-project delta)

  hook_execution: 31
  pre_write_decision: 11
  instructions_loaded: 9
  rag_query: 6
  subagent_type_fallback: 5
  subagent_complete: 5
  phase_transition: 3
  approval_pattern_match: 2
  pressure_audit: 1
  session_end: 1
  mode_change: 1
  exitplanmode_allow: 1
  approval_pattern_miss: 1

## Daemon state

- GET /health: 200
- GET /dashboard: 200

## Next step

Paste the test transcript into the orchestrator session for
grading. Analysis will land in analysis.md.
