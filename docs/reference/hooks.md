<!-- GENERATED FILE - do not edit. Source: hooks/hooks.json. Regenerate with `make docs` (scripts/render-docs.py). -->


# Hook registration matrix

50 registrations across 12 events wiring 46 scripts under `hooks/scripts/`, generated from `hooks/hooks.json` (the single source; `templates/settings.json` is rendered from the same file). `writ-statusline.sh` is wired through the settings `statusLine` channel, not a hook event. Behavior and blocking semantics: `HANDBOOK.md` section 14.

## SessionStart

| Matcher | Script |
|---|---|
| `(all)` | `writ-blackbox-capture.sh` |
| `(all)` | `session-start-bootstrap.sh` |

## UserPromptSubmit

| Matcher | Script |
|---|---|
| `(all)` | `writ-manual-test-grant.sh` |
| `(all)` | `auto-approve-gate.sh` |
| `(all)` | `writ-rag-inject.sh` |

## SubagentStart

| Matcher | Script |
|---|---|
| `(all)` | `writ-subagent-start.sh` |

## SubagentStop

| Matcher | Script |
|---|---|
| `(all)` | `writ-blackbox-capture.sh` |
| `(all)` | `writ-subagent-stop.sh` |

## Stop

| Matcher | Script |
|---|---|
| `(all)` | `friction-logger.sh` |
| `(all)` | `enforce-violations.sh` |
| `(all)` | `writ-verify-before-claim.sh` |
| `(all)` | `writ-run-pending-tests.sh` |
| `(all)` | `writ-comms-output-gate.sh` |

## PostToolUseFailure

| Matcher | Script |
|---|---|
| `.*` | `writ-blackbox-capture.sh` |
| `Bash|run_terminal_command` | `writ-bash-failure.sh` |

## PreCompact

| Matcher | Script |
|---|---|
| `(all)` | `writ-precompact.sh` |

## PostCompact

| Matcher | Script |
|---|---|
| `(all)` | `writ-blackbox-capture.sh` |
| `(all)` | `writ-postcompact.sh` |

## SessionEnd

| Matcher | Script |
|---|---|
| `(all)` | `writ-session-end.sh` |
| `(all)` | `writ-pressure-audit.sh` |

## CwdChanged

| Matcher | Script |
|---|---|
| `(all)` | `writ-blackbox-capture.sh` |
| `(all)` | `writ-cwd-changed.sh` |

## PreToolUse

| Matcher | Script |
|---|---|
| `Read|Grep|Bash|read_file|grep|run_terminal_command` | `writ-read-credential-gate.sh` |
| `ExitPlanMode|exit_plan_mode` | `validate-exit-plan.sh` |
| `Read|read_file` | `writ-read-junk-gate.sh` |
| `Read|read_file` | `writ-read-rag.sh` |
| `Grep|Read|Glob|grep|read_file` | `writ-debug-code-gate.sh` |
| `Write|Edit|NotebookEdit|write|search_replace` | `writ-state-write-gate.sh` |
| `Write|Edit|NotebookEdit|write|search_replace` | `writ-pre-write-dispatch.sh` |
| `Write|Edit|write|search_replace` | `pre-validate-file.sh` |
| `Task|Agent|spawn_subagent` | `writ-dispatch-discipline.sh` |
| `Task|spawn_subagent` | `writ-agent-hotswap.sh` |
| `Task|spawn_subagent` | `writ-sdd-review-order.sh` |
| `Bash|run_terminal_command` | `writ-worktree-safety.sh` |
| `Bash|run_terminal_command` | `writ-bash-write-gate.sh` |
| `Write|write` | `validate-test-file.sh` |
| `Write|write` | `validate-design-doc.sh` |
| `Write|write` | `writ-memory-policy-guard.sh` |

## PostToolUse

| Matcher | Script |
|---|---|
| `Bash|run_terminal_command` | `inject-tier-workflow.sh` |
| `Bash|run_terminal_command` | `writ-output-rewrite.sh` |
| `WebFetch|WebSearch|web_search|web_fetch` | `writ-web-capture.sh` |
| `Write|Edit|write|search_replace` | `validate-file.sh` |
| `Write|Edit|write|search_replace` | `writ-output-compress.sh` |
| `Write|Edit|write|search_replace` | `writ-bible-authoring-push.sh` |
| `Write|Edit|write|search_replace` | `validate-handoff.sh` |
| `Write|Edit|write|search_replace` | `validate-rules.sh` |
| `Write|Edit|NotebookEdit|write|search_replace` | `writ-posttool-rag.sh` |
| `Write|write` | `writ-quality-judge.sh` |
| `Write|Edit|write|search_replace` | `writ-mark-pending-test.sh` |
| `Write|Edit|write|search_replace` | `writ-memory-capture.sh` |
