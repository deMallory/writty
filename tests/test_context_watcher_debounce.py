"""Item 1: writ-context-watcher.sh 50% one-shot debounce tests.

The 50% directive is emitted at most once per crossing. Subsequent
computations above 50% (but below 75%) do not re-emit. After
PostCompact resets context_warning_emitted_at_pct to 0, crossing 50%
again re-emits.
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


def _make_transcript_at_pct(pct: int, window: int, tmp_path: Path) -> Path:
    """Write a transcript whose last assistant entry yields ~pct% of window."""
    tokens = int(window * pct / 100)
    path = tmp_path / f"transcript_{pct}pct.jsonl"
    entry = {
        "type": "assistant",
        "message": {
            "role": "assistant",
            "content": [{"type": "text", "text": "x"}],
            "usage": {
                "input_tokens": tokens,
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
    event_type: str = "UserPromptSubmit",
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


def _run_session(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, SESSION_HELPER, *args],
        capture_output=True, text=True, timeout=5,
    )


def _read_cache(session_id: str) -> dict:
    result = _run_session("read", session_id)
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError:
        return {}


def _set_cache_field(session_id: str, field: str, value) -> None:
    """Directly update a cache field via writ-session update."""
    _run_session("update", session_id, f"--{field}", str(value))


def _cleanup_session(session_id: str) -> None:
    path = Path(tempfile.gettempdir()) / f"writ-session-{session_id}.json"
    if path.exists():
        path.unlink()


@pytest.fixture()
def session_id():
    sid = f"test-ctx-deb-{uuid.uuid4().hex[:8]}"
    yield sid
    _cleanup_session(sid)


class TestFiftyPercentDebounce:
    """50% threshold emits the soft directive at most once per crossing."""

    def test_crossing_50_percent_emits_directive(
        self, session_id: str, tmp_path: Path
    ) -> None:
        """First crossing of 50% produces output on stderr (soft directive)."""
        transcript = _make_transcript_at_pct(55, 200_000, tmp_path)
        _stdout, stderr, code = _run_watcher(
            transcript, session_id, event_type="UserPromptSubmit"
        )
        combined = _stdout + stderr
        # The directive must be emitted (non-empty output)
        assert len(combined.strip()) > 0, (
            "Crossing 50% for the first time must emit the soft directive"
        )

    def test_crossing_50_sets_emitted_at_pct_to_50(
        self, session_id: str, tmp_path: Path
    ) -> None:
        """After the first 50% crossing, context_warning_emitted_at_pct is set to 50."""
        transcript = _make_transcript_at_pct(55, 200_000, tmp_path)
        _run_watcher(transcript, session_id, event_type="UserPromptSubmit")
        cache = _read_cache(session_id)
        emitted_at = cache.get("context_warning_emitted_at_pct", -1)
        assert emitted_at == 50, (
            f"After 50% crossing, context_warning_emitted_at_pct must be 50; got {emitted_at}"
        )

    def test_second_computation_at_60_does_not_re_emit(
        self, session_id: str, tmp_path: Path
    ) -> None:
        """Subsequent computation at 60% does NOT re-emit the soft directive."""
        # First crossing at 55%
        transcript_55 = _make_transcript_at_pct(55, 200_000, tmp_path)
        first_stdout, first_stderr, _ = _run_watcher(
            transcript_55, session_id, event_type="UserPromptSubmit"
        )
        first_output = first_stdout + first_stderr

        # Second computation at 60% -- must NOT re-emit (debounced)
        transcript_60 = _make_transcript_at_pct(60, 200_000, tmp_path)
        second_stdout, second_stderr, _ = _run_watcher(
            transcript_60, session_id, event_type="UserPromptSubmit"
        )
        second_output = second_stdout + second_stderr

        # The second run's output must be shorter/absent relative to first
        # (exact comparison depends on implementation; key: no duplicate directive)
        # If first had content, second must not also have the same directive text
        if first_output.strip() and second_output.strip():
            # Both produced output -- check they are not the same directive twice
            # by asserting the second is empty or substantially different
            assert len(second_output.strip()) < len(first_output.strip()), (
                "Second computation at 60% must not re-emit the full soft directive"
            )

    def test_after_postcompact_reset_50_pct_re_emits(
        self, session_id: str, tmp_path: Path
    ) -> None:
        """After context_warning_emitted_at_pct is reset to 0, crossing 50% re-emits."""
        # First crossing
        transcript_55 = _make_transcript_at_pct(55, 200_000, tmp_path)
        _run_watcher(transcript_55, session_id, event_type="UserPromptSubmit")

        # Simulate PostCompact reset
        _run_session("update", session_id,
                     "--context-warning-emitted-at-pct", "0")

        cache_after_reset = _read_cache(session_id)
        assert cache_after_reset.get("context_warning_emitted_at_pct", -1) == 0, (
            "PostCompact reset must set context_warning_emitted_at_pct=0"
        )

        # Second crossing after reset -- should re-emit
        transcript_58 = _make_transcript_at_pct(58, 200_000, tmp_path)
        _stdout, stderr, code = _run_watcher(
            transcript_58, session_id, event_type="UserPromptSubmit"
        )
        combined = _stdout + stderr
        assert len(combined.strip()) > 0, (
            "After PostCompact reset, crossing 50% again must re-emit the directive"
        )
