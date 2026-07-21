"""SERVER-SINGLETON: one flock-guarded server-start routine.

scripts/lib/writ-server-lib.sh provides writ_ensure_server(), which both ensure-server.sh and
session-start-bootstrap.sh call. flock on /tmp/writ-server-${WRIT_PORT}.lock makes the
check-then-start critical section atomic, so concurrent SessionStarts launch exactly one server.
RED until the lib + the script edits land.

The concurrency tests inject WRIT_HEALTH_CMD + WRIT_SERVE_CMD so the singleton is exercised
deterministically without binding a real port.
"""

from __future__ import annotations

import os
import subprocess
import time
from pathlib import Path

import pytest

from tests.plugin.conftest import REPO_ROOT

LIB = REPO_ROOT / "scripts" / "lib" / "writ-server-lib.sh"
ENSURE = REPO_ROOT / "scripts" / "ensure-server.sh"
BOOTSTRAP = REPO_ROOT / "hooks" / "scripts" / "session-start-bootstrap.sh"
RAG_INJECT = REPO_ROOT / "hooks" / "scripts" / "writ-rag-inject.sh"

TEST_PORT = "8791"  # not 8765; the lib only uses it for the lockfile name + URL (health overridden)


# --------------------------------------------------------------------------- #
# source shape
# --------------------------------------------------------------------------- #
class TestLibShape:
    def test_lib_exists(self):
        assert LIB.exists(), "scripts/lib/writ-server-lib.sh must exist"

    def test_defines_entry_points(self):
        src = LIB.read_text()
        assert "writ_ensure_server" in src
        assert "writ_server_health" in src

    def test_uses_flock_on_per_port_lockfile(self):
        src = LIB.read_text()
        assert "flock" in src
        assert "writ-server-${WRIT_PORT}.lock" in src or 'writ-server-$WRIT_PORT.lock' in src

    def test_pins_cache_dir(self):
        assert "WRIT_CACHE_DIR" in LIB.read_text()

    def test_serve_uses_absolute_venv_writ(self):
        """F5: launch via the venv's ABSOLUTE console script, not bare `writ`.

        After `cd "$WRIT_DIR"` (which contains a `writ/` package directory) and with
        an empty PATH component (cwd) ahead of bin/, bare `writ serve` can resolve to
        the directory -> `nohup: failed to run command 'writ': Permission denied` ->
        the daemon never starts. The absolute venv path removes that ambiguity.
        """
        src = LIB.read_text()
        assert '"$VENV_DIR/bin/writ"' in src, (
            "writ-server-lib.sh must launch the daemon via the absolute venv writ "
            '("$VENV_DIR/bin/writ"), not bare `writ` (collides with the writ/ package dir)'
        )


class TestScriptsUseLib:
    def test_ensure_server_sources_lib_and_calls_entry(self):
        src = ENSURE.read_text()
        assert "writ-server-lib.sh" in src
        assert "writ_ensure_server" in src
        assert "nohup" not in src, "ensure-server.sh must not launch the server inline anymore"

    def test_bootstrap_sources_lib_and_calls_entry(self):
        src = BOOTSTRAP.read_text()
        assert "writ-server-lib.sh" in src
        assert "writ_ensure_server" in src
        assert "nohup" not in src, "session-start-bootstrap.sh must not launch the server inline anymore"

    def test_rag_inject_autostart_uses_lib(self):
        """Audit #4: the UserPromptSubmit hook's auto-start must go through the shared
        flock-guarded singleton, not a bespoke noclobber lockfile + raw uvicorn nohup
        (which could not coordinate with the other start paths -> duplicate-daemon race)."""
        src = RAG_INJECT.read_text()
        assert "writ-server-lib.sh" in src, (
            "writ-rag-inject.sh must source the shared server-start lib"
        )
        assert "writ_ensure_server" in src, (
            "writ-rag-inject.sh must auto-start via writ_ensure_server (flock-guarded)"
        )
        assert "uvicorn" not in src, (
            "writ-rag-inject.sh must not launch uvicorn inline; route through the lib"
        )


# --------------------------------------------------------------------------- #
# behavior (deterministic, no real server)
# --------------------------------------------------------------------------- #
def _harness(tmp_path: Path, counter: Path, sentinel: Path):
    """A fake serve cmd (single executable token) that records a start then makes health pass."""
    fake = tmp_path / "fakeserve.sh"
    fake.write_text(
        "#!/usr/bin/env bash\n"
        f'echo start >> "{counter}"\n'
        "sleep 0.4\n"
        f'touch "{sentinel}"\n'
    )
    fake.chmod(0o755)
    env = dict(os.environ)
    env.update({
        "WRIT_PORT": TEST_PORT,
        "WRIT_HOST": "localhost",
        "WRIT_LOG": str(tmp_path / "serve.log"),
        "WRIT_HEALTH_CMD": f"test -f {sentinel}",
        "WRIT_SERVE_CMD": str(fake),
    })
    # ensure a clean lockfile
    lock = Path(f"/tmp/writ-server-{TEST_PORT}.lock")
    if lock.exists():
        lock.unlink()
    return env

def _run_ensure(env):
    return subprocess.Popen(
        ["bash", "-c", f'source "{LIB}"; writ_ensure_server'],
        env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )


class TestSingletonBehavior:
    def test_concurrent_starts_launch_once(self, tmp_path):
        counter = tmp_path / "counter"
        sentinel = tmp_path / "sentinel"
        env = _harness(tmp_path, counter, sentinel)
        p1 = _run_ensure(env)
        p2 = _run_ensure(env)
        p1.wait(timeout=30)
        p2.wait(timeout=30)
        starts = counter.read_text().count("start") if counter.exists() else 0
        assert starts == 1, f"flock must serialize start: expected 1 launch, got {starts}"

    def test_already_healthy_starts_nothing(self, tmp_path):
        counter = tmp_path / "counter"
        sentinel = tmp_path / "sentinel"
        env = _harness(tmp_path, counter, sentinel)
        sentinel.touch()  # health passes immediately
        p = _run_ensure(env)
        p.wait(timeout=30)
        starts = counter.read_text().count("start") if counter.exists() else 0
        assert starts == 0, f"healthy server must not be restarted: got {starts} launches"

    def test_returns_zero_on_success(self, tmp_path):
        counter = tmp_path / "counter"
        sentinel = tmp_path / "sentinel"
        env = _harness(tmp_path, counter, sentinel)
        rc = subprocess.run(
            ["bash", "-c", f'set -e; source "{LIB}"; writ_ensure_server'],
            env=env, capture_output=True, timeout=30,
        ).returncode
        assert rc == 0, "writ_ensure_server must return 0 even under set -e"
