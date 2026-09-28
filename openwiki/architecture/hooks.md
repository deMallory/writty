---
type: Guide
title: "Hooks"
description: What Writty does on each Claude Code event, which hooks can block, the patterns every hook follows, and how to add one.
---

# Hooks

Hooks are how Writty acts at all. Claude Code runs a shell command on each lifecycle event; Writty registers bash scripts under `hooks/scripts/` for the events in the table below, all in one file, `hooks/hooks.json`. The script-by-script matrix is generated from that file: `docs/reference/hooks.md`. Blocking semantics per hook: `HANDBOOK.md` section 14.

## What happens on each event

| Event | What Writty does there | Can block |
|---|---|---|
| `SessionStart` | Starts the daemon if nothing answers and bootstraps the session (`session-start-bootstrap.sh`) | No |
| `UserPromptSubmit` | Mints a manual-testing grant from the user's words (`writ-manual-test-grant.sh`), scans for an approval and advances a pending gate (`auto-approve-gate.sh`), sets a mode when the prompt makes it obvious, then injects the rules for this prompt in one daemon call (`writ-rag-inject.sh`) | No |
| `PreToolUse` | The gates. Source writes checked against the mode and phase (`writ-pre-write-dispatch.sh`), writes hidden in Bash commands (`writ-bash-write-gate.sh`), reads of secret files (`writ-read-credential-gate.sh`), writes to the session store (`writ-state-write-gate.sh`), the test-first check (`validate-test-file.sh`), `plan.md` at plan-mode exit (`validate-exit-plan.sh`), sub-agent dispatch (`writ-dispatch-discipline.sh`, `writ-agent-hotswap.sh`, `writ-sdd-review-order.sh`), and more | Yes |
| `PostToolUse` | Rules for the file just read or written (`writ-posttool-rag.sh`), post-write validators, marking a written test for the end-of-turn run (`writ-mark-pending-test.sh`), the self-review prompt after a plan or test file (`writ-quality-judge.sh`), secret redaction in Bash output (`writ-output-rewrite.sh`), the auto-memory mirror (`writ-memory-capture.sh`) | No |
| `PostToolUseFailure` | Logs a failed Bash command to the friction log (`writ-bash-failure.sh`) | No |
| `Stop` | Runs the tests marked this turn, and refuses to end the turn on a failing test in the implementation phase, an unresolved violation in Work mode, an unverified low self-review score, or an em dash, en dash or ` -- ` in the reply. Logs friction (`friction-logger.sh`) | Yes |
| `SubagentStart` | Gives each sub-agent its own session cache seeded from the parent's mode and phase (`writ-subagent-start.sh`) | No |
| `SubagentStop` | Records a reviewer's verdict straight from the payload, which is what holds a commit after a CRITICAL review (`writ-subagent-stop.sh`) | No |
| `PreCompact` | Drops the full rule objects from the session cache before compaction, keeping their ids (`writ-precompact.sh`) | No |
| `PostCompact` | Resets post-compaction state and queues a re-orientation for the next prompt (`writ-postcompact.sh`) | No |
| `CwdChanged` | Detects the project domain in the new directory for the next rule query (`writ-cwd-changed.sh`) | No |
| `SessionEnd` | Rule feedback, coverage, and a pressure audit of the session (`writ-session-end.sh`, `writ-pressure-audit.sh`) | No |

`writ-blackbox-capture.sh` also sits on several of these events. It logs the raw event payload when capture is switched on, emits nothing and never blocks.

The typed-approval path, from prompt to phase advance, is drawn in [Work gates and approvals](../workflows/work-gates.md). The dispatch hooks are covered in [Sub-agents](../workflows/sub-agents.md).

## Patterns every hook follows

- **Daemon first, then fall back.** A hook calls the daemon over HTTP with a timeout of a few hundred milliseconds, and runs `bin/lib/writ-session.py` when the daemon does not answer (`_writ_session` in `bin/lib/common.sh`).
- **Fail open.** A hook that errors or cannot reach anything lets the tool call through and logs the failure. The deliberate exceptions fail closed: secret-path denial, the research triangulation gate, and token validation on a phase advance.
- **One parse per hook.** `load_hook_env` in `bin/lib/common.sh` reads the event payload once.
- **Every exit is logged.** `hook_instrument` in `bin/lib/common.sh` sets the exit trap that records each run. A hook adds its own cleanup with `writ_on_exit`, never a second `trap ... EXIT`, which would silently replace the first.
- **Output goes where the model can see it.** Plain stdout reaches the model only on `UserPromptSubmit`, `UserPromptExpansion` and `SessionStart`. Tool hooks use `additionalContext`. `PreCompact` and `PostCompact` have no channel to the model at all. The table is `writ/shared/delivery.py`, and `writ/hooks_lint.py` flags a hook that writes where nobody reads.
- **Blocking a Stop.** A blocking Stop hook writes to stderr and exits non-zero, and checks `stop_hook_active` first. A Stop hook's `additionalContext` would restart the turn and loop.

## Adding or changing a hook

1. Write the script under `hooks/scripts/`. Source `bin/lib/common.sh` and call `hook_instrument` right after.
2. Register it in `hooks/hooks.json`.
3. Regenerate the two files derived from `hooks/hooks.json`: `make docs` for `docs/reference/hooks.md`, and `python3 scripts/render-settings-template.py` for `templates/settings.json`. Both take `--check` (`make docs-check` for the first), and `tests/test_settings_template_sync.py` fails on a stale template.
4. Start a new Claude Code session. A change to `hooks/hooks.json` is read at session start; a script edit applies on its next run.

On a plugin install, Claude Code runs the scripts from the plugin cache, not from this repo. A repo edit reaches a session only after the plugin is updated; the integrations section covers the update.
