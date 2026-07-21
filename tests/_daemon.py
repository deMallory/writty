"""INC-1b: daemon cache-dir alignment helpers for the test suite.

`bin/lib/common.sh::_writ_session` mutates session state in the daemon first (curl), so a
hook writes to the daemon's cache_dir while a file-helper test reads from
`WRIT_CACHE_DIR`/`gettempdir`. When those diverge, live-hook/session tests fail en masse.
These helpers let the suite align the shared daemon to the tests' cache dir at startup.
"""
from __future__ import annotations

import json
import os
import subprocess
import tempfile
import time
import urllib.request
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent


def _port() -> str:
    """The daemon port, resolved LIVE from WRIT_PORT (default 8765).

    A function, not a module constant, so the suite's dedicated test port (set in
    conftest pytest_sessionstart) is honored regardless of when this module is
    imported -- a module-level constant would freeze 8765 at import time.
    """
    return os.environ.get("WRIT_PORT", "8765")


def _health_url() -> str:
    return f"http://localhost:{_port()}/health"


def expected_cache_dir() -> str:
    """The cache dir writ-session.py uses file-side: WRIT_CACHE_DIR or gettempdir()."""
    return os.environ.get("WRIT_CACHE_DIR") or tempfile.gettempdir()


def _daemon_health() -> dict | None:
    """The running daemon's /health JSON, or None if unreachable."""
    try:
        with urllib.request.urlopen(_health_url(), timeout=2) as r:
            return json.load(r)
    except Exception:  # noqa: BLE001
        return None


def daemon_cache_dir() -> str | None:
    """The running daemon's cache_dir from /health, or None if no daemon is reachable."""
    h = _daemon_health()
    return h.get("cache_dir") if h else None


def daemon_friction_log() -> str | None:
    """The running daemon's friction-log path from /health (None if unreachable or an
    older daemon that does not report it)."""
    h = _daemon_health()
    return h.get("friction_log") if h else None


def expected_friction_log() -> str | None:
    """The friction-log path the suite wants the daemon to use (a throwaway set by
    conftest via WRIT_FRICTION_LOG). None means friction alignment is not enforced."""
    return os.environ.get("WRIT_FRICTION_LOG")


def classify_daemon_alignment(daemon_dir: str | None, expected: str) -> str:
    """'down' (no daemon) | 'aligned' (dirs match) | 'diverged' (dirs differ). Pure.

    The anti-masking contract: a diverged daemon must never read as 'aligned', so the suite
    cannot silently tolerate the desync that fails live-hook tests en masse.
    """
    if daemon_dir is None:
        return "down"
    return "aligned" if daemon_dir == expected else "diverged"


def ensure_daemon_aligned() -> str:
    """Realign a daemon whose cache_dir OR friction-log path diverges from expected.

    Restart (stop-server.sh + ensure-server.sh) with WRIT_CACHE_DIR pinned to
    expected_cache_dir() when the daemon's cache_dir diverges, and -- when the suite
    sets WRIT_FRICTION_LOG -- when its friction_log diverges too. Pinning the friction
    log keeps daemon-emitted events (post_compaction, gate decisions for test sessions,
    via daemon-first _writ_session calls) out of the repo's workflow-friction.log; tests
    assert on per-test in-process logs, never the daemon's. Idempotent; a no-op when
    already aligned or when no daemon is running. Returns the cache-alignment state.
    """
    expected = expected_cache_dir()
    expected_friction = expected_friction_log()
    health = _daemon_health()
    cache_state = classify_daemon_alignment(health.get("cache_dir") if health else None, expected)
    friction_aligned = (
        expected_friction is None
        or (health is not None and health.get("friction_log") == expected_friction)
    )
    if cache_state == "down":
        return "down"
    if cache_state == "aligned" and friction_aligned:
        return "aligned"

    env = {**os.environ, "WRIT_CACHE_DIR": expected}
    if expected_friction:
        env["WRIT_FRICTION_LOG"] = expected_friction
    for script in ("stop-server.sh", "ensure-server.sh"):
        path = _REPO_ROOT / "scripts" / script
        if not path.exists():
            continue
        try:
            subprocess.run(
                ["bash", str(path)],
                cwd=str(_REPO_ROOT), env=env,
                capture_output=True, timeout=60, check=False,
            )
        except (subprocess.SubprocessError, OSError):
            return "diverged"

    # ensure-server may take a moment to answer /health after restart.
    for _ in range(10):
        st = classify_daemon_alignment(daemon_cache_dir(), expected)
        if st != "down":
            return st
        time.sleep(0.5)
    return classify_daemon_alignment(daemon_cache_dir(), expected)


def start_test_daemon() -> str:
    """Start the suite's dedicated daemon on the test port (WRIT_PORT) with the test
    cache + throwaway friction, via ensure-server.sh (idempotent: starts if down).

    The interactive 8765 daemon is never touched -- the suite owns this daemon's full
    lifecycle (started here, stopped in stop_test_daemon). Returns the alignment state.
    """
    env = {**os.environ, "WRIT_CACHE_DIR": expected_cache_dir()}
    ensure = _REPO_ROOT / "scripts" / "ensure-server.sh"
    if ensure.exists():
        try:
            subprocess.run(
                ["bash", str(ensure)],
                cwd=str(_REPO_ROOT), env=env,
                capture_output=True, timeout=60, check=False,
            )
        except (subprocess.SubprocessError, OSError):
            return "down"
    return ensure_daemon_aligned()


def stop_test_daemon() -> None:
    """Stop the suite's dedicated test daemon at session finish (F4b/option C).

    The suite runs its own daemon on WRIT_PORT (a dedicated test port, never the
    interactive 8765), so there is nothing to "restore" -- we just stop the test
    daemon so it is not left running. Supersedes F4's restore_daemon_friction:
    isolation removes the hijack, so the restore-the-shared-daemon dance is gone.
    No-op when no daemon answers on the test port.
    """
    if daemon_cache_dir() is None:
        return
    stop = _REPO_ROOT / "scripts" / "stop-server.sh"
    if not stop.exists():
        return
    try:
        subprocess.run(
            ["bash", str(stop)],
            cwd=str(_REPO_ROOT), env={**os.environ},
            capture_output=True, timeout=30, check=False,
        )
    except (subprocess.SubprocessError, OSError):
        return
