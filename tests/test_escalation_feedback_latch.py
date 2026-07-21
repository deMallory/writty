"""Wave 1 Cycle 4 S1: the escalation "send negative feedback once" latch.

Compounding pair (WRIT-HYGIENE-AUDIT 3.1): cmd_check_escalation never emitted
feedback_sent (guard always None -> re-send) and the hook write-back ignored
WRIT_CACHE_DIR (latch never persisted). Both must hold for the guarantee.

Per TEST-TDD-001: skeletons approved before implementation. RED until S1a/S1b land.
"""
from __future__ import annotations

import contextlib
import importlib
import importlib.util
import io
import json
import os
import sys
import uuid
from pathlib import Path

SKILL_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
FACADE_PATH = os.path.join(SKILL_ROOT, "bin", "lib", "writ-session.py")
HOOK = Path(SKILL_ROOT) / "hooks" / "scripts" / "writ-rag-inject.sh"


def _load_facade():
    spec = importlib.util.spec_from_file_location("writ_session_s1", FACADE_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _imp(name):
    if SKILL_ROOT not in sys.path:
        sys.path.insert(0, SKILL_ROOT)
    return importlib.import_module(name)


def _seed(sid, **fields):
    cache = _imp("writ.session.cache")
    data = cache._read_cache(sid)
    data.update(fields)
    cache._write_cache(sid, data)


def _read(sid):
    return _imp("writ.session.cache")._read_cache(sid)


def _call_json(fn, *args):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        fn(*args)
    return json.loads(buf.getvalue().strip())


def _escalate(f, sid):
    for _ in range(f.MAX_CYCLES_BEFORE_ESCALATION):
        f.cmd_invalidate_gate(sid, ["phase-a", "--rule", "ENF-001", "--file", "a.py"])


class TestCheckEscalationEmitsFeedbackSent:
    """S1a: cmd_check_escalation's output JSON must carry feedback_sent, sourced
    from the real escalation cache state, not just needed/gate/diagnosis/cycles."""

    def test_feedback_sent_present_default_false(self, tmp_path, monkeypatch):
        monkeypatch.setenv("WRIT_CACHE_DIR", str(tmp_path))
        f = _load_facade()
        sid = f"s1-{uuid.uuid4().hex[:8]}"
        _seed(sid)
        _escalate(f, sid)
        r = _call_json(f.cmd_check_escalation, sid)
        assert r["needed"] is True
        assert "feedback_sent" in r, "check-escalation must surface feedback_sent"
        assert r["feedback_sent"] is False  # not yet sent

    def test_feedback_sent_reflects_latched_value(self, tmp_path, monkeypatch):
        monkeypatch.setenv("WRIT_CACHE_DIR", str(tmp_path))
        f = _load_facade()
        sid = f"s1-{uuid.uuid4().hex[:8]}"
        _seed(sid)
        _escalate(f, sid)
        data = _read(sid)
        data["escalation"]["feedback_sent"] = True  # simulate the hook latch
        _imp("writ.session.cache")._write_cache(sid, data)
        r = _call_json(f.cmd_check_escalation, sid)
        assert r["feedback_sent"] is True  # second prompt would NOT re-send

    def test_feedback_sent_false_when_no_escalation(self, tmp_path, monkeypatch):
        monkeypatch.setenv("WRIT_CACHE_DIR", str(tmp_path))
        f = _load_facade()
        sid = f"s1-{uuid.uuid4().hex[:8]}"
        _seed(sid)
        r = _call_json(f.cmd_check_escalation, sid)
        assert r["feedback_sent"] is False


class TestHookWriteBackHonorsCacheDir:
    """S1b (updated by fix/session-mode-preserve): the escalation feedback write-back
    must resolve the cache path the same way _read_cache/_write_cache do. The
    write-back is no longer hand-rolled inline python -- it routes through
    `writ-session.py update --set-escalation-feedback-sent`, which writes via
    cmd_update -> _cache_dir() (WRIT_CACHE_DIR at call time), so the latch lands in
    the same file the next _read_cache reads by construction, and cannot torn-write
    the whole cache. This guards that the block did not regress back to a hand-rolled
    path/temp writer."""

    def test_writeback_uses_update_cli_not_handrolled_path(self):
        src = HOOK.read_text()
        marker = "Mark feedback as sent in escalation"
        assert marker in src
        block = src[src.index(marker): src.index(marker) + 400]
        assert "--set-escalation-feedback-sent" in block, (
            "escalation write-back must route through `writ-session.py update "
            "--set-escalation-feedback-sent` (which honors WRIT_CACHE_DIR via _cache_dir)"
        )
        assert "tempfile.gettempdir()" not in block, (
            "the write-back must not hand-roll a cache-dir fallback (the S1b bug)"
        )
        assert "path + '.tmp'" not in block and 'path + ".tmp"' not in block, (
            "the write-back must not hand-roll a temp write (the torn-write root cause)"
        )


class TestCacheDirResolutionContract:
    """Resolution-contract test for the unit S1b's fix must agree with: the
    session-cache path _read_cache/_write_cache resolve is keyed on WRIT_CACHE_DIR
    at call time (writ/session/cache.py:_cache_dir). A write-back that honors
    WRIT_CACHE_DIR (per TestHookWriteBackHonorsCacheDir above) lands in exactly
    the file the next _read_cache call reads -- proving the two halves agree on
    one target path, not just that each independently mentions the env var."""

    def test_read_cache_resolves_under_writ_cache_dir(self, tmp_path, monkeypatch):
        monkeypatch.setenv("WRIT_CACHE_DIR", str(tmp_path))
        cache = _imp("writ.session.cache")
        sid = f"s1-{uuid.uuid4().hex[:8]}"
        cache._write_cache(sid, {"escalation": {"feedback_sent": False}})
        expected_path = os.path.join(str(tmp_path), f"writ-session-{sid}.json")
        assert os.path.isfile(expected_path), (
            "the session cache must land under WRIT_CACHE_DIR so a write-back "
            "targeting the same env var lands in the file the next _read_cache "
            "call reads"
        )
        data = cache._read_cache(sid)
        assert data["escalation"]["feedback_sent"] is False

    def test_writeback_target_matches_read_cache_target(self, tmp_path, monkeypatch):
        """Simulate the FIXED write-back (honoring WRIT_CACHE_DIR) and assert the
        next cmd_check_escalation call (which reads via _read_cache) observes the
        latch -- the end-to-end contract the hook write-back must satisfy."""
        monkeypatch.setenv("WRIT_CACHE_DIR", str(tmp_path))
        f = _load_facade()
        sid = f"s1-{uuid.uuid4().hex[:8]}"
        _seed(sid)
        _escalate(f, sid)

        # Simulate the fixed write-back: resolve WRIT_CACHE_DIR first, matching
        # the sibling blocks, then latch feedback_sent directly in that file.
        cache_dir = os.environ.get("WRIT_CACHE_DIR")
        path = os.path.join(cache_dir, f"writ-session-{sid}.json")
        with open(path) as fh:
            cache_json = json.load(fh)
        cache_json.setdefault("escalation", {})["feedback_sent"] = True
        tmp = path + ".tmp"
        with open(tmp, "w") as fh:
            json.dump(cache_json, fh)
        os.rename(tmp, path)

        r = _call_json(f.cmd_check_escalation, sid)
        assert r["feedback_sent"] is True, (
            "a write-back honoring WRIT_CACHE_DIR must be visible to the very "
            "next cmd_check_escalation call reading via the same env var"
        )
