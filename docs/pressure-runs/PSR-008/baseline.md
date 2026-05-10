# PSR-008 baseline -- pre-run snapshot

Captured 2026-05-09 just before the run.

## Friction logs

| log | line count |
|---|---:|
| Master (`~/.claude/skills/writ/workflow-friction.log`) | 15863 |
| Test project (`~/workspaces/MageContextABTest/workflow-friction.log`) | 475 |

## Neo4j state

| label | count |
|---|---:|
| Rule | 90 |
| Skill | 7 |
| Playbook | 7 |
| Technique | 4 |
| AntiPattern | 10 |
| ForbiddenResponse | 2 |

## Server

`/health` -> `{"status":"healthy","rule_count":90,"mandatory_count":41,"index_state":"warm","startup_time":"2026-05-09T19:32:48"}`

## Commits under test (this session, all on `main`, none pushed)

```
8a26868 End-of-suite Neo4j restoration: drop count==0 gate, shell to migrate.py
f636471 Always-on bundle: surface methodology nodes + tag selective candidates
6436bc5 Phase-machine deeper fix: ExitPlanMode resets task phase to planning
2d7c028 Followup: test_retrieval pipeline_db teardown restores Neo4j state
c219397 Followup: redirect remaining cache-write + emit blocks to WRIT_HOOK_LOG; raise pipeline-latency budgets for post-methodology corpus
33e0adc Followup: /advance-phase rejects when current_phase=complete
61758d6 Phase 6j unblock + hook stderr surfacing + always-on budget tracking
```

## What this PSR validates

Each new behavior shipped this session, in one fresh-session run:

1. **Phase 6j skill-usage path** -- methodology companion `rag_query` events emit with SKL- IDs; `--skill-usage --since 60` returns non-empty.
2. **Always-on extension** -- the bundle injected on every UserPromptSubmit contains SKL/PBK nodes (visible in the model's context as `[SKL-PROC-PLAN-001] WHEN: ...`).
3. **Always-on token tracking** -- `always_on_inject` friction events appear with non-zero tokens.
4. **ExitPlanMode resets phase** -- a fresh /plan -> approved cycle does not silently consume implementation->complete from a stale prior task.
5. **Hook stderr surfacing** -- if any `_writ_session update` mutation fails during the run, a line lands in `${WRIT_HOOK_LOG:-/tmp/writ-hooks.log}` rather than being silently dropped.
6. **Post-compact discipline** (carryover from PSR-007) -- after `/compact`, completion claims require fresh verification.
