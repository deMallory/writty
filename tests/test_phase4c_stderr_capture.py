"""Phase 4c D1: stderr capture extension to Task / Subagent hooks.

PSR-004 surfaced PreToolUse:Agent hook tracebacks during sub-agent
dispatches. The Task-matcher hook (writ-sdd-review-order.sh) and
SubagentStart/Stop hooks need the same diagnostic stderr-tee that
writ-pre-write-dispatch.sh got in Phase 4b. Verifies all three
redirect stderr to /tmp/writ-hook-debug.log without changing
behavior.
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

WRIT_ROOT = Path(__file__).resolve().parent.parent
HOOKS = WRIT_ROOT / ".claude" / "hooks"
DEBUG_LOG = Path("/tmp/writ-hook-debug.log")


HOOKS_TO_CHECK = [
    "writ-sdd-review-order.sh",
    "writ-subagent-start.sh",
    "writ-subagent-stop.sh",
]


@pytest.fixture(autouse=True)
def truncate_debug_log():
    """Start each test with a clean debug log so writes are isolated."""
    if DEBUG_LOG.exists():
        DEBUG_LOG.unlink()
    yield


class TestStderrTeePresent:
    """Each target hook must contain the tee directive at the top."""

    @pytest.mark.parametrize("hook_name", HOOKS_TO_CHECK)
    def test_hook_redirects_stderr_to_debug_log(self, hook_name: str) -> None:
        """The hook source must contain the exec 2> >(tee ...) line."""
        path = HOOKS / hook_name
        assert path.exists(), f"{hook_name} does not exist"
        content = path.read_text()
        # Match either single-line or split form of the tee redirect
        has_tee = (
            "tee -a /tmp/writ-hook-debug.log" in content
            or "tee -a $HOME/writ-hook-debug.log" in content
            or "tee -a \"/tmp/writ-hook-debug.log\"" in content
        )
        assert has_tee, (
            f"{hook_name} must redirect stderr via tee to "
            "/tmp/writ-hook-debug.log so tracebacks are diagnosable"
        )

    @pytest.mark.parametrize("hook_name", HOOKS_TO_CHECK)
    def test_hook_syntax_valid(self, hook_name: str) -> None:
        proc = subprocess.run(
            ["bash", "-n", str(HOOKS / hook_name)],
            capture_output=True, text=True,
        )
        assert proc.returncode == 0, f"{hook_name} syntax error: {proc.stderr}"


class TestStderrTeeIdiomWorks:
    """Verify the bash idiom itself, not the production hook (which has
    relative-path dependencies that break under copy-and-modify).

    The hooks contain `exec 2> >(tee -a /tmp/writ-hook-debug.log >&2)`.
    This test creates a minimal script with the same idiom + a known
    stderr write, runs it, and asserts the log captured the line.
    """

    def test_tee_idiom_captures_stderr(self, tmp_path: Path) -> None:
        marker = "PHASE4C_TEE_IDIOM_TEST_MARKER"
        script = tmp_path / "fake-hook.sh"
        script.write_text(f"""#!/usr/bin/env bash
set -euo pipefail
exec 2> >(tee -a /tmp/writ-hook-debug.log >&2)
printf '%s\\n' "{marker}" >&2
exit 0
""")
        script.chmod(0o755)

        proc = subprocess.run([str(script)], capture_output=True, text=True, timeout=5)
        assert proc.returncode == 0, f"idiom script failed: {proc.stderr}"
        # Marker is in stderr (tee preserves it) AND in the debug log.
        assert marker in proc.stderr
        assert DEBUG_LOG.exists(), "debug log was not created"
        assert marker in DEBUG_LOG.read_text(), (
            f"marker {marker!r} not found in {DEBUG_LOG}"
        )


class TestPreWriteDispatchStillCovered:
    """Phase 4b tee on writ-pre-write-dispatch.sh is preserved."""

    def test_pre_write_dispatch_still_has_tee(self) -> None:
        content = (HOOKS / "writ-pre-write-dispatch.sh").read_text()
        assert "tee -a /tmp/writ-hook-debug.log" in content, (
            "Phase 4b tee on writ-pre-write-dispatch.sh must remain"
        )