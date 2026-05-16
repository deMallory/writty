"""Item 1: writ-context-watcher.sh verbatim message pinning.

The 50% and 75% threshold warnings must match the approved text. These
tests pin the key phrases so a copy-edit does not silently diverge from
the specification. Post-v1.2.0 follow-up, 75% is a non-blocking warning
(not a hard block).

If the implementer changes the approved text, these tests must be
updated in the same commit.
"""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
import uuid
from pathlib import Path

import pytest

SKILL_DIR = Path("/home/lucio.saldivar/.claude/skills/writ")
WATCHER_HOOK = SKILL_DIR / ".claude" / "hooks" / "writ-context-watcher.sh"

# ---------------------------------------------------------------------------
# Approved verbatim message fragments.
# ---------------------------------------------------------------------------

# 50% warning: key phrases that must appear
SOFT_DIRECTIVE_PHRASES = [
    "context",                  # must mention context
    "50",                       # must reference 50% threshold
    "compact",                  # must instruct /compact as the relief valve
    "performance regressions",  # new v1.2.0-followup wording
]

# 75% warning: key phrases that must appear (no blocking, but still warns)
HARD_BLOCK_PHRASES = [
    "context",                  # must mention context
    "75",                       # must reference 75% threshold
    "compact",                  # must name the relief action
    "stopping point",           # new v1.2.0-followup wording
]


def _make_transcript(input_tokens: int, tmp_path: Path, label: str = "msg") -> Path:
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
    event_type: str,
    window: int = 200_000,
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
    }
    result = subprocess.run(
        ["bash", str(WATCHER_HOOK)],
        input=json.dumps(payload),
        capture_output=True, text=True,
        cwd=str(SKILL_DIR), env=env, timeout=15,
    )
    return result.stdout, result.stderr, result.returncode


def _cleanup_session(session_id: str) -> None:
    path = Path(tempfile.gettempdir()) / f"writ-session-{session_id}.json"
    if path.exists():
        path.unlink()


@pytest.fixture()
def session_id():
    sid = f"test-ctx-msg-{uuid.uuid4().hex[:8]}"
    yield sid
    _cleanup_session(sid)


class TestFiftyPercentWarningMessage:
    """50% warning (UserPromptSubmit) contains approved key phrases."""

    def test_warning_contains_context_phrase(
        self, session_id: str, tmp_path: Path
    ) -> None:
        """50% warning references 'context' in the emitted message."""
        transcript = _make_transcript(110_000, tmp_path, "soft_ctx")
        stdout, stderr, _ = _run_watcher(
            transcript, session_id, event_type="UserPromptSubmit"
        )
        combined = (stdout + stderr).lower()
        assert "context" in combined, (
            f"50% warning must mention 'context'; got: {combined[:400]!r}"
        )

    def test_warning_references_threshold(
        self, session_id: str, tmp_path: Path
    ) -> None:
        """50% warning references the 50% threshold."""
        transcript = _make_transcript(110_000, tmp_path, "soft_thr")
        stdout, stderr, _ = _run_watcher(
            transcript, session_id, event_type="UserPromptSubmit"
        )
        combined = stdout + stderr
        assert "50" in combined or "fifty" in combined.lower(), (
            f"50% warning must reference the 50 threshold; got: {combined[:400]!r}"
        )

    def test_warning_mentions_compact(
        self, session_id: str, tmp_path: Path
    ) -> None:
        """50% warning instructs the user to run /compact."""
        transcript = _make_transcript(110_000, tmp_path, "soft_compact")
        stdout, stderr, _ = _run_watcher(
            transcript, session_id, event_type="UserPromptSubmit"
        )
        combined = (stdout + stderr).lower()
        assert "compact" in combined, (
            f"50% warning must mention /compact; got: {combined[:400]!r}"
        )

    def test_warning_mentions_performance_regression(
        self, session_id: str, tmp_path: Path
    ) -> None:
        """50% warning includes the approved 'performance regressions' phrasing."""
        transcript = _make_transcript(110_000, tmp_path, "soft_perf")
        stdout, stderr, _ = _run_watcher(
            transcript, session_id, event_type="UserPromptSubmit"
        )
        combined = (stdout + stderr).lower()
        assert "performance regressions" in combined, (
            f"50% warning must include 'performance regressions'; got: {combined[:400]!r}"
        )

    def test_warning_is_emitted_to_stderr(
        self, session_id: str, tmp_path: Path
    ) -> None:
        """50% warning is emitted on stderr (not stdout)."""
        transcript = _make_transcript(110_000, tmp_path, "soft_channel")
        _stdout, stderr, _ = _run_watcher(
            transcript, session_id, event_type="UserPromptSubmit"
        )
        assert len(stderr.strip()) > 0, (
            "50% warning must appear on stderr"
        )


class TestSeventyFivePercentWarningMessage:
    """75% warning (any event) contains approved key phrases and does NOT block."""

    def test_warning_contains_context_phrase(
        self, session_id: str, tmp_path: Path
    ) -> None:
        """75% warning references 'context'."""
        transcript = _make_transcript(150_000, tmp_path, "hard_ctx")
        stdout, stderr, code = _run_watcher(
            transcript, session_id, event_type="PreToolUse"
        )
        assert code == 0, f"75% must NOT block; got exit {code}"
        combined = (stdout + stderr).lower()
        assert "context" in combined, (
            f"75% warning must mention 'context'; got: {combined[:400]!r}"
        )

    def test_warning_references_threshold(
        self, session_id: str, tmp_path: Path
    ) -> None:
        """75% warning references the 75% threshold."""
        transcript = _make_transcript(150_000, tmp_path, "hard_thr")
        stdout, stderr, code = _run_watcher(
            transcript, session_id, event_type="PreToolUse"
        )
        assert code == 0
        combined = stdout + stderr
        assert "75" in combined, (
            f"75% warning must reference 75 threshold; got: {combined[:400]!r}"
        )

    def test_warning_mentions_compact(
        self, session_id: str, tmp_path: Path
    ) -> None:
        """75% warning instructs the user to /compact."""
        transcript = _make_transcript(150_000, tmp_path, "hard_compact")
        stdout, stderr, code = _run_watcher(
            transcript, session_id, event_type="PreToolUse"
        )
        assert code == 0
        combined = (stdout + stderr).lower()
        assert "compact" in combined, (
            f"75% warning must mention /compact; got: {combined[:400]!r}"
        )

    def test_warning_mentions_stopping_point(
        self, session_id: str, tmp_path: Path
    ) -> None:
        """75% warning instructs the agent to come to a stopping point."""
        transcript = _make_transcript(150_000, tmp_path, "hard_stop")
        stdout, stderr, code = _run_watcher(
            transcript, session_id, event_type="PreToolUse"
        )
        assert code == 0
        combined = (stdout + stderr).lower()
        assert "stopping point" in combined, (
            f"75% warning must include 'stopping point'; got: {combined[:400]!r}"
        )

    def test_warning_emitted_to_stderr(
        self, session_id: str, tmp_path: Path
    ) -> None:
        """75% warning is emitted on stderr."""
        transcript = _make_transcript(150_000, tmp_path, "hard_channel")
        _stdout, stderr, code = _run_watcher(
            transcript, session_id, event_type="PreToolUse"
        )
        assert code == 0
        assert len(stderr.strip()) > 0, (
            "75% warning must appear on stderr"
        )
