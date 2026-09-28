"""bin/lib/run-bounded.py, the stand-in for GNU timeout(1), and the Stop hook that uses it.

Stock macOS ships no `timeout`. The shell answers exit 127, which each caller misread as the
failure it was checking for: SessionStart as "Neo4j down", so it never started the daemon,
and the Stop hook as a failed test group, so no pending test ever ran. Found 2026-09-28.

The SessionStart side runs the hook itself, in tests/plugin/test_session_start_bootstrap.py.
"""
from __future__ import annotations

import json
import os
import re
import signal
import subprocess
import sys
import time
from pathlib import Path

import pytest

from tests._scope import DEFAULT_IGNORE, Universe, scan, shell_file

# autouse: pins cwd to a sandbox so `mode set` cannot delete THIS repo's gate artifacts.
from tests.fixtures.session_state import sandbox_cwd  # noqa: F401

REPO = Path(__file__).resolve().parent.parent
RUN_BOUNDED = REPO / "bin" / "lib" / "run-bounded.py"
RUN_HOOK = REPO / "hooks" / "scripts" / "writ-run-pending-tests.sh"
SESSION_HELPER = REPO / "bin" / "lib" / "writ-session.py"

# Exits 127 like the shell does when `timeout` is missing, and records the call. First on
# PATH, it reproduces the macOS failure on Linux CI, where the real `timeout` exists.
STUB_TIMEOUT = """#!/usr/bin/env bash
echo called >> "{calls}"
exit 127
"""

FAKE_RUNNER = """#!/usr/bin/env bash
echo "fake-runner stdout"
echo "fake-runner stderr" >&2
touch "{ran}"
"""

# Same declared universe as tests/test_cache_root_seam.py: every directory a shell file
# may live in, so the guard's zero covers them all.
SHELL_UNIVERSE = Universe(
    base=REPO,
    dirs=("hooks/scripts", "hooks/git", "bin", "bin/lib", "scripts", "scripts/lib"),
    match=shell_file,
    ignore=DEFAULT_IGNORE + ("docs",),
)
COMMENT_LINE = re.compile(r"^[ \t]*#.*$", re.M)
# `timeout` in command position, followed by a duration. The lookbehind skips flags and
# names that only end in it (`--connect-timeout 5`, `read_timeout 3`).
GNU_TIMEOUT = re.compile(r"(?<![\w.-])timeout[ \t]+[0-9][^\n]*")


def _alive(pid: int) -> bool:
    # A zombie counts as gone: it is dead and only waits for a reaper, which in a
    # container without an init may never come.
    stat = subprocess.run(
        ["ps", "-o", "stat=", "-p", str(pid)], capture_output=True, text=True,
    ).stdout.strip()
    return bool(stat) and not stat.startswith("Z")


def _gone(pid: int, within: float = 3.0) -> bool:
    deadline = time.monotonic() + within
    while time.monotonic() < deadline:
        if not _alive(pid):
            return True
        time.sleep(0.05)
    return False


def _kill(pid: int | None) -> None:
    if pid is None:
        return
    try:
        os.kill(pid, signal.SIGKILL)
    except ProcessLookupError:
        pass


def _wait_for_pid(pid_file: Path, proc: subprocess.Popen, within: float = 5.0) -> int:
    deadline = time.monotonic() + within
    while True:
        text = pid_file.read_text().strip() if pid_file.is_file() else ""
        if text:
            return int(text)
        if proc.poll() is not None or time.monotonic() > deadline:
            pytest.fail(f"the command never started (run-bounded.py exit {proc.returncode})")
        time.sleep(0.05)


class TestRunBounded:
    def _run(self, seconds: float, *cmd: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            [sys.executable, str(RUN_BOUNDED), str(seconds), *cmd],
            capture_output=True, text=True, timeout=30,
        )

    @pytest.mark.parametrize("status", [0, 3])
    def test_exits_with_the_command_status(self, status: int) -> None:
        r = self._run(5, "bash", "-c", f"exit {status}")
        assert r.returncode == status, r.stderr

    def test_expiry_exits_124_and_kills_the_command_children(self, tmp_path: Path) -> None:
        pid_file = tmp_path / "child.pid"
        start = time.monotonic()
        r = self._run(1, "bash", "-c", f'sleep 30 & echo $! > "{pid_file}"; wait')
        elapsed = time.monotonic() - start
        assert r.returncode == 124, r.stderr
        assert elapsed < 5, f"a 1 s bound took {elapsed:.1f} s"
        child = int(pid_file.read_text())
        try:
            assert _gone(child), (
                "the command's child outlived the expiry: only the direct child was killed, "
                "so a test runner's workers would keep running"
            )
        finally:
            _kill(child)

    def test_sigterm_reaches_the_command(self, tmp_path: Path) -> None:
        pid_file = tmp_path / "cmd.pid"
        proc = subprocess.Popen(
            [sys.executable, str(RUN_BOUNDED), "30",
             "bash", "-c", f'echo $$ > "{pid_file}"; exec sleep 30'],
        )
        cmd_pid = None
        try:
            cmd_pid = _wait_for_pid(pid_file, proc)
            proc.send_signal(signal.SIGTERM)
            assert proc.wait(timeout=10) == 128 + signal.SIGTERM
            assert _gone(cmd_pid), (
                "the command outlived the SIGTERM sent to run-bounded.py; a hook killed by "
                "Claude Code would orphan its test run"
            )
        finally:
            if proc.poll() is None:
                proc.kill()
            _kill(cmd_pid)


class TestStopHookWithoutGnuTimeout:
    SID = "run-bounded-stop-hook"

    def test_the_pending_test_runs_and_its_output_is_logged(
        self, tmp_path: Path, sandbox_cwd: Path,
    ) -> None:
        cache = tmp_path / "cache"
        stub_bin = tmp_path / "stub-bin"
        stub_bin.mkdir()
        calls = tmp_path / "timeout-calls"
        stub = stub_bin / "timeout"
        stub.write_text(STUB_TIMEOUT.format(calls=calls))
        stub.chmod(0o755)
        env = {
            **os.environ,
            "WRIT_CACHE_DIR": str(cache),
            "WRIT_FRICTION_LOG": str(cache / "friction.log"),
            "WRIT_LOG_ROOT": str(cache / "logs"),
            "PATH": f"{stub_bin}:{os.environ['PATH']}",
        }
        subprocess.run(
            [sys.executable, str(SESSION_HELPER), "mode", "set", "work", self.SID],
            env=env, check=True, capture_output=True, text=True,
        )

        # The runner comes from the sandbox project's own config, so the hook runs a
        # script this test controls instead of a real suite.
        ran = tmp_path / "ran"
        runner = tmp_path / "fake-runner.sh"
        runner.write_text(FAKE_RUNNER.format(ran=ran))
        runner.chmod(0o755)
        (sandbox_cwd / ".claude" / "writ.json").write_text(json.dumps({
            "patterns": [{
                "name": "fake-runner",
                "test_match": ["*/tests/test_*.py"],
                "runner_command": str(runner),
            }],
        }))
        test_file = sandbox_cwd / "tests" / "test_widget.py"
        test_file.parent.mkdir()
        test_file.write_text("def test_widget():\n    pass\n")
        session_dir = cache / self.SID
        session_dir.mkdir(parents=True, exist_ok=True)
        (session_dir / "pending-tests.txt").write_text(f"{test_file}\n")

        r = subprocess.run(
            ["bash", str(RUN_HOOK)],
            input=json.dumps({"session_id": self.SID, "hook_event_name": "Stop"}),
            capture_output=True, text=True, env=env, timeout=120,
        )

        log_path = session_dir / "last-test-run.log"
        log = log_path.read_text() if log_path.is_file() else ""
        assert ran.is_file(), (
            f"the pending test's runner never ran. exit={r.returncode} log={log!r} "
            f"stderr={r.stderr!r}"
        )
        assert "fake-runner stdout" in log and "fake-runner stderr" in log, log
        assert not calls.exists(), "the Stop hook still calls GNU timeout"


class TestNoGnuTimeout:
    def test_the_pattern_sees_both_forms_it_replaced(self) -> None:
        assert GNU_TIMEOUT.findall('if ! timeout 2 bash -c "exec 3<>/dev/tcp/h/1"; then')
        assert GNU_TIMEOUT.findall('        timeout 60s bash -c "$cmd" 2>&1')
        assert not GNU_TIMEOUT.findall('curl --connect-timeout 5 "$url"')
        assert not GNU_TIMEOUT.findall("read_timeout 3")

    def test_no_shell_file_calls_gnu_timeout(self) -> None:
        offenders = scan(
            GNU_TIMEOUT,
            roots=[REPO / d for d in SHELL_UNIVERSE.dirs],
            universe=SHELL_UNIVERSE,
            transform=lambda text: COMMENT_LINE.sub("", text),
        )
        assert offenders == {}, (
            f"stock macOS has no GNU timeout, and the shell's exit 127 reads as the "
            f"failure being checked for. Use bin/lib/run-bounded.py: {offenders}"
        )
