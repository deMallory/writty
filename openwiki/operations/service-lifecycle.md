---
type: Guide
title: "Service lifecycle"
description: What runs and on which port, who starts the daemon on Linux and on macOS, when to restart it, and where to read its health and logs.
---

# Service lifecycle

Writty runs two processes: the daemon on port 8765 and Neo4j on 7687. You rarely start either by hand, because a hook starts the daemon when it finds it down. You restart the daemon after a change to Python code under `writ/` and after a re-seed of Neo4j. How the daemon works inside: [Local service](../architecture/local-service.md).

## What runs

| What | Port | Set in | Started by |
|---|---|---|---|
| Daemon | 8765 | `scripts/lib/writ-server-lib.sh` | a hook, `scripts/ensure-server.sh`, or systemd on Linux |
| Neo4j | 7687 | `docker-compose.yml` | Docker: container `writ-neo4j`, `restart: unless-stopped` |
| Test daemon | 8799 | `tests/conftest.py` | the test suite |
| Test Neo4j | 7688 | `scripts/test-graph.sh` | `make test`, or `make test-graph-up` |

The suite keeps its own pair, so a test run never touches the daemon or the graph you work with. `scripts/test-graph.sh` refuses to publish port 7687.

## Who owns the daemon

| | Linux with the unit | macOS, or Linux without the unit |
|---|---|---|
| Owner | the `writ-server` systemd user unit, installed by `scripts/install-server-service.sh` | nobody: hooks start it on demand |
| Starts | at login, or at boot after `sudo loginctl enable-linger $USER` | when a session or a prompt finds it down |
| After a crash | systemd restarts it | the next prompt starts it again |
| Daily log sweep | the `writ-logs-rotate.timer` unit | none: run `writ logs rotate` |

**On demand.** Two hooks start the daemon, both through the same locked routine in `scripts/lib/writ-server-lib.sh`, so two sessions never start two daemons. SessionStart (`hooks/scripts/session-start-bootstrap.sh`) starts it once Neo4j answers. The prompt hook (`hooks/scripts/writ-rag-inject.sh`) starts it on any prompt that finds it down, after `docker start writ-neo4j`.

**The macOS realign.** On macOS, SessionStart runs that routine with `WRIT_REALIGN_CACHE=1`: a daemon that reports a different session store than the hooks use is stopped and started again. Two stores for one session is what made approvals vanish; see "State it does not own" in [Local service](../architecture/local-service.md). Linux skips the realign, because a restart from a hook would fight systemd.

**Known gap, seen 2026-09-28.** SessionStart probes Neo4j through `timeout`, a GNU tool that stock macOS does not ship. Without it the probe fails even with Neo4j up, SessionStart stops early, and neither its start nor the realign runs. The prompt hook still starts the daemon, without the realign. Check with `command -v timeout`: no output means this machine is affected. PR 15 fixes it (open on 2026-09-28). Until the fix reaches the installed plugin, restart the daemon by hand if approvals go missing.

## When to restart

| Change | What to do |
|---|---|
| Python under `writ/` (routes, retrieval, schema) | Restart the daemon: it keeps serving the old modules |
| Neo4j re-seeded, or `/health` says `degraded` | Restart the daemon: its indexes were built from the old graph |
| A hook script edited | Nothing: each call reads the script again |
| An entry added to `hooks/hooks.json` | Start a new Claude Code session |
| Plugin updated | Run the bootstrap again (`docs/install.md`, section "Updating"), restart the daemon, start a new session |

## Commands

Run the scripts from the repo, or from the plugin's copy under ~/.claude/plugins/cache/writty/writty/ on a plugin install.

| Task | Linux with the unit | macOS, or Linux without the unit |
|---|---|---|
| Restart | `systemctl --user restart writ-server` | `bash scripts/stop-server.sh; bash scripts/ensure-server.sh` |
| Stop | `systemctl --user stop writ-server` | `bash scripts/stop-server.sh` |
| Status | `systemctl --user status writ-server` | `curl -s localhost:8765/health` |
| Daemon log | `journalctl --user -u writ-server -f` | `tail -f ~/.cache/writ/logs/server.log` |

With the unit installed, stay on `systemctl`. `scripts/stop-server.sh` stops the unit through systemd, and `scripts/ensure-server.sh` would then start a daemon systemd does not manage. Neither script stops Neo4j.

`scripts/ensure-server.sh` also starts Neo4j with `docker compose up -d neo4j` when port 7687 does not answer.

## Health and repair

- `GET /health` reports `healthy` or `degraded`, the rule counts, and `cache_dir`, the session store the daemon uses. A `cache_dir` other than the hooks' store (`~/.cache/writ/session` by default) is the split the realign heals.
- `writ doctor` runs the deeper checks: daemon, ports, Neo4j, constraints, embedding stack, corpus drift, hook registration. `writ doctor --fix` repairs what it can. Reference: `docs/reference/cli.md`.

## Logs

- **Daemon output.** The first that applies: `$WRIT_LOG`, `$WRIT_LOG_ROOT/server.log`, `$CLAUDE_PLUGIN_DATA/server.log` when a plugin hook started it, then `~/.cache/writ/logs/server.log` (`writ_default_server_log` in `scripts/lib/writ-server-lib.sh`). Under the systemd unit it goes to the journal.
- **Typed streams.** Audit, friction, metrics and errors, one file each under `~/.cache/writ/logs/<project>/` (`stream_path` in `writ/shared/logging.py`). `WRIT_LOG_ROOT` moves the root. Read them with `writ logs tail`, `writ logs stats` and `writ logs list`. What each stream holds: `docs/reference/logging.md`.
- **Rotation.** A stream rotates at 50 MB when written. The daily sweep (gzip, prune by retention) runs from the systemd timer on Linux; on macOS run `writ logs rotate` yourself.

`HANDBOOK.md` section 18 still places the streams under `<install>/var/logs/`. Since 1.7.2 the code writes them under `~/.cache/writ/logs`.

## Neo4j

The container `writ-neo4j` comes from `docker-compose.yml`, keeps its data in the `writ-neo4j-data` volume, and restarts with Docker. Start it by hand with `docker compose up -d neo4j` from the repo. The browser answers on http://localhost:7474. What the graph holds: [Rule graph](../architecture/rule-graph.md).
