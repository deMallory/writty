---
type: Guide
title: "Quickstart"
description: What Writty does and does not do, how to install it, and a first gated task from plan to code.
---

# Quickstart

Writty makes Claude Code ask before it builds. In Work mode the AI cannot write source code until you approve its plan, then its tests. On every prompt it also receives the few engineering rules that fit the task. Claude proposes, Writty checks, you decide.

## What it does and does not do

| Does | Does not |
|---|---|
| Blocks source writes in Work mode until you approve a plan, then tests | Judge whether a plan is good. It checks the plan's shape; you read it |
| Refuses access to secret files (`.env`, keys) in every mode | Stop an AI that tries to escape. It frames a cooperative one |
| Injects the rules that match the current task, file and phase | Block anything while its service is down. Hooks then let actions through, except secret-file access |
| Records the approved plan and rules behind each commit | Prove that code gets better. Rule retrieval is measured, outcomes are not |

## Prerequisites

- Claude Code
- Python 3.11 or newer
- Docker, because Neo4j runs in a container

`jq` and `curl` are optional. Every call has a Python fallback.

## Install

```bash
claude plugin marketplace add deMallory/writty
claude plugin install writty@writty
```

Open Claude Code once in any project. Writty sees it is not set up yet and prints one command with an absolute path:

```bash
bash /path/it/prints/scripts/bootstrap-plugin.sh
```

Run it, then restart Claude Code. The script sets up the Python environment, Neo4j, the rules, the background service and the permissions. It is safe to re-run, and re-running it is also how you update. Details and troubleshooting: `docs/install.md`.

Check that the service answers:

```bash
curl http://localhost:8765/health
```

Then type any prompt in Claude Code. You should see a `[Writ: ...]` status line and a `--- WRIT RULES ---` block.

## A first gated task

1. Ask for a change. When no mode is set, a build request switches the session to Work mode on its own. You can also name the mode you want.
2. Claude writes `plan.md` at the repo root: the files it will touch and why, the design, the rules it applied, the behaviors to test. Read it.
3. Type `approved`. The plan gate opens and Claude writes the tests only.
4. Read the tests and type `approved` again. Now Claude may write the code.

Type the approval as the whole message. The accepted words are English: `approved`, `ok`, `yes`, `go`, `lgtm` and a few more, listed in `bin/lib/approval_match.py`. A typo within two letters of `approved` also counts. An approval word inside a longer sentence makes Writty ask, not advance.

## The five modes

| Mode | Use it to | Gates |
|---|---|---|
| `conversation` | discuss, brainstorm | none |
| `debug` | chase one failure | root cause before any source edit |
| `investigate` | audit, explore, research | advisory, per lens |
| `review` | check code against the rules | none |
| `work` | build or change code | plan, then tests |

The modes are defined in `writ/session/mode_engine.py`.

## When something blocks

- **An approval is refused with "Invalid or missing gate token".** The background service runs older code than the hooks. Restart it from the install directory with `bash scripts/stop-server.sh && bash scripts/ensure-server.sh`, then approve again. The helper scripts are `scripts/stop-server.sh` and `scripts/ensure-server.sh`.
- **Writty is silent.** A stopped service lets everything through except secret-file access. Check `curl http://localhost:8765/health`.
- **Something else looks wrong.** `writ doctor` checks the service, Neo4j, the embedding model and the hook registration. `writ doctor --fix` repairs the common cases.

## Where to go next

- [The core stack](architecture/core-stack.md): what Claude Code, the gates, Neo4j, Tantivy, ONNX and hnswlib each do.
- `HANDBOOK.md`: modes, gates, helper agents, the command line.
- `docs/reference/session-and-gates.md`: the exact gate contract.
- `docs/install.md`: the other install paths, running the service under systemd, troubleshooting.
