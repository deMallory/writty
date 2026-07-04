#!/usr/bin/env bash
# SessionStart hook: probes the plugin's runtime prerequisites and starts
# the Writ FastAPI daemon if everything is in place. Graceful-degrades
# in every failure branch (exits 0 so the session is never blocked).
#
# Lives at hooks/scripts/, not .claude/hooks/, so dirname walks resolve
# wrong; uses ${CLAUDE_PLUGIN_ROOT} directly instead.

set -u

# 1. Resolve install root and persistent-data dir. The plugin loader sets
#    CLAUDE_PLUGIN_ROOT; if unset, we're not running under the loader so
#    there's nothing to bootstrap.
if [ -z "${CLAUDE_PLUGIN_ROOT:-}" ]; then
  exit 0
fi
WRIT_DIR="${CLAUDE_PLUGIN_ROOT}"
WRIT_DATA="${CLAUDE_PLUGIN_DATA:-$HOME/.cache/writ}"

# Hook-map version canary. Every force-swap hook is built against the
# envelope map captured on one Claude Code build (hooks/hookmap-version);
# field names and events drift between builds. On mismatch, warn via
# stdout: SessionStart stdout at exit 0 is added as context the model
# sees, so the session itself knows the map may be stale. Runs before the
# early-exit probes below so degraded sessions still get the warning.
PINNED_FILE="${WRIT_DIR}/hooks/hookmap-version"
if [ -f "$PINNED_FILE" ]; then
  PINNED=$(tr -d '[:space:]' < "$PINNED_FILE")
  CURRENT="${CLAUDE_CODE_VERSION:-}"
  if [ -z "$CURRENT" ] && command -v claude >/dev/null 2>&1; then
    if command -v timeout >/dev/null 2>&1; then
      CURRENT=$(timeout 5 claude --version 2>/dev/null | grep -oE '[0-9]+\.[0-9]+\.[0-9]+' | head -1)
    else
      CURRENT=$(claude --version 2>/dev/null | grep -oE '[0-9]+\.[0-9]+\.[0-9]+' | head -1)
    fi
  fi
  if [ -n "$PINNED" ] && [ -n "$CURRENT" ] && [ "$PINNED" != "$CURRENT" ]; then
    echo "[Writ] Hook envelope map pinned to Claude Code ${PINNED}; running ${CURRENT}. Rewrite surfaces may have drifted: re-run the blackbox capture (touch ~/.claude/writ-blackbox.on, exercise tools, diff envelopes) and update hooks/hookmap-version."
  fi
fi
# Venv lives at ${CLAUDE_PLUGIN_DATA:-$HOME/.cache/writ}/.venv so it
# survives plugin upgrades that rewrite ${CLAUDE_PLUGIN_ROOT}.
VENV_DIR="${CLAUDE_PLUGIN_DATA:-$HOME/.cache/writ}/.venv"
SERVER_URL="${WRIT_SERVER_URL:-http://localhost:8765}"
SERVER_HEALTH_URL="http://localhost:8765/health"
NEO4J_HOST="${WRIT_NEO4J_HOST:-localhost}"
NEO4J_PORT="${WRIT_NEO4J_PORT:-7687}"

# 2. Probe venv. If missing, instruct user and exit 0.
if [ ! -x "${VENV_DIR}/bin/python3" ]; then
  cat >&2 <<MSG
[Writ] Plugin venv not bootstrapped at ${VENV_DIR}.
[Writ] Run once:
[Writ]   bash ${WRIT_DIR}/scripts/bootstrap-plugin.sh
[Writ] Writ hooks will degrade gracefully until bootstrap completes.
MSG
  exit 0
fi

# 3. Probe Neo4j bolt port 7687. If unreachable, instruct user and exit 0.
if ! (exec 3<>/dev/tcp/"${NEO4J_HOST}"/"${NEO4J_PORT}") 2>/dev/null; then
  cat >&2 <<MSG
[Writ] Neo4j not reachable at ${NEO4J_HOST}:${NEO4J_PORT}.
[Writ] Start it with:
[Writ]   docker compose -f ${WRIT_DIR}/docker-compose.yml up -d neo4j
[Writ] Writ hooks will degrade gracefully until Neo4j is up.
MSG
  exit 0
fi
exec 3<&- 2>/dev/null || true
exec 3>&- 2>/dev/null || true

# 4. Probe server health at http://localhost:8765/health. If already
#    running, we're done.
if curl -fsS --max-time 1 "${SERVER_HEALTH_URL}" >/dev/null 2>&1; then
  exit 0
fi

# 5. Start the server in the background. cd into WRIT_DIR so writ.toml is
#    read from the plugin install dir, not the user's cwd.
(
  cd "${WRIT_DIR}" || exit 0
  # shellcheck disable=SC1091
  . "${VENV_DIR}/bin/activate" 2>/dev/null || exit 0
  nohup writ serve >"${WRIT_DATA}/server.log" 2>&1 &
  disown 2>/dev/null || true
) >/dev/null 2>&1 &

# Wait up to 5 seconds for the server to come up.
for _ in 1 2 3 4 5; do
  if curl -fsS --max-time 1 "${SERVER_HEALTH_URL}" >/dev/null 2>&1; then
    break
  fi
  sleep 1
done

exit 0
