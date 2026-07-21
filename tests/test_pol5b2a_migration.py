"""POL-5b-2a: migrate the 7 clean content/parsed_bool hooks to load_hook_env.

Each hook drops the parse_hook_stdin + parsed_field(+parsed_bool/detect_session_id)
multi-spawn idiom for a single load_hook_env spawn; content hooks pipe $HOOK_ENVELOPE
to their own python instead of $PARSED.

RED until the hooks are migrated.
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest

SKILL_DIR = Path.home() / ".claude/skills/writ"
HOOKS = SKILL_DIR / "hooks" / "scripts"

ALL_HOOKS = [
    "validate-rules.sh",
    "validate-file.sh",
    "validate-handoff.sh",
    "writ-quality-judge.sh",
    "pre-validate-file.sh",
    "validate-design-doc.sh",
    "writ-memory-policy-guard.sh",
]
ENVELOPE_HOOKS = ["pre-validate-file.sh", "validate-design-doc.sh", "writ-memory-policy-guard.sh"]
ISERROR_HOOKS = ["validate-rules.sh", "validate-file.sh", "validate-handoff.sh"]

SAMPLE_ENV = json.dumps({
    "hook_event_name": "PreToolUse", "tool_name": "Write", "session_id": "sid-5b2a",
    "tool_input": {"file_path": "/tmp/pol5b2a_sample.txt", "content": "hello world"},
})
ISERROR_ENV = json.dumps({
    "hook_event_name": "PostToolUse", "tool_name": "Write", "session_id": "sid-5b2a",
    "tool_result_is_error": True,
    "tool_input": {"file_path": "/tmp/pol5b2a_sample.txt", "content": "hello"},
})


def _run(hook: str, envelope: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["bash", str(HOOKS / hook)],
        input=envelope, capture_output=True, text=True,
        cwd=str(SKILL_DIR),
        env={**os.environ, "WRIT_HOST": "localhost"},
        timeout=20,
    )


# --------------------------------------------------------------------------- #
# 1. migration markers
# --------------------------------------------------------------------------- #
class TestMigration:
    @pytest.mark.parametrize("hook", ALL_HOOKS)
    def test_uses_load_hook_env(self, hook: str) -> None:
        assert "load_hook_env" in (HOOKS / hook).read_text(), f"{hook} must call load_hook_env"

    @pytest.mark.parametrize("hook", ALL_HOOKS)
    def test_dropped_old_idiom(self, hook: str) -> None:
        src = (HOOKS / hook).read_text()
        for stale in ("parsed_field", "parse_hook_stdin", "detect_session_id", "parsed_bool"):
            assert stale not in src, f"{hook} must not still use {stale}"

    @pytest.mark.parametrize("hook", ENVELOPE_HOOKS)
    def test_content_hook_uses_envelope(self, hook: str) -> None:
        src = (HOOKS / hook).read_text()
        assert "HOOK_ENVELOPE" in src, f"{hook} must feed $HOOK_ENVELOPE to its python"
        assert "$PARSED" not in src, f"{hook} must not reference $PARSED after migration"

    @pytest.mark.parametrize("hook", ISERROR_HOOKS)
    def test_iserror_hook_uses_hook_is_error(self, hook: str) -> None:
        assert "HOOK_IS_ERROR" in (HOOKS / hook).read_text(), (
            f"{hook} must gate on $HOOK_IS_ERROR"
        )


# --------------------------------------------------------------------------- #
# 2. behavior preserved
# --------------------------------------------------------------------------- #
class TestBehaviorPreserved:
    @pytest.mark.parametrize("hook", ALL_HOOKS)
    def test_runs_clean_on_sample(self, hook: str) -> None:
        r = _run(hook, SAMPLE_ENV)
        assert r.returncode == 0, f"{hook} exited {r.returncode}; stderr={r.stderr[:200]!r}"

    @pytest.mark.parametrize("hook", ISERROR_HOOKS)
    def test_iserror_envelope_runs_clean(self, hook: str) -> None:
        """A failed-write envelope (is_error) must be skipped cleanly (exit 0)."""
        r = _run(hook, ISERROR_ENV)
        assert r.returncode == 0, f"{hook} exited {r.returncode} on is_error; stderr={r.stderr[:200]!r}"

    def test_pre_validate_file_processes_content(self) -> None:
        """pre-validate-file resolves the file + builds the tmpfile from envelope content."""
        r = _run("pre-validate-file.sh", SAMPLE_ENV)
        assert r.returncode == 0, f"pre-validate-file crashed: {r.stderr[:200]!r}"
