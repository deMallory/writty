---
type: Guide
title: "Modes"
description: The five session modes, how a session gets one, and what each mode blocks.
---

# Modes

A mode says what kind of work a session is doing, and it decides which gates apply. There are five. Only `work` holds source writes behind your approvals; `debug` holds them behind a written root cause. The modes are one config table, `MODE_CONFIG` in `writ/session/mode_engine.py`.

## The five modes

| Mode | Use it to | What it blocks |
|---|---|---|
| `conversation` | discuss, brainstorm, ask | nothing |
| `review` | check code against the rules | nothing |
| `investigate` | audit, explore, research | advisory checks only, except that web research cannot conclude on a single source |
| `debug` | chase one failure | reading source before the evidence is written down, editing source before the root cause is |
| `work` | build or change code | source writes until you approve a plan, then its tests. See [Work gates and approvals](work-gates.md) |

With no mode set, Writty denies every write except `plan.md` and `capabilities.md`, and the prompt hook asks you to pick one.

## How a session gets a mode

- **Auto-route.** When no mode is set, a build request sets `work` and an audit, explore or research request sets `investigate`. Anything else gets the prompt to pick a mode. The classifier, `bin/lib/writ_mode_hint.py`, prefers asking to guessing, and it never replaces a mode already set.
- **`mode set <mode>`** starts fresh: the mode's first phase, no approvals, no denial counts. Use it for each new task. It clears this session's approvals only, never another session's.
- **`mode switch <mode>`** keeps paused work. Leave `work` for `debug` in the middle of a task, come back, and the phase and approvals are restored.

Both are subcommands of `bin/lib/writ-session.py`. When a mode is missing, the prompt hook prints the full command with your install path and session id.

## Debug

Two gates stop a fix from being a guess. Both read `debug.md` at the project root.

- Reading or searching source (Read, Grep, Glob) waits until `debug.md` has real `## Evidence` and `## Narrowing` sections. Logs, docs and Bash stay open, because they are how evidence gets gathered. This gate lets everything through if it hits an internal error.
- Editing source waits until `## Root cause` is filled in.

In debug mode, every Bash output is recorded as evidence. Switching from `debug` to `work` copies the root cause into `plan.md` as `## Root Cause Evidence`, so the diagnosis starts the plan.

## Investigate

One engine, three lenses. The lens decides what counts as evidence and how strict the check is.

| Lens | Evidence | Check before a conclusion |
|---|---|---|
| code | files read and searched | advisory: warns when nothing in scope was examined |
| web | pages captured from WebFetch and WebSearch | hard: sources from two independent domains |
| runtime | command output | the debug gates above |

Coverage is measured against a scope you freeze once, so narrowing the scope later cannot inflate it. Reports say what was examined, never that an investigation is complete.

## Session rotation

When Claude Code gives a conversation a new session id, the mode carries over, within the same project. Approvals do not: the new session approves again. Approvals also end with the session that earned them.

## Where to read more

- `HANDBOOK.md` sections 3 to 5: modes, investigate, debug.
- `docs/reference/session-and-gates.md` sections 2, 3 and 6: the exact contract.
