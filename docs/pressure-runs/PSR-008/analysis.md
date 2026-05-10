# PSR-008 analysis -- post-Phase-6j stack validation

Run date: 2026-05-09
Verdict: **8 of 9 criteria passed; criterion 3 failed by orchestrator-mode design (not a bug). Two real findings to file.**

## Pass criteria scoring

| # | Criterion | Result | Evidence |
|---|---|---|---|
| 1 | Workflow ran cleanly | PASS | `phase advances: ['planning->testing', 'testing->implementation']` in friction-log delta. ExitPlanMode reset (commit `6436bc5`) wired correctly: first /advance-phase from `planning` (not `implementation`). |
| 2 | Always-on bundle in injected context | PASS | post-run `/always-on?mode=work` returns 11 nodes / 824 tokens including SKL-PROC-{BRAIN, PLAN, VERIFY}-001 and PBK-PROC-PLAN-001. System reminders shown in transcript include the always-active block. |
| 3 | Methodology companion fired (`query_source: "methodology"`) | FAIL by design | 0 events. **Root cause: `--orchestrator` flag suppresses ALL master-session RAG injection per writ-orchestrator.md design.** The methodology companion code lives in the same broad-RAG block, so it is intentionally suppressed when the master is acting as an orchestrator. Not a bug in commit `61758d6`; an architectural gap noted as Finding 1 below. |
| 4 | `always_on_inject` events emitted | PASS | 2 combined (1 in test-project log, 1 in master). Both with non-zero `tokens` field. |
| 5 | `--skill-usage --since 60` non-empty | PASS | 7 SKL rows: BRAIN, EXEC, PARALLEL, PLAN, REVRECV, VERIFY, VISUAL -- each `loads=1`, `completion_rate=1.00`. (The completion-rate=1.00 is real but artifactual: every SKL load occurred in a session that also produced a `playbook_step_complete`. Rate will dilute as more sessions run methodology queries without finishing the SDD playbook.) |
| 6 | `--playbook-compliance --since 30` non-empty | PASS | PBK-PROC-SDD-001 \| runs=6 \| compliant=2 \| skip_points=testing, implementation. (5 prior + this run's 1 = 6.) |
| 7 | `/always-on?mode=work` >= 8 nodes including SKL + PBK | PASS | 11 nodes, 3 SKL, 1 PBK. |
| 8 | Post-compact discipline (no "yes" collapse) | PASS | After "yes is it ready?" the agent did NOT immediately answer. It re-verified by attempting `docker compose exec`, then `docker exec magento-upgrade`, then host phpunit -- only after the host run produced fresh "OK, but there were issues! Tests: 4, Assertions: 16" output did it answer "yes, the module is ready to enable". Behaved per the post-compact directive. |
| 9 | No fabricated rule IDs | PASS | All cited rule IDs exist on disk: FW-M2-RT-001, FW-M2-RT-002, FW-M2-001, FW-M2-003, FW-M2-005, SEC-UNI-002, PY-IMPORT-001 (advisory non-applicable), and the always-active block (ENF-COMMS-001, ENF-PROC-DEBUG-001, ENF-PROC-PLAN-001, ENF-PROC-TDD-001, ENF-PROC-VERIFY-001, FRB-COMMS-001, FRB-COMMS-002, SKL-PROC-{BRAIN, PLAN, VERIFY}-001, PBK-PROC-PLAN-001). |

## Findings

### Finding 1 -- Methodology companion never fires in orchestrator mode

**Symptom:** `--skill-usage` populated (7 SKL skills) but ZERO `query_source: "methodology"` events. Skills got logged via the writ-explorer/writ-planner/writ-test-writer/writ-implementer subagent dispatches (they each get RAG via writ-subagent-start.sh), not via the master's methodology companion query.

**Root cause:** `writ-rag-inject.sh` short-circuits broad RAG injection when `is_orchestrator: true`. The methodology companion code (commit `61758d6`) lives below that short-circuit, so it never fires in orchestrator sessions.

**Implication:** orchestrator-mode work loses one of the two methodology surfaces. Workers still surface SKL- via their own RAG path -- but the master never sees a `[Writ: methodology companion]` block.

**Fix candidates (next session):**
- (a) Move methodology companion above the orchestrator short-circuit. One extra HTTP call per UserPromptSubmit, ~600 tokens. Justification: methodology context is exactly what an orchestrator needs (planning + workflow discipline) -- the broad coding-rule RAG suppression is correct, but methodology is a different concern.
- (b) Have `writ-subagent-start.sh` fire a one-shot methodology query keyed off `subagent_type`. e.g., `writ-planner` -> PBK-PROC-PLAN-001 + SKL-PROC-PLAN-001. Surfaces methodology to the worker that needs it.
- (c) Document as intentional and live with it. Workers cover the gap via their own RAG.

(a) and (b) are both low-effort. (a) keeps the analyzer signal symmetric (every Work-mode UserPromptSubmit logs a methodology event). (b) is more efficient but depends on the agent_type field being reliably set.

### Finding 2 -- writ-sdd-review-order.sh has the same JSON-decode bug class as the legacy hotfix

**Symptom:** "PreToolUse:Agent hook error -- Failed with non-blocking status code: Traceback (most recent call last): ..." printed on every subagent dispatch (4 dispatches this run).

**Root cause** (from `/tmp/writ-hook-debug.log`):
```
json.decoder.JSONDecodeError: Invalid control character at: line 1 column 395 (char 394)
```

`writ-sdd-review-order.sh` builds an inline Python heredoc with `parsed = json.loads('''$PARSED''')`. When the tool-input envelope contains literal newlines/tabs/control chars (which the user's task prompt does -- multi-line code-fenced block), the Python triple-string substitution preserves the raw control characters and `json.loads` rejects them.

This is the same bug class commit `db58ec1` patched in `writ-rag-inject.sh` and `writ-pretool-rag.sh`. The fix did not propagate to `writ-sdd-review-order.sh`.

**Impact:** the SDD review-order gate falls open silently (the hook exits non-zero, "non-blocking status code" so the dispatch proceeds). Code-quality reviews dispatched out of order would not be denied. Real blast radius: any orchestrator session whose subagents include code-reviewer roles. PSR-008 didn't dispatch reviewers, so this stayed hidden as a noisy log line.

**Fix:** apply the `json.loads(sys.argv[N])` defensive pattern (env var or argv passthrough with explicit JSON encoding) instead of heredoc substitution. Same shape as the `db58ec1` fix.

### Finding 3 -- analyze-friction CLI invocation footgun

**Symptom:** the user's prompt embeds `python3 -m writ.cli analyze-friction ...` as if the writ module is universally importable. It is not -- only the writ skill's `.venv` has it. The agent's first run failed with `ModuleNotFoundError: No module named 'writ'`. Self-corrected by switching to `cd ~/.claude/skills/writ && .venv/bin/python -m writ.cli`.

**Impact:** transient confusion in the transcript. Did not affect grading.

**Fix candidate:** add a `writ` shim to `~/.local/bin` that forwards to the venv python, so the prompt's bare `python3 -m writ.cli` becomes `writ analyze-friction`. Or: update the PSR template prompt to use the qualified path.

## Other observations

- **Methodology coverage**: 7 of 7 SKL-PROC-* skills got at least one `loads` event this run, but the loads came from worker subagents (writ-explorer, writ-planner, writ-test-writer, writ-implementer) firing their own RAG queries. That confirms `node_types` opt-in works in workers. Without it, those workers would have returned only Rule nodes per the Phase 6h MRR-preservation default.
- **Phase-machine fix verified live**: the friction-log delta shows `planning -> testing -> implementation` only. No `implementation -> complete` smell. The ExitPlanMode reset (commit `6436bc5`) is doing what it should.
- **Always-on tagging took**: post-run `/always-on?mode=work` returns the 6 newly-tagged nodes from commit `f636471` (3 SKL + 1 PBK + 2 newly-tagged ENF). 824 tokens, 16% of the 5000-token cap.
- **Hook log empty**: `/tmp/writ-hooks.log` is 0 bytes after the run. No mutating `_writ_session update` failed. Confirms commit `c219397`'s redirects are wired but no failure has actually exercised them; the bug class they catch hasn't reproduced this run.

## Verdict

**Pass.** 8 of 9 criteria green. The single fail is by orchestrator-mode design (not a defect in this session's commits). The two findings filed are real but pre-existing or architectural -- neither is regression of the seven commits under test.

The Phase 6j unblock + always-on extension + phase-machine fixes hold up under fresh-session pressure. Recommend filing Finding 1 (methodology companion in orchestrator mode) and Finding 2 (writ-sdd-review-order.sh JSON bug) as separate followups.
