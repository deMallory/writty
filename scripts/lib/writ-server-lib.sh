#!/usr/bin/env bash
# Shared, singleton-safe Writ server start. Sourced by scripts/ensure-server.sh and
# hooks/scripts/session-start-bootstrap.sh -- this file defines functions only, no top-level
# side effects. writ_ensure_server() guards the check-then-start critical section with flock so
# concurrent SessionStarts (two Claude windows opening together, or both callers firing close in
# time) launch the daemon EXACTLY once. Port-bind remains the final backstop.
#
# Inputs (env, defaulted at call time): WRIT_HOST, WRIT_PORT, WRIT_DIR, VENV_DIR, WRIT_LOG.
# Optional:
#   WRIT_REALIGN_CACHE=1  restart a cache-dir-misaligned daemon (FIX-2); off by default.
#   WRIT_SERVE_CMD        override the serve command (single token or space-separated, no quotes);
#                         default `writ serve --port $WRIT_PORT --host $WRIT_HOST`. Test injection.
#   WRIT_HEALTH_CMD       override the health probe; default curls /health. Test injection.

# True when the daemon answers /health (or the injected probe succeeds).
writ_server_health() {
    : "${WRIT_HOST:=localhost}" "${WRIT_PORT:=8765}"
    if [ -n "${WRIT_HEALTH_CMD:-}" ]; then
        ${WRIT_HEALTH_CMD} >/dev/null 2>&1
    else
        curl -s --connect-timeout 0.1 "http://${WRIT_HOST}:${WRIT_PORT}/health" >/dev/null 2>&1
    fi
}

# Critical section, run only while holding the flock. Always returns 0 (graceful).
_writ_start_locked() {
    if writ_server_health; then
        if [ "${WRIT_REALIGN_CACHE:-0}" = "1" ]; then
            # "already running" is only good if the daemon's cache dir AND friction-log
            # match ours (FIX-2 + audit #4). A daemon born under a divergent TMPDIR, or
            # carrying a stale WRIT_FRICTION_LOG, silently blackholes its telemetry until
            # restarted. Read both from /health in one probe.
            # Fail-safe: a value we cannot READ (empty), or an expectation we do not hold
            # (env unset), is treated as aligned -- we never restart a healthy daemon on
            # missing evidence.
            local health running_cache running_friction
            health=$(curl -s --connect-timeout 0.3 "http://${WRIT_HOST}:${WRIT_PORT}/health" 2>/dev/null || echo "")
            running_cache=$(printf '%s' "$health" | python3 -c "import sys,json; print(json.load(sys.stdin).get('cache_dir') or '')" 2>/dev/null || echo "")
            running_friction=$(printf '%s' "$health" | python3 -c "import sys,json; print(json.load(sys.stdin).get('friction_log') or '')" 2>/dev/null || echo "")
            local cache_mismatch=0 friction_mismatch=0
            if [ -n "$running_cache" ] && [ -n "${WRIT_CACHE_DIR:-}" ] && [ "$running_cache" != "$WRIT_CACHE_DIR" ]; then
                cache_mismatch=1
            fi
            if [ -n "$running_friction" ] && [ -n "${WRIT_FRICTION_LOG:-}" ] && [ "$running_friction" != "$WRIT_FRICTION_LOG" ]; then
                friction_mismatch=1
            fi
            if [ "$cache_mismatch" = 0 ] && [ "$friction_mismatch" = 0 ]; then
                echo "[Writ] Server already running on port $WRIT_PORT (cache_dir=${running_cache:-unknown})" >&2
                return 0
            fi
            echo "[Writ] Server on $WRIT_PORT misaligned (cache_dir=$running_cache vs ${WRIT_CACHE_DIR:-unset}; friction_log=$running_friction vs ${WRIT_FRICTION_LOG:-unset}); restarting to realign" >&2
            WRIT_PORT="$WRIT_PORT" WRIT_HOST="$WRIT_HOST" bash "${WRIT_DIR}/scripts/stop-server.sh" >/dev/null 2>&1 || true
            # fall through to start a correctly-pinned daemon
        else
            echo "[Writ] Server already running on port $WRIT_PORT" >&2
            return 0
        fi
    fi

    if [ -n "${VENV_DIR:-}" ] && [ -f "$VENV_DIR/bin/activate" ]; then
        # shellcheck disable=SC1091
        . "$VENV_DIR/bin/activate" 2>/dev/null || true
    fi

    # cd into the install dir so `writ serve` reads writ.toml from there, not the user's cwd.
    # Safe: this runs inside the flock subshell, so it never changes the caller's cwd.
    if [ -n "${WRIT_DIR:-}" ] && [ -d "$WRIT_DIR" ]; then
        cd "$WRIT_DIR" 2>/dev/null || true
    fi

    # Launch via the venv's ABSOLUTE console script. Bare `writ` is unsafe here: we
    # just cd'd into WRIT_DIR (which contains a `writ/` package directory) and PATH can
    # carry an empty component (= cwd) ahead of bin/, so `writ` may resolve to the
    # directory -> `nohup: failed to run command 'writ': Permission denied`. The absolute
    # path removes that ambiguity regardless of cwd / PATH / whether activation won.
    local serve_cmd="${WRIT_SERVE_CMD:-}"
    if [ -z "$serve_cmd" ]; then
        if [ -n "${VENV_DIR:-}" ] && [ -x "$VENV_DIR/bin/writ" ]; then
            serve_cmd="$VENV_DIR/bin/writ serve --port $WRIT_PORT --host $WRIT_HOST"
        else
            serve_cmd="writ serve --port $WRIT_PORT --host $WRIT_HOST"
        fi
    fi
    # 9>&- closes the inherited flock fd in the daemon child. Without it the long-lived daemon
    # would hold the lock for its entire life, so every later writ_ensure_server would block on
    # flock for the full timeout (and a realign could never re-acquire the lock to restart).
    nohup $serve_cmd > "$WRIT_LOG" 2>&1 9>&- &
    local pid=$!

    # Wait up to 5s for startup (Writ cold start is ~0.6s at 80 rules).
    local i
    for i in $(seq 1 50); do
        if writ_server_health; then
            echo "[Writ] Server started (PID $pid, log: $WRIT_LOG)" >&2
            return 0
        fi
        sleep 0.1
    done
    echo "[Writ] Warning: server did not respond within 5s (PID $pid, check $WRIT_LOG)" >&2
    return 0
}

# Idempotent, singleton-safe entry point. Always returns 0 so a caller's `set -e` never trips
# and hooks degrade gracefully (server unavailable) on any failure.
writ_ensure_server() {
    : "${WRIT_HOST:=localhost}" "${WRIT_PORT:=8765}" "${WRIT_LOG:=/tmp/writ-server.log}"
    # FIX-2: pin the daemon's session-cache dir deterministically (not ambient TMPDIR), so every
    # start path agrees and /health can report it. Exported here so `writ serve` inherits it.
    export WRIT_CACHE_DIR="${WRIT_CACHE_DIR:-$(python3 -c 'import tempfile; print(tempfile.gettempdir())' 2>/dev/null || echo /tmp)}"

    local lock="/tmp/writ-server-${WRIT_PORT}.lock"
    (
        if ! flock -w 15 9; then
            # Could not acquire in 15s: another starter is bringing the server up. Best-effort
            # health check, then yield -- do not start a competing daemon.
            writ_server_health || true
            exit 0
        fi
        _writ_start_locked
    ) 9>"$lock" || true
    return 0
}
