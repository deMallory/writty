# PSR-008 post-run state

Captured by take-after-snapshot.sh.

## Friction-log deltas

| log | baseline | after | delta |
|---|---:|---:|---:|
| Test project | 475 | 541 | 66 |
| Master | 15863 | 15882 | 19 |

## Event breakdown (combined delta)

```
  hook_execution: 28
  pre_write_decision: 10
  subagent_complete: 9
  phase_transition: 5
  subagent_type_fallback: 5
  rag_query: 4
  subagent_start: 4
  cwd_changed: 4
  instructions_loaded: 3
  always_on_inject: 2
  approval_pattern_match: 2
  phase_advance: 2
  playbook_step_complete: 2
  mode_change: 1
  approval_pattern_miss: 1
  phase_transition_time: 1
  pre_compaction: 1
  post_compaction: 1

  query_source=methodology: 0
  always_on_inject:         2
  phase advances:           ['planning->testing', 'testing->implementation']
```

## Server health

- /health: 200
- /dashboard: 200

## /always-on?mode=work post-run

```
  count: 11, total_tokens: 824
  ENF: ['ENF-COMMS-001', 'ENF-PROC-DEBUG-001', 'ENF-PROC-PLAN-001', 'ENF-PROC-TDD-001', 'ENF-PROC-VERIFY-001']
  FRB: ['FRB-COMMS-001', 'FRB-COMMS-002']
  SKL: ['SKL-PROC-BRAIN-001', 'SKL-PROC-PLAN-001', 'SKL-PROC-VERIFY-001']
  PBK: ['PBK-PROC-PLAN-001']
```
