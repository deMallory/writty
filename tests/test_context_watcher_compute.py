"""Item 1: writ-context-watcher.sh threshold computation tests.

Tests that the watcher correctly computes context percent from the last
assistant message's usage fields in the transcript JSONL, and that the
WRIT_CONTEXT_WINDOW_TOKENS env var override changes the computed ratio.
"""

from __future__ import annotations

import importlib.util
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

# Default context window per plan
DEFAULT_WINDOW = 200_000


def _make_transcript(entries: list[dict], tmp_path: Path) -> Path:
    """Write a JSONL transcript file and return its path."""
    path = tmp_path / "transcript.jsonl"
    with open(path, "w") as f:
        for entry in entries:
            f.write(json.dumps(entry) + "\n")
    return path


def _make_assistant_entry(
    input_tokens: int = 0,
    cache_read: int = 0,
    cache_creation: int = 0,
) -> dict:
    """Create a synthetic assistant message entry with usage fields."""
    return {
        "type": "assistant",
        "message": {
            "role": "assistant",
            "content": [{"type": "text", "text": "Hello"}],
            "usage": {
                "input_tokens": input_tokens,
                "cache_read_input_tokens": cache_read,
                "cache_creation_input_tokens": cache_creation,
                "output_tokens": 50,
            },
        },
    }


def _run_watcher(
    transcript_path: Path,
    session_id: str,
    event_type: str = "UserPromptSubmit",
    env_overrides: dict | None = None,
) -> tuple[str, str, int]:
    """Run the context watcher hook with a constructed stdin payload."""
    payload = {
        "session_id": session_id,
        "hook_event_name": event_type,
        "transcript_path": str(transcript_path),
    }
    merged_env = {
        **os.environ,
        "SESSION_ID": session_id,
        "SKILL_DIR": str(SKILL_DIR),
        **(env_overrides or {}),
    }
    result = subprocess.run(
        ["bash", str(WATCHER_HOOK)],
        input=json.dumps(payload),
        capture_output=True, text=True,
        cwd=str(SKILL_DIR),
        env=merged_env,
        timeout=15,
    )
    return result.stdout, result.stderr, result.returncode


def _read_cache(session_id: str) -> dict:
    result = subprocess.run(
        [sys.executable, SESSION_HELPER, "read", session_id],
        capture_output=True, text=True, timeout=5,
    )
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError:
        return {}


def _cleanup_session(session_id: str) -> None:
    path = Path(tempfile.gettempdir()) / f"writ-session-{session_id}.json"
    if path.exists():
        path.unlink()


@pytest.fixture()
def session_id():
    sid = f"test-ctx-compute-{uuid.uuid4().hex[:8]}"
    yield sid
    _cleanup_session(sid)


class TestContextPercentComputation:
    """Watcher computes (input + cache_read + cache_creation) / WRIT_CONTEXT_WINDOW_TOKENS."""

    def test_percent_at_50_percent_default_window(
        self, session_id: str, tmp_path: Path
    ) -> None:
        """100k tokens / 200k window = 50% is computed correctly."""
        transcript = _make_transcript(
            [_make_assistant_entry(input_tokens=100_000)], tmp_path
        )
        _run_watcher(transcript, session_id, event_type="UserPromptSubmit")
        cache = _read_cache(session_id)
        pct = cache.get("context_percent", -1)
        assert pct == 50, (
            f"100k/200k should yield context_percent=50; got {pct}"
        )

    def test_percent_sums_all_three_token_fields(
        self, session_id: str, tmp_path: Path
    ) -> None:
        """Sum of input_tokens + cache_read + cache_creation is the numerator."""
        # 40k + 40k + 20k = 100k out of 200k = 50%
        transcript = _make_transcript(
            [_make_assistant_entry(
                input_tokens=40_000, cache_read=40_000, cache_creation=20_000
            )], tmp_path
        )
        _run_watcher(transcript, session_id, event_type="UserPromptSubmit")
        cache = _read_cache(session_id)
        pct = cache.get("context_percent", -1)
        assert pct == 50, (
            f"40k+40k+20k = 100k / 200k should yield 50%; got {pct}"
        )

    def test_percent_uses_last_assistant_entry(
        self, session_id: str, tmp_path: Path
    ) -> None:
        """Only the LAST type=assistant entry is used for computation."""
        transcript = _make_transcript([
            _make_assistant_entry(input_tokens=10_000),   # earlier entry
            {"type": "user", "message": {"content": "hello"}},
            _make_assistant_entry(input_tokens=100_000),  # last entry
        ], tmp_path)
        _run_watcher(transcript, session_id, event_type="UserPromptSubmit")
        cache = _read_cache(session_id)
        pct = cache.get("context_percent", -1)
        # Last entry has 100k tokens -> 50% of 200k default
        assert pct == 50, (
            f"Must use last assistant entry (100k/200k = 50%); got {pct}"
        )

    def test_env_override_changes_computed_percent(
        self, session_id: str, tmp_path: Path
    ) -> None:
        """WRIT_CONTEXT_WINDOW_TOKENS=1000000 yields different percent for same usage."""
        transcript = _make_transcript(
            [_make_assistant_entry(input_tokens=100_000)], tmp_path
        )
        _run_watcher(
            transcript, session_id, event_type="UserPromptSubmit",
            env_overrides={"WRIT_CONTEXT_WINDOW_TOKENS": "1000000"},
        )
        cache = _read_cache(session_id)
        pct = cache.get("context_percent", -1)
        # 100k / 1000k = 10%
        assert pct == 10, (
            f"100k/1000k should yield context_percent=10; got {pct}"
        )

    def test_default_window_200k_when_env_not_set(
        self, session_id: str, tmp_path: Path
    ) -> None:
        """Default window of 200000 applies when env var is absent."""
        transcript = _make_transcript(
            [_make_assistant_entry(input_tokens=200_000)], tmp_path
        )
        env = {k: v for k, v in os.environ.items() if k != "WRIT_CONTEXT_WINDOW_TOKENS"}
        env["SESSION_ID"] = session_id
        env["SKILL_DIR"] = str(SKILL_DIR)

        payload = {
            "session_id": session_id,
            "hook_event_name": "UserPromptSubmit",
            "transcript_path": str(transcript),
        }
        subprocess.run(
            ["bash", str(WATCHER_HOOK)],
            input=json.dumps(payload),
            capture_output=True, text=True,
            cwd=str(SKILL_DIR), env=env, timeout=15,
        )
        cache = _read_cache(session_id)
        pct = cache.get("context_percent", -1)
        # 200k / 200k = 100%
        assert pct == 100, (
            f"200k/200k default window should yield 100%; got {pct}"
        )

    def test_empty_transcript_does_not_crash(
        self, session_id: str, tmp_path: Path
    ) -> None:
        """Empty transcript produces no crash (context_percent stays 0 or absent)."""
        transcript = _make_transcript([], tmp_path)
        _stdout, stderr, code = _run_watcher(
            transcript, session_id, event_type="UserPromptSubmit"
        )
        assert "Traceback" not in stderr, (
            f"Watcher must not traceback on empty transcript; stderr={stderr!r}"
        )
        assert code in (0, 1), (
            f"Empty transcript must exit cleanly (0 or 1); got {code}"
        )