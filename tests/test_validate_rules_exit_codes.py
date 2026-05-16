"""Item 2a: validate-rules.sh exit-code behavior in boundary mode.

The sentinel-file fix ensures that boundary mode exits 0 when no
finding triggers gate-invalidation, and exits 2 only when the sentinel
is written (at least one finding was routed to invalidate-gate).
"""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
import uuid

import pytest

SKILL_DIR = os.path.join(os.path.dirname(__file__), "..")
VALIDATE_HOOK = os.path.join(SKILL_DIR, ".claude", "hooks", "validate-rules.sh")
SESSION_HELPER = os.path.join(SKILL_DIR, "bin", "lib", "writ-session.py")


def _run_session(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["python3", SESSION_HELPER, *args],
        capture_output=True, text=True, timeout=10,
    )


def _run_hook(stdin_payload: dict, env: dict | None = None) -> tuple[str, str, int]:
    merged_env = {**os.environ, **(env or {})}
    proc = subprocess.run(
        ["bash", VALIDATE_HOOK],
        input=json.dumps(stdin_payload),
        capture_output=True, text=True,
        cwd=SKILL_DIR,
        env=merged_env,
        timeout=30,
    )
    return proc.stdout, proc.stderr, proc.returncode


@pytest.fixture()
def session_id():
    sid = f"test-vr-exit-{uuid.uuid4().hex[:10]}"
    yield sid
    path = os.path.join(tempfile.gettempdir(), f"writ-session-{sid}.json")
    if os.path.exists(path):
        os.remove(path)
    sentinel = os.path.join(tempfile.gettempdir(), f"writ-validate-rules-invalidated-{sid}")
    if os.path.exists(sentinel):
        os.remove(sentinel)


class TestBoundaryModeExitCode:
    """validate-rules.sh exits 0 in boundary mode when no gate invalidation occurs."""

    def test_no_violations_boundary_mode_exits_zero(self, session_id: str) -> None:
        """Boundary mode with no findings routed to invalidate-gate exits 0, not 2."""
        # Arrange: session in boundary mode with no pending violations
        _run_session("tier", "set", "2", session_id)
        payload = {
            "session_id": session_id,
            "tool_input": {
                "file_path": "/tmp/clean_boundary.py",
                "content": "# no violations here\ndef hello(): pass\n",
            },
        }
        env = {"SESSION_ID": session_id, "SKILL_DIR": SKILL_DIR}

        # Act
        _stdout, _stderr, code = _run_hook(payload, env)

        # Assert: boundary mode with no invalidations must exit 0
        assert code == 0, (
            f"validate-rules.sh must exit 0 in boundary mode with no gate invalidations; "
            f"got {code}. stderr={_stderr[:500]!r}"
        )

    def test_gate_invalidation_sentinel_causes_exit_two(self, session_id: str) -> None:
        """When the sentinel file is present (gate invalidated), hook exits 2."""
        # Arrange: pre-write the sentinel file as the gate-invalidation block would
        sentinel_path = os.path.join(
            tempfile.gettempdir(), f"writ-validate-rules-invalidated-{session_id}"
        )
        with open(sentinel_path, "w") as f:
            f.write("invalidated")

        _run_session("tier", "set", "2", session_id)
        payload = {
            "session_id": session_id,
            "tool_input": {
                "file_path": "/tmp/violating_file.py",
                "content": "x = 1\n",
            },
        }
        env = {"SESSION_ID": session_id, "SKILL_DIR": SKILL_DIR}

        # Act
        _stdout, _stderr, code = _run_hook(payload, env)

        # Assert: sentinel present -> must exit 2 (non-blocking hook error)
        assert code == 2, (
            f"validate-rules.sh must exit 2 when gate-invalidation sentinel is present; "
            f"got {code}. stderr={_stderr[:500]!r}"
        )

    def test_sentinel_file_removed_after_read(self, session_id: str) -> None:
        """The sentinel file is deleted after validate-rules.sh reads it."""
        sentinel_path = os.path.join(
            tempfile.gettempdir(), f"writ-validate-rules-invalidated-{session_id}"
        )
        with open(sentinel_path, "w") as f:
            f.write("invalidated")

        _run_session("tier", "set", "2", session_id)
        payload = {
            "session_id": session_id,
            "tool_input": {"file_path": "/tmp/f.py", "content": "pass\n"},
        }
        env = {"SESSION_ID": session_id, "SKILL_DIR": SKILL_DIR}

        _run_hook(payload, env)

        # Assert: sentinel must be cleaned up so a second run does not re-exit-2
        assert not os.path.exists(sentinel_path), (
            "Sentinel file must be deleted after validate-rules.sh reads it"
        )

    def test_second_run_after_sentinel_removed_exits_zero(self, session_id: str) -> None:
        """After the sentinel is consumed, a subsequent boundary-mode run exits 0."""
        sentinel_path = os.path.join(
            tempfile.gettempdir(), f"writ-validate-rules-invalidated-{session_id}"
        )
        # Write and consume the sentinel via the first run
        with open(sentinel_path, "w") as f:
            f.write("invalidated")
        _run_session("tier", "set", "2", session_id)
        payload = {
            "session_id": session_id,
            "tool_input": {"file_path": "/tmp/f.py", "content": "pass\n"},
        }
        env = {"SESSION_ID": session_id, "SKILL_DIR": SKILL_DIR}
        _run_hook(payload, env)

        # Act: second run with no sentinel
        _stdout, _stderr, code = _run_hook(payload, env)

        assert code == 0, (
            f"Second boundary-mode run (no sentinel) must exit 0; got {code}"
        )
