"""Tests for hooks/scripts/session-start-bootstrap.sh (Phase C).

Verifies the SessionStart hook script exists, uses explicit CLAUDE_PLUGIN_ROOT
resolution (not dirname walk), probes the expected services, and exits 0 in
all branches (graceful degradation).
"""

from __future__ import annotations

import os
import platform
import socket
import subprocess
import sys
import time
from pathlib import Path

import pytest

from tests.plugin.conftest import REPO_ROOT

SESSION_START_BOOTSTRAP = REPO_ROOT / "hooks" / "scripts" / "session-start-bootstrap.sh"
RUN_BOUNDED = REPO_ROOT / "bin" / "lib" / "run-bounded.py"

# Exits 127 like the shell does when `timeout` is missing (stock macOS), and records the
# call. First on PATH, it reproduces the macOS failure on Linux CI, where `timeout` exists.
STUB_TIMEOUT = """#!/usr/bin/env bash
echo called >> "{calls}"
exit 127
"""

# Stands in for the real lib so no daemon starts: records that step 4 was reached, and
# with which realign setting.
STUB_SERVER_LIB = """writ_ensure_server() {
  printf 'realign=%s\\n' "${WRIT_REALIGN_CACHE:-}" > "${WRIT_DIR}/ensure-called"
}
"""


class TestSessionStartBootstrapExists:
    def test_session_start_bootstrap_script_exists(self) -> None:
        """hooks/scripts/session-start-bootstrap.sh must exist and be executable."""
        if not SESSION_START_BOOTSTRAP.exists():
            pytest.skip(
                "Phase C artifact hooks/scripts/session-start-bootstrap.sh not yet created"
            )
        assert SESSION_START_BOOTSTRAP.exists()
        assert os.access(SESSION_START_BOOTSTRAP, os.X_OK), (
            "hooks/scripts/session-start-bootstrap.sh must have the executable bit set"
        )


class TestSessionStartBootstrapContent:
    @pytest.fixture()
    def content(self) -> str:
        if not SESSION_START_BOOTSTRAP.exists():
            pytest.skip(
                "Phase C artifact hooks/scripts/session-start-bootstrap.sh not yet created"
            )
        return SESSION_START_BOOTSTRAP.read_text()

    def test_session_start_uses_explicit_plugin_root(self, content: str) -> None:
        """Script must set WRIT_DIR from ${CLAUDE_PLUGIN_ROOT}, not from dirname walk.

        The script lives at hooks/scripts/ (two levels deep), so a dirname walk
        would resolve to hooks/scripts rather than the repo root.
        """
        assert (
            'WRIT_DIR="${CLAUDE_PLUGIN_ROOT}"' in content
            or "WRIT_DIR=${CLAUDE_PLUGIN_ROOT}" in content
            or 'WRIT_DIR="${CLAUDE_PLUGIN_ROOT:-' in content
        ), (
            "session-start-bootstrap.sh must set WRIT_DIR from ${CLAUDE_PLUGIN_ROOT} explicitly"
        )
        # Should NOT use dirname-based resolution for WRIT_DIR
        assert 'dirname "$0"' not in content or "WRIT_DIR" not in content.split('dirname "$0"')[0].split('\n')[-1], (
            "session-start-bootstrap.sh must not use dirname walk to resolve WRIT_DIR"
        )

    def test_session_start_probes_venv(self, content: str) -> None:
        """The venv comes from the shared resolver and its python3 is probed before use."""
        assert 'writ_resolve_venv "${WRIT_DIR}"' in content, (
            "session-start-bootstrap.sh must take VENV_DIR from writ_resolve_venv"
        )
        assert '"${VENV_DIR}/bin/python3"' in content, (
            "session-start-bootstrap.sh venv probe must check for the python3 binary"
        )

    def test_session_start_probes_neo4j(self, content: str) -> None:
        """Script must contain a TCP probe for Neo4j bolt port 7687."""
        assert "7687" in content, (
            "session-start-bootstrap.sh must probe Neo4j bolt port 7687"
        )
        # Accept any of the common probe mechanisms
        has_probe = (
            "nc -z" in content
            or "curl" in content
            or "/dev/tcp/" in content
            or "bash -c" in content
        )
        assert has_probe, (
            "session-start-bootstrap.sh must probe port 7687 via nc -z, curl, or /dev/tcp/"
        )

    def test_session_start_ensures_server_via_shared_lib(self, content: str) -> None:
        """Server health/start is delegated to the flock-guarded shared lib (which probes /health)."""
        assert "writ-server-lib.sh" in content and "writ_ensure_server" in content, (
            "session-start-bootstrap.sh must source writ-server-lib.sh and call writ_ensure_server"
        )
        lib = (REPO_ROOT / "scripts" / "lib" / "writ-server-lib.sh").read_text()
        assert "/health" in lib, "the shared server lib must probe /health"

    def test_session_start_graceful_degradation(self, content: str) -> None:
        """Script must exit 0 in all branches; must not exit 1 for missing venv or Neo4j."""
        lines = content.splitlines()
        hard_exits = [
            line.strip() for line in lines
            if line.strip().startswith("exit 1")
        ]
        assert not hard_exits, (
            "session-start-bootstrap.sh must not call 'exit 1' — all degradation paths "
            f"must exit 0. Found: {hard_exits}"
        )


class TestNeo4jProbeWithoutGnuTimeout:
    """The probe must not need GNU timeout, which stock macOS lacks.

    With it, the probe exited 127 with Neo4j up, the hook stopped at step 3, and neither
    the daemon start nor the Darwin realign ever ran (found 2026-09-28).
    """

    @pytest.fixture()
    def sandbox(self, tmp_path: Path) -> Path:
        plugin_root = tmp_path / "plugin-root"
        (plugin_root / "bin" / "lib").mkdir(parents=True)
        (plugin_root / "bin" / "lib" / "run-bounded.py").symlink_to(RUN_BOUNDED)
        (plugin_root / "scripts" / "lib").mkdir(parents=True)
        (plugin_root / "scripts" / "lib" / "writ-server-lib.sh").write_text(STUB_SERVER_LIB)
        venv_bin = tmp_path / "data" / ".venv" / "bin"
        venv_bin.mkdir(parents=True)
        (venv_bin / "python3").symlink_to(sys.executable)
        stub_bin = tmp_path / "stub-bin"
        stub_bin.mkdir()
        stub = stub_bin / "timeout"
        stub.write_text(STUB_TIMEOUT.format(calls=tmp_path / "timeout-calls"))
        stub.chmod(0o755)
        return tmp_path

    @pytest.fixture()
    def listener(self):
        with socket.socket() as s:
            s.bind(("127.0.0.1", 0))
            s.listen(1)
            yield s.getsockname()[1]

    def _run(self, sandbox: Path, host: str, port: int) -> subprocess.CompletedProcess:
        env = {
            **os.environ,
            "PATH": f"{sandbox / 'stub-bin'}:{os.environ['PATH']}",
            "CLAUDE_PLUGIN_ROOT": str(sandbox / "plugin-root"),
            "CLAUDE_PLUGIN_DATA": str(sandbox / "data"),
            "WRIT_NEO4J_HOST": host,
            "WRIT_NEO4J_PORT": str(port),
        }
        # The suite sets this so a hook cannot spawn a real daemon. This test stubs
        # writ_ensure_server and is checking that the start is reached.
        env.pop("WRIT_NO_AUTOSTART", None)
        return subprocess.run(
            ["bash", str(SESSION_START_BOOTSTRAP)], input="{}",
            capture_output=True, text=True, env=env, timeout=30,
        )

    def test_reachable_neo4j_reaches_the_server_start(self, sandbox: Path, listener: int) -> None:
        r = self._run(sandbox, "127.0.0.1", listener)
        assert r.returncode == 0, r.stderr
        assert "Neo4j not reachable" not in r.stderr, r.stderr
        assert (sandbox / "plugin-root" / "ensure-called").is_file(), (
            "the hook stopped at the Neo4j probe while Neo4j was listening"
        )
        assert not (sandbox / "timeout-calls").exists(), "the probe still calls GNU timeout"

    def test_the_darwin_realign_runs(self, sandbox: Path, listener: int) -> None:
        self._run(sandbox, "127.0.0.1", listener)
        marker = sandbox / "plugin-root" / "ensure-called"
        assert marker.is_file(), "the hook never reached writ_ensure_server"
        expected = "realign=1" if platform.system() == "Darwin" else "realign="
        assert marker.read_text().strip() == expected

    def test_closed_port_reports_unreachable_and_skips_the_start(self, sandbox: Path) -> None:
        with socket.socket() as s:
            s.bind(("127.0.0.1", 0))
            port = s.getsockname()[1]
        r = self._run(sandbox, "127.0.0.1", port)
        assert r.returncode == 0, r.stderr
        assert f"Neo4j not reachable at 127.0.0.1:{port}" in r.stderr, r.stderr
        assert not (sandbox / "plugin-root" / "ensure-called").exists()
        assert not (sandbox / "timeout-calls").exists(), "the probe still calls GNU timeout"

    def test_black_holed_host_is_bounded(self, sandbox: Path) -> None:
        # 10.255.255.1 is unroutable in practice: the SYN goes unanswered, so an unbounded
        # connect would block for the kernel SYN timeout. A network that refuses it at once
        # also passes; only a broken bound fails.
        start = time.monotonic()
        r = self._run(sandbox, "10.255.255.1", 7687)
        elapsed = time.monotonic() - start
        assert r.returncode == 0, r.stderr
        assert "Neo4j not reachable at 10.255.255.1:7687" in r.stderr, r.stderr
        assert not (sandbox / "plugin-root" / "ensure-called").exists()
        assert elapsed < 8, f"the probe took {elapsed:.1f} s; its bound is 2 s"