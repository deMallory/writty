---
type: Guide
title: "Local service"
description: The FastAPI daemon every hook calls, how it starts, its route modules, its error contract and health states, and the state it does not own.
---

# Local service

The daemon is one FastAPI process on `localhost:8765`, shared by every Claude Code session on the machine. Hooks call it over HTTP so each turn pays for one warm request instead of a cold Python start. It has no authentication because it listens on localhost only. The exact endpoint list is generated: `docs/reference/http-api.md`.

## How it starts

- `writ serve` (`writ/cli.py`) runs uvicorn on the app in `writ/server/__init__.py`. Host and port default to `localhost` and `8765`; `WRIT_HOST` and `WRIT_PORT` override them.
- Nobody has to start it by hand. The SessionStart hook, the prompt hook (`writ-rag-inject.sh`) and `scripts/ensure-server.sh` all call `writ_ensure_server` in `scripts/lib/writ-server-lib.sh`. It probes `/health`, and starts `writ serve` under a lock only when nothing answers, so two sessions never start two daemons. A healthy daemon is never restarted.
- Restarting after a code change: `bash scripts/stop-server.sh; bash scripts/ensure-server.sh`. Operator detail: `HANDBOOK.md` section 16.

## Startup order

The `lifespan` function in `writ/server/__init__.py` builds everything before the first request, so a request handler never waits on disk or on the graph:

1. Open the Neo4j connection (`writ/graph/db/`).
2. Build the retrieval pipeline with the abstention gate on. See [Retrieval](retrieval.md).
3. Build the methodology trigger index from the graph.
4. Create the analyzer and instrumentation clients.

A consequence: the daemon's indexes reflect the graph as it was at startup. After a re-seed of Neo4j, restart the daemon.

## Route modules

One router module per domain under `writ/server/routes/`, wired into the app at the bottom of `writ/server/__init__.py`.

| Module | Serves |
|---|---|
| `writ/server/routes/query.py` | Retrieval (`/query`, `/prompt-bundle`, `/always-on`, `/methodology-companion`), rule lookup, rule proposal and feedback, `/analyze`, `/health` |
| `writ/server/routes/gate.py` | The write gate (`/pre-write-check`), phase advance, promotion of a rule candidate. See [Work gates and approvals](../workflows/work-gates.md) |
| `writ/server/routes/session_state.py` | Reads and writes of one session's state under `/session/{session_id}/...` |
| `writ/server/routes/decision_memory.py` | Commit capture, recall, and the auto-memory mirror. See [Rule graph](rule-graph.md) |
| `writ/server/routes/git_hooks.py` | Installs the post-commit git hook on the first Work-mode entry into a repo |
| `writ/server/routes/explorer.py` | The read-only HTML dashboard and graph explorer |

Handlers read the pipeline and the database as live attributes of `writ.server` (`server._pipeline`, `server._db`), never through a `from` import. That is what lets the lifespan swap them in and lets tests monkeypatch them.

## Error contract

- A logical failure returns HTTP 200 with an `error` key. Hooks read the key.
- 422 means the request body failed validation.
- A handler that raises gives a 500. Hooks fail open on it: the turn goes on without that hook's help, and the failure is logged.
- `POST /session/{session_id}/mode` is the one route that returns 400, for an unknown mode.

Full contract: `docs/reference/architecture.md` section 3.

## Health

`GET /health` reports rule counts, index state and startup time. Its status is `healthy`, or `degraded` when the retrieval index is warm but Neo4j reports zero rules: the daemon outlived a re-seed and its index disagrees with the graph. Restart it.

Every other request emits one `daemon_request` metrics row with the route template, status and latency, even when the handler raises.

## State it does not own

- Session state is files under `~/.cache/writ/session`, one store per user (`writ/session/cache.py`). The daemon reads and writes them, and so does `bin/lib/writ-session.py` when the daemon is down. Both must resolve the same directory: with two stores for one session, a phase or approval written to one is invisible to the other.
- Rules live in Neo4j. The daemon holds indexes built from them, not the rules themselves.
