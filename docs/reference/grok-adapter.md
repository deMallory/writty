# Grok Build adapter

Writ's daemon, graph, and gates stay the source of truth. This adapter translates Grok Build hook envelopes and decisions so Work mode can refuse writes on Grok the same way it does on Claude Code.

## Dialect

| Topic | Claude Code | Grok Build | Adapter |
|---|---|---|---|
| Envelope keys | `session_id`, `tool_input` | `sessionId`, `toolInput` | `writ.harness.envelope.normalize` |
| Session env | `$CLAUDE_SESSION_ID` | `$GROK_SESSION_ID` | resolver prefers Grok |
| PreToolUse deny | `hookSpecificOutput.permissionDecision` | `{"decision":"deny"}` | dual-emit both |
| Stop block | stderr + non-zero | `{"decision":"block"}` + exit 2 | dual-emit + exit 2 |
| Rule injection | stdout on `UserPromptSubmit` | observe-only (stdout discarded) | sidecar `$GROK_PLUGIN_DATA/current-rules.md` |
| Plan file | `<repo>/plan.md` | `~/.grok/sessions/<encoded-cwd>/<sid>/plan.md` | `writ grok materialize-plan` |
| Plan approval | type `approved` | TUI `a` then `/writ-approve` | `/writ-approve` mints the token |

Grok skips unknown events (`CwdChanged`). Matcher aliases map `Bash` to `run_terminal_command`; hooks.json also names Grok natives (`write`, `search_replace`, `spawn_subagent`, `exit_plan_mode`).

## Install

```bash
bash scripts/bootstrap-grok.sh
grok plugin install "$PWD" --trust
```

If Grok also scans `~/.claude/settings.json` hooks, they will double-fire. Add:

```toml
[compat.claude]
hooks = false
```

or pass `--patch-compat` to the bootstrap. Restart the Grok session and confirm `/hooks` lists `writ-pre-write-dispatch`, `auto-approve-gate`, and `writ-rag-inject`.

## Plan ownership (option 2)

Grok plan mode is the planning UX. Writ still owns the gate.

1. Agent writes the Grok session plan with Writ's four sections (`## Files`, `## Analysis`, `## Rules Applied`, `## Capabilities`).
2. Agent calls `exit_plan_mode`. You review and press `a`. That exits Grok plan mode. It does **not** open the Writ gate.
3. You type `/writ-approve`. That prompt mints the token, copies the session plan to `<repo>/plan.md`, and POSTs `/advance-phase`.
4. A second `/writ-approve` after real test files opens implementation.

Do not mint a token from `exit_plan_mode`. The agent calls that tool before you press `a`.

## Live probe (not CI)

Record the outcome of each step in this file when you run it.

1. `mode set work` (or let auto-route send a build prompt).
2. Ask Grok to `write` a dummy line in `writ/cli.py` before any approval. Expect a deny whose reason names `[ENF-GATE-PLAN]`.
3. After `a` on a Writ-shaped plan, type `/writ-approve`. Expect `writ grok materialize-plan` to copy the session plan and phase to become `testing`.
4. Confirm `/hooks` shows the Work scripts trusted.

Probe results (fill in after a live run):

- Deny visible: _not yet run_
- `/writ-approve` advanced planning to testing: _not yet run_
- `additionalContext` on PreToolUse allow reached the model: _not yet run_
