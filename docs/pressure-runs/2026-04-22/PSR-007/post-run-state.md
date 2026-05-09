# PSR-007 post-run state

Captured by take-after-snapshot.sh.

## Test project friction log delta (load-bearing)

Path: ~/workspaces/MageContextABTest/workflow-friction.log

- Baseline: 379 lines
- Post-run: 464 lines
- Delta: 85 new events
- Captured to: test-project-friction.jsonl (also aliased as friction.jsonl)

## Master log delta (orchestrator-side noise)

Path: ~/.claude/skills/writ/workflow-friction.log

- Baseline: 9718 lines
- Post-run: 9735 lines
- Delta: 17 new events
- Captured to: master-friction.jsonl

## Event-type breakdown (test-project delta)

  hook_execution: 34
  pre_write_decision: 12
  subagent_type_fallback: 7
  subagent_complete: 7
  instructions_loaded: 6
  rag_query: 5
  cwd_changed: 4
  approval_pattern_match: 3
  mode_change: 2
  phase_transition: 2
  exitplanmode_denial: 1
  exitplanmode_allow: 1
  approval_pattern_miss: 1

## Daemon state

- GET /health: 200
- GET /dashboard: 200

## Phase 6 final-verification status

Awaiting transcript paste + grading in analysis.md.
