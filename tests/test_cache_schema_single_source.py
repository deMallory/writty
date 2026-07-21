"""Guard for the Wave 3 cache.py schema single-source (drift fix).

writ/session/cache.py::_read_cache declared the session schema twice: a `default` dict
(no-file path) and a `data.setdefault(...)` block (file path). They agreed on 35 keys but
the setdefault block carried 3 the default dict lacked -- current_phase, gates_approved,
loaded_rule_ids_by_phase -- so a brand-new session's cache was missing them. The dedup
introduces one `_default_cache()` used by every path, which also closes the drift.

RED today: the default dict lacks the 3 phase keys (tests 1-2 fail on their assertions) and
`_default_cache` does not exist (test 3 fails on import).
"""
from __future__ import annotations

import pytest

from writ.session.cache import _read_cache, _write_cache

THREE_PHASE_KEYS = {"current_phase", "gates_approved", "loaded_rule_ids_by_phase"}


@pytest.fixture(autouse=True)
def _isolate_cache_dir(tmp_path, monkeypatch):
    # cache.py resolves WRIT_CACHE_DIR at call time; isolate to a temp dir per test.
    monkeypatch.setenv("WRIT_CACHE_DIR", str(tmp_path))


class TestDriftClosed:
    def test_new_session_cache_has_the_three_phase_keys(self) -> None:
        r = _read_cache("fresh-sid")
        assert THREE_PHASE_KEYS <= set(r), f"new-session cache missing {THREE_PHASE_KEYS - set(r)}"
        assert r["current_phase"] is None
        assert r["gates_approved"] == []
        assert r["loaded_rule_ids_by_phase"] == {}

    def test_new_and_existing_session_have_identical_keysets(self) -> None:
        # write a minimal cache to disk, then reread (file path applies defaults)
        _write_cache("existing-sid", {"mode": "work"})
        reread = _read_cache("existing-sid")
        fresh = _read_cache("brand-new-sid")
        assert set(reread) == set(fresh), (
            f"keyset drift: only-in-existing={set(reread) - set(fresh)}, "
            f"only-in-new={set(fresh) - set(reread)}"
        )


class TestSingleSource:
    def test_read_cache_new_session_equals_default_cache(self) -> None:
        from writ.session.cache import _default_cache  # RED today: absent

        assert _read_cache("fresh-sid") == _default_cache()


class TestNoMutableDefaultAliasing:
    def test_mutable_defaults_not_aliased_across_sessions(self) -> None:
        a = _read_cache("sid-a")
        b = _read_cache("sid-b")
        a["pending_violations"].append("x")
        a["invalidation_history"]["phase-a"] = [1]
        a["escalation"]["needed"] = True  # nested dict default
        assert b["pending_violations"] == [], "list default aliased across sessions"
        assert b["invalidation_history"] == {}, "dict default aliased across sessions"
        assert b["escalation"]["needed"] is False, "nested escalation dict aliased across sessions"
