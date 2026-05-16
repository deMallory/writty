"""Item 1: writ-context-watcher.sh 75% warning + subagent gating.

History: this file originally pinned the 75% hard-block semantics
(exit 2 on PreToolUse). Post-v1.2.0 follow-up, the 75% threshold was
demoted from a hard block to a non-blocking stderr warning. The file
name is kept for git-history continuity; tests now verify:

- PreToolUse exits 0 at every pct (no blocking).
- 75% pct still emits a stderr warning (visible red text).
- When cache.get('is_subagent') is True, watcher emits nothing.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import uuid
from pathlib import Path

import pytest

SKILL_DIR = Path("/home/lucio.saldivar/.claude/skills/writ")
WATCHER_HOOK = SKILL_DIR / ".claude" / "hooks" / "writ-context-watcher.sh"
SESSION_HELPER = str(SKILL_DIR / "bin" / "lib" / "writ-session.py")


def _make_transcript(input_tokens: int, tmp_path: Path, label: str = "t") -> Path:
    path = tmp_path / f"transcript_{label}.jsonl"
    entry = {
        "type": "assistant",
        "message": {
            "role": "assistant",
            "content": [{"type": "text", "text": "x"}],
            "usage": {
                "input_tokens": input_tokens,
                "cache_read_input_tokens": 0,
                "cache_creation_input_tokens": 0,
                "output_tokens": 10,
            },
        },
    }
    with open(path, "w") as f:
        f.write(json.dumps(entry) + "\n")
    return path


def _run_watcher(
    transcript_path: Path,
    session_id: str,
    event_type: str = "PreToolUse",
    window: int = 200_000,
    extra_env: dict | None = None,
) -> tuple[str, str, int]:
    payload = {
        "session_id": session_id,
        "hook_event_name": event_type,
        "transcript_path": str(transcript_path),
    }
    env = {
        **os.environ,
        "SESSION_ID": session_id,
        "SKILL_DIR": str(SKILL_DIR),
        "WRIT_CONTEXT_WINDOW_TOKENS": str(window),
        **(extra_env or {}),
    }
    result = subprocess.run(
        ["bash", str(WATCHER_HOOK)],
        input=json.dumps(payload),
        capture_output=True, text=True,
        cwd=str(SKILL_DIR), env=env, timeout=15,
    )
    return result.stdout, result.stderr, result.returncode


def _set_session_subagent(session_id: str, is_subagent: bool) -> None:
    """Write is_subagent into the session cache."""
    subprocess.run(
        [sys.executable, SESSION_HELPER, "update", session_id,
         "--is-subagent", str(is_subagent).lower()],
        capture_output=True, timeout=5,
    )


def _cleanup_session(session_id: str) -> None:
    path = Path(tempfile.gettempdir()) / f"writ-session-{session_id}.json"
    if path.exists():
        path.unlink()


@pytest.fixture()
def session_id():
    sid = f"test-ctx-block-{uuid.uuid4().hex[:8]}"
    yield sid
    _cleanup_session(sid)


class TestSeventyFivePercentWarning:
    """PreToolUse never blocks; 75% emits a stderr warning."""

    def test_pretooluse_exits_0_at_75_pct(
        self, session_id: str, tmp_path: Path
    ) -> None:
        """pct=75 on PreToolUse must NOT block (exit 0)."""
        transcript = _make_transcript(150_000, tmp_path, "75pct")
        _stdout, stderr, code = _run_watcher(
            transcript, session_id, event_type="PreToolUse"
        )
        assert code == 0, (
            f"PreToolUse at 75% must exit 0 (no hard block); got {code}. "
            f"stderr={stderr[:500]!r}"
        )

    def test_pretooluse_exits_0_above_75_pct(
        self, session_id: str, tmp_path: Path
    ) -> None:
        """pct=90 on PreToolUse must also exit 0."""
        transcript = _make_transcript(180_000, tmp_path, "90pct")
        _stdout, _stderr, code = _run_watcher(
            transcript, session_id, event_type="PreToolUse"
        )
        assert code == 0, f"PreToolUse at 90% must exit 0; got {code}"

    def test_pretooluse_exits_0_below_75_pct(
        self, session_id: str, tmp_path: Path
    ) -> None:
        """pct=50 on PreToolUse exits 0."""
        transcript = _make_transcript(100_000, tmp_path, "50pct")
        _stdout, _stderr, code = _run_watcher(
            transcript, session_id, event_type="PreToolUse"
        )
        assert code == 0, f"PreToolUse at 50% must exit 0; got {code}"

    def test_pretooluse_exits_0_at_74_pct(
        self, session_id: str, tmp_path: Path
    ) -> None:
        """pct=74 (just under 75% floor) on PreToolUse exits 0."""
        tokens_74pct = int(200_000 * 0.74)
        transcript = _make_transcript(tokens_74pct, tmp_path, "74pct")
        _stdout, _stderr, code = _run_watcher(
            transcript, session_id, event_type="PreToolUse"
        )
        assert code == 0, f"PreToolUse at 74% must exit 0; got {code}"

    def test_75_warning_emits_to_stderr(
        self, session_id: str, tmp_path: Path
    ) -> None:
        """75% warning produces a non-empty stderr message (visible red text)."""
        transcript = _make_transcript(150_000, tmp_path, "warn_stderr")
        _stdout, stderr, code = _run_watcher(
            transcript, session_id, event_type="PreToolUse"
        )
        assert code == 0
        assert len(stderr.strip()) > 0, (
            "75% must emit a warning message on stderr"
        )


class TestSubagentGating:
    """When is_subagent is True, watcher emits nothing and never blocks."""

    def test_subagent_pretooluse_exits_0_at_90_pct(
        self, session_id: str, tmp_path: Path
    ) -> None:
        """Subagent at 90% context on PreToolUse exits 0 (no block, no warning)."""
        _set_session_subagent(session_id, True)
        transcript = _make_transcript(180_000, tmp_path, "sub_90pct")
        _stdout, _stderr, code = _run_watcher(
            transcript, session_id, event_type="PreToolUse"
        )
        assert code == 0, (
            f"Subagent PreToolUse at 90% must exit 0 (no block); got {code}"
        )

    def test_subagent_userpromptsubmit_no_directive(
        self, session_id: str, tmp_path: Path
    ) -> None:
        """Subagent at 55% context on UserPromptSubmit produces no directive."""
        _set_session_subagent(session_id, True)
        transcript = _make_transcript(110_000, tmp_path, "sub_55pct")
        stdout, stderr, code = _run_watcher(
            transcript, session_id, event_type="UserPromptSubmit"
        )
        assert code == 0, (
            f"Subagent UserPromptSubmit must exit 0; got {code}"
        )
        combined = stdout + stderr
        assert "context" not in combined.lower() or len(combined.strip()) == 0, (
            "Subagent watcher must not emit context directive; "
            f"output={combined[:300]!r}"
        )

    def test_subagent_skip_regardless_of_pct(
        self, session_id: str, tmp_path: Path
    ) -> None:
        """is_subagent=True causes skip even at 100% context."""
        _set_session_subagent(session_id, True)
        transcript = _make_transcript(200_000, tmp_path, "sub_100pct")
        _stdout, _stderr, code = _run_watcher(
            transcript, session_id, event_type="PreToolUse"
        )
        assert code == 0, (
            f"Subagent at 100% must still exit 0 (never blocked); got {code}"
        )
