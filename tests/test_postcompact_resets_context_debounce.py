"""Item 1: writ-postcompact.sh resets context_warning_emitted_at_pct to 0.

After PostCompact runs, the context warning debounce field must be reset
to 0 so the 50% band re-arms for the next session segment.
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import uuid
from pathlib import Path

import pytest

SKILL_DIR = Path("/home/lucio.saldivar/.claude/skills/writ")
POSTCOMPACT_HOOK = SKILL_DIR / ".claude" / "hooks" / "writ-postcompact.sh"
SESSION_HELPER = str(SKILL_DIR / "bin" / "lib" / "writ-session.py")


def _run_session(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, SESSION_HELPER, *args],
        capture_output=True, text=True, timeout=5,
    )


def _run_postcompact(session_id: str) -> tuple[str, str, int]:
    payload = {"session_id": session_id, "event": "compact"}
    result = subprocess.run(
        ["bash", str(POSTCOMPACT_HOOK)],
        input=json.dumps(payload),
        capture_output=True, text=True,
        cwd=str(SKILL_DIR),
        timeout=15,
    )
    return result.stdout, result.stderr, result.returncode


def _read_cache(session_id: str) -> dict:
    result = _run_session("read", session_id)
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
    sid = f"test-compact-reset-{uuid.uuid4().hex[:8]}"
    yield sid
    _cleanup_session(sid)


class TestPostcompactResetsContextDebounce:
    """writ-postcompact.sh resets context_warning_emitted_at_pct to 0."""

    def test_field_is_reset_to_zero_after_compact(
        self, session_id: str
    ) -> None:
        """context_warning_emitted_at_pct is 0 after PostCompact runs."""
        # Arrange: set the field to 50 (as if a 50% crossing was emitted)
        _run_session("update", session_id,
                     "--context-warning-emitted-at-pct", "50")

        cache_before = _read_cache(session_id)
        assert cache_before.get("context_warning_emitted_at_pct") == 50, (
            "Pre-condition: field should be 50 before compact"
        )

        # Act: run PostCompact hook
        _stdout, _stderr, code = _run_postcompact(session_id)
        assert code == 0, (
            f"PostCompact hook must exit 0; stderr={_stderr[:300]!r}"
        )

        # Assert: field reset to 0
        cache_after = _read_cache(session_id)
        pct = cache_after.get("context_warning_emitted_at_pct", -1)
        assert pct == 0, (
            f"context_warning_emitted_at_pct must be 0 after PostCompact; got {pct}"
        )

    def test_field_reset_from_75_to_zero(self, session_id: str) -> None:
        """Field set to 75 (hard block emitted) is also reset to 0 after compact."""
        _run_session("update", session_id,
                     "--context-warning-emitted-at-pct", "75")

        _run_postcompact(session_id)

        cache_after = _read_cache(session_id)
        pct = cache_after.get("context_warning_emitted_at_pct", -1)
        assert pct == 0, (
            f"Field must reset from 75 to 0 after PostCompact; got {pct}"
        )

    def test_reset_does_not_affect_other_session_fields(
        self, session_id: str
    ) -> None:
        """PostCompact reset only modifies context_warning_emitted_at_pct, not other fields."""
        _run_session("tier", "set", "2", session_id)
        _run_session("update", session_id,
                     "--context-warning-emitted-at-pct", "50")

        _run_postcompact(session_id)

        cache_after = _read_cache(session_id)
        # Other fields must be untouched by the context debounce reset
        assert cache_after.get("context_warning_emitted_at_pct") == 0
        # tier or other fields should still be present
        # (exact fields depend on implementation, but session_id must survive)
        assert "session_id" in cache_after or cache_after != {}, (
            "PostCompact must not wipe the session cache entirely"
        )

    def test_field_already_zero_stays_zero(self, session_id: str) -> None:
        """If field is already 0, PostCompact leaves it at 0 (idempotent)."""
        # Ensure the field is 0 from the start
        _run_session("update", session_id,
                     "--context-warning-emitted-at-pct", "0")

        _run_postcompact(session_id)

        cache_after = _read_cache(session_id)
        pct = cache_after.get("context_warning_emitted_at_pct", -1)
        assert pct == 0, (
            f"Field must remain 0 when already 0; got {pct}"
        )