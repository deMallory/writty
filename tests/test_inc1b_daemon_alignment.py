"""INC-1b: daemon cache-desync test hardening (NRV-0 follow-up).

`bin/lib/common.sh::_writ_session` mutates session state in the DAEMON first (curl), falling
back to the file helper. Live-hook tests set/read state via writ-session.py directly (file).
When the daemon's cache_dir diverges from the tests' computed dir, a hook's write (daemon
dir) and a test's read (file dir) hit different files -> the reset "succeeds" but the test
reads a stale value -> en-masse live-hook/session failure.

The fix (tests/_daemon.py + conftest pytest_sessionstart) aligns the daemon to the tests'
expected dir at suite start. This file pins the contract:
  - classify_daemon_alignment(daemon_dir, expected) -> 'down' | 'aligned' | 'diverged' (pure)
  - ensure_daemon_aligned() realigns a diverged daemon (idempotent)
  - end-to-end: a daemon-routed reset is visible to a file-helper read once aligned.

The classifier test is pure (always runs). Live tests skip only when no daemon is reachable.
"""
from __future__ import annotations

import json
import subprocess
import sys
import uuid
from pathlib import Path

import pytest

from tests._daemon import (
    classify_daemon_alignment,
    daemon_cache_dir,
    ensure_daemon_aligned,
    expected_cache_dir,
)

SKILL_DIR = Path(__file__).resolve().parent.parent
SESSION_HELPER = str(SKILL_DIR / "bin" / "lib" / "writ-session.py")
POSTCOMPACT_HOOK = SKILL_DIR / "hooks" / "scripts" / "writ-postcompact.sh"


# --- 1. Alignment classifier (pure, always runs) -----------------------------


class TestClassifier:
    def test_no_daemon_is_down(self) -> None:
        assert classify_daemon_alignment(None, "/tmp/claude-1001") == "down"

    def test_matching_dirs_aligned(self) -> None:
        assert classify_daemon_alignment("/tmp/claude-1001", "/tmp/claude-1001") == "aligned"

    def test_differing_dirs_diverged(self) -> None:
        assert classify_daemon_alignment("/tmp", "/tmp/claude-1001") == "diverged"

    def test_diverged_is_never_aligned(self) -> None:
        # Regression guard: a desynced daemon must never read as 'aligned'.
        assert classify_daemon_alignment("/tmp", "/tmp/claude-1001") != "aligned"


# --- 2. ensure_daemon_aligned brings the daemon into alignment (live) --------


class TestEnsureAligned:
    def test_daemon_aligned_after_ensure(self) -> None:
        ensure_daemon_aligned()
        dd = daemon_cache_dir()
        if dd is None:
            pytest.skip("no daemon reachable")
        assert dd == expected_cache_dir(), (
            f"daemon cache_dir {dd} != expected {expected_cache_dir()} after ensure_daemon_aligned"
        )

    def test_ensure_is_idempotent(self) -> None:
        ensure_daemon_aligned()
        ensure_daemon_aligned()
        dd = daemon_cache_dir()
        if dd is None:
            pytest.skip("no daemon reachable")
        assert dd == expected_cache_dir()


# --- 3. End-to-end: daemon-routed reset is visible to a file-helper read -----


class TestCrossPathReset:
    """Reproduces the exact failure: a hook resets via the daemon, a test reads via the file
    helper. Once aligned, the read sees the reset."""

    def _session(self, *args: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            [sys.executable, SESSION_HELPER, *args],
            capture_output=True, text=True, timeout=10,
        )

    def test_postcompact_reset_visible_after_alignment(self) -> None:
        ensure_daemon_aligned()
        if daemon_cache_dir() is None:
            pytest.skip("no daemon reachable")
        sid = f"inc1b-{uuid.uuid4().hex[:8]}"
        # Deplete the budget via the file helper (a field PostCompact resets to
        # DEFAULT_SESSION_BUDGET=8000). A fresh session starts at 8000.
        self._session("update", sid, "--cost", "5000")
        # Reset via the postcompact hook (which routes through the daemon first).
        proc = subprocess.run(
            ["bash", str(POSTCOMPACT_HOOK)],
            input=json.dumps({"session_id": sid, "event": "compact"}),
            capture_output=True, text=True, cwd=str(SKILL_DIR), timeout=15,
        )
        assert proc.returncode == 0, f"postcompact hook failed: {proc.stderr[:300]!r}"
        # Read via the file helper: the daemon-routed reset must be visible.
        read = self._session("read", sid)
        try:
            cache = json.loads(read.stdout)
        except json.JSONDecodeError:
            cache = {}
        self._session("clear", sid)  # best-effort cleanup
        assert cache.get("remaining_budget", -1) == 8000, (
            "daemon-routed postcompact reset was not visible to the file-helper read "
            f"(remaining_budget got {cache.get('remaining_budget', -1)}, expected DEFAULT 8000); "
            "daemon/file cache dirs diverged"
        )
