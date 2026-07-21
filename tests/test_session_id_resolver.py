"""PIECE 1: resolve_current_session_id() -- the canonical current-session resolver.

Ordering (first non-empty wins), per plan.md:
  1. $CLAUDE_SESSION_ID          (per-process; authoritative if CC sets it)
  2. basename($CLAUDE_JOB_DIR)   (per-job; concurrency-safe; trailing / stripped)
  3. /tmp/writ-current-session   (payload-derived pointer; shared-global)
  4. newest writ-session-*.json  (mtime glob; last resort; racy)
Returns None when nothing resolves.

`writ.session.cache.resolve_current_session_id` does not exist yet -- this file is RED
until PIECE 1 lands. Per TEST-TDD-001: skeletons approved before implementation.

Hermetic: WRIT_CACHE_DIR is monkeypatched to tmp_path (same mechanism as
tests/test_pol6b2_cache_dir_env.py) so writ-session-*.json glob candidates never touch
the real /tmp. The pointer file is expected to live behind a module-level constant
(named _SESSION_POINTER_PATH here) so it too can be monkeypatched to a tmp_path file
instead of the real /tmp/writ-current-session -- no real /tmp path is ever read or
written by this suite.
"""

from __future__ import annotations

import os

import pytest

from writ.session import cache


def _pointer_path(tmp_path, monkeypatch) -> str:
    """Point the resolver's pointer-file constant at a tmp_path file.

    Assumes the resolver reads a module-level path constant (not a hardcoded
    literal) so tests never touch the real /tmp/writ-current-session. If PIECE 1
    lands with a different seam name, this helper (and only this helper) needs
    updating -- the test bodies stay unchanged.
    """
    pointer = tmp_path / "writ-current-session"
    monkeypatch.setattr(cache, "_SESSION_POINTER_PATH", str(pointer), raising=False)
    return str(pointer)


@pytest.fixture(autouse=True)
def _isolated_cache_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("WRIT_CACHE_DIR", str(tmp_path))
    monkeypatch.delenv("CLAUDE_SESSION_ID", raising=False)
    monkeypatch.delenv("CLAUDE_JOB_DIR", raising=False)
    yield


class TestResolverExists:
    def test_resolver_is_importable_and_callable(self):
        assert callable(cache.resolve_current_session_id)


class TestEnvSessionIdWins:
    def test_returns_claude_session_id_when_set_and_nonempty(self, monkeypatch):
        monkeypatch.setenv("CLAUDE_SESSION_ID", "sid-from-env-123")
        assert cache.resolve_current_session_id() == "sid-from-env-123"

    def test_env_session_id_wins_over_job_dir(self, monkeypatch):
        monkeypatch.setenv("CLAUDE_SESSION_ID", "sid-env-wins")
        monkeypatch.setenv("CLAUDE_JOB_DIR", "/home/user/.claude/jobs/sid-job-loses")
        assert cache.resolve_current_session_id() == "sid-env-wins"

    def test_env_session_id_wins_over_pointer_file(self, tmp_path, monkeypatch):
        pointer = _pointer_path(tmp_path, monkeypatch)
        with open(pointer, "w") as f:
            f.write("sid-pointer-loses")
        monkeypatch.setenv("CLAUDE_SESSION_ID", "sid-env-wins-2")
        assert cache.resolve_current_session_id() == "sid-env-wins-2"

    def test_empty_string_env_session_id_is_not_treated_as_set(self, monkeypatch):
        monkeypatch.setenv("CLAUDE_SESSION_ID", "")
        monkeypatch.setenv("CLAUDE_JOB_DIR", "/home/user/.claude/jobs/sid-job-fallback")
        assert cache.resolve_current_session_id() == "sid-job-fallback"


class TestJobDirFallback:
    def test_returns_basename_of_job_dir_when_session_id_env_unset(self, monkeypatch):
        monkeypatch.setenv("CLAUDE_JOB_DIR", "/home/user/.claude/jobs/sid-job-456")
        assert cache.resolve_current_session_id() == "sid-job-456"

    def test_strips_trailing_slash_from_job_dir(self, monkeypatch):
        monkeypatch.setenv("CLAUDE_JOB_DIR", "/home/user/.claude/jobs/sid-job-789/")
        assert cache.resolve_current_session_id() == "sid-job-789"

    def test_job_dir_wins_over_pointer_file(self, tmp_path, monkeypatch):
        pointer = _pointer_path(tmp_path, monkeypatch)
        with open(pointer, "w") as f:
            f.write("sid-pointer-loses-2")
        monkeypatch.setenv("CLAUDE_JOB_DIR", "/home/user/.claude/jobs/sid-job-wins")
        assert cache.resolve_current_session_id() == "sid-job-wins"


class TestPointerFileFallback:
    def test_returns_pointer_file_contents_when_env_signals_absent(self, tmp_path, monkeypatch):
        pointer = _pointer_path(tmp_path, monkeypatch)
        with open(pointer, "w") as f:
            f.write("sid-from-pointer")
        assert cache.resolve_current_session_id() == "sid-from-pointer"

    def test_pointer_file_contents_are_stripped_of_whitespace(self, tmp_path, monkeypatch):
        pointer = _pointer_path(tmp_path, monkeypatch)
        with open(pointer, "w") as f:
            f.write("  sid-with-whitespace\n")
        assert cache.resolve_current_session_id() == "sid-with-whitespace"

    def test_missing_pointer_file_falls_through_to_mtime_glob(self, tmp_path, monkeypatch):
        _pointer_path(tmp_path, monkeypatch)  # points at a nonexistent file
        cache._write_cache("sid-glob-only", cache._read_cache("sid-glob-only"))
        assert cache.resolve_current_session_id() == "sid-glob-only"

    def test_empty_pointer_file_falls_through_to_mtime_glob(self, tmp_path, monkeypatch):
        pointer = _pointer_path(tmp_path, monkeypatch)
        with open(pointer, "w") as f:
            f.write("")
        cache._write_cache("sid-glob-fallback", cache._read_cache("sid-glob-fallback"))
        assert cache.resolve_current_session_id() == "sid-glob-fallback"


class TestMtimeGlobLastResort:
    def test_returns_newest_session_cache_by_mtime(self, tmp_path, monkeypatch):
        _pointer_path(tmp_path, monkeypatch)  # nonexistent -> falls through
        cache._write_cache("sid-older", cache._read_cache("sid-older"))
        older_path = os.path.join(str(tmp_path), "writ-session-sid-older.json")
        os.utime(older_path, (1000, 1000))

        cache._write_cache("sid-newer", cache._read_cache("sid-newer"))
        newer_path = os.path.join(str(tmp_path), "writ-session-sid-newer.json")
        os.utime(newer_path, (2000, 2000))

        assert cache.resolve_current_session_id() == "sid-newer"

    def test_returns_none_when_no_signal_resolves(self, tmp_path, monkeypatch):
        _pointer_path(tmp_path, monkeypatch)  # nonexistent -> falls through
        # tmp_path (the isolated cache dir) holds no writ-session-*.json files.
        assert cache.resolve_current_session_id() is None


class TestFailOpenPerSignal:
    def test_unreadable_pointer_file_falls_through_without_raising(self, tmp_path, monkeypatch):
        pointer_dir = tmp_path / "not-a-file"
        pointer_dir.mkdir()
        # Point the constant at a directory (not a file) so a naive open() would raise;
        # the resolver must catch this and fall through to the mtime glob instead of
        # propagating an exception.
        monkeypatch.setattr(cache, "_SESSION_POINTER_PATH", str(pointer_dir), raising=False)
        cache._write_cache("sid-after-bad-pointer", cache._read_cache("sid-after-bad-pointer"))
        assert cache.resolve_current_session_id() == "sid-after-bad-pointer"

    def test_no_exception_escapes_when_everything_is_absent(self, tmp_path, monkeypatch):
        _pointer_path(tmp_path, monkeypatch)
        try:
            result = cache.resolve_current_session_id()
        except Exception as exc:  # noqa: BLE001
            pytest.fail(f"resolver must never raise, got {type(exc).__name__}: {exc}")
        assert result is None
