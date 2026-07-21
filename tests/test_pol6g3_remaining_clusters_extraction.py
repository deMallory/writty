"""POL-6g-3: the last three command clusters -> writ/session/.

violations.py (pending-violation/escalation state machine), session_lifecycle.py (cmd_read +
PreCompact/PostCompact), feedback.py (cmd_auto_feedback). Three independent leaf modules; each
imports only lower layers. RED until the move lands.

Per TEST-TDD-001: skeletons approved before implementation.
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

import pytest

SKILL_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
FACADE_PATH = os.path.join(SKILL_ROOT, "bin", "lib", "writ-session.py")
VIOL_PATH = os.path.join(SKILL_ROOT, "writ", "session", "violations.py")
LIFECYCLE_PATH = os.path.join(SKILL_ROOT, "writ", "session", "session_lifecycle.py")
FEEDBACK_PATH = os.path.join(SKILL_ROOT, "writ", "session", "feedback.py")


def _load_facade():
    spec = importlib.util.spec_from_file_location("writ_session_pol6g3", FACADE_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _imp(name):
    if SKILL_ROOT not in sys.path:
        sys.path.insert(0, SKILL_ROOT)
    return importlib.import_module(name)


def _import_lines(path):
    with open(path) as f:
        return "\n".join(
            l for l in f.read().splitlines() if l.strip().startswith(("import ", "from "))
        )


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


# --------------------------------------------------------------------------- #
# violations.py
# --------------------------------------------------------------------------- #
class TestViolationsModule:
    def test_module_exists(self):
        assert os.path.isfile(VIOL_PATH)

    def test_acyclic_lower_layers_only(self):
        imports = _import_lines(VIOL_PATH)
        assert "writ_session" not in imports and "writ-session" not in imports
        assert "from writ.session.cache import" in open(VIOL_PATH).read()


class TestViolationsBehavior:
    def test_add_dedups_by_triple(self, tmp_path, monkeypatch):
        monkeypatch.setenv("WRIT_CACHE_DIR", str(tmp_path))
        f = _load_facade()
        sid = f"v-{uuid.uuid4().hex[:8]}"
        _seed(sid)
        args = ["--rule", "SEC-001", "--file", "a.py", "--line", "3"]
        f.cmd_add_pending_violation(sid, args)
        f.cmd_add_pending_violation(sid, args)  # same triple -> no dup
        assert len(_read(sid)["pending_violations"]) == 1

    def test_clear_empties(self, tmp_path, monkeypatch):
        monkeypatch.setenv("WRIT_CACHE_DIR", str(tmp_path))
        f = _load_facade()
        sid = f"v-{uuid.uuid4().hex[:8]}"
        _seed(sid, pending_violations=[{"rule_id": "X", "file": "y", "line": None}])
        f.cmd_clear_pending_violations(sid)
        assert _read(sid)["pending_violations"] == []

    def test_invalidate_flags_escalation_at_max_cycles(self, tmp_path, monkeypatch):
        monkeypatch.setenv("WRIT_CACHE_DIR", str(tmp_path))
        f = _load_facade()
        sid = f"v-{uuid.uuid4().hex[:8]}"
        _seed(sid)
        for _ in range(f.MAX_CYCLES_BEFORE_ESCALATION):
            f.cmd_invalidate_gate(sid, ["phase-a", "--rule", "ENF-001", "--file", "a.py"])
        r = _call_json(f.cmd_check_escalation, sid)
        assert r["needed"] is True
        assert r["cycles"] >= f.MAX_CYCLES_BEFORE_ESCALATION

    def test_pending_violations_lists(self, tmp_path, monkeypatch):
        monkeypatch.setenv("WRIT_CACHE_DIR", str(tmp_path))
        f = _load_facade()
        sid = f"v-{uuid.uuid4().hex[:8]}"
        _seed(sid, pending_violations=[{"rule_id": "X", "file": "y", "line": 1}])
        r = _call_json(f.cmd_pending_violations, sid)
        assert isinstance(r, list) and r[0]["rule_id"] == "X"


# --------------------------------------------------------------------------- #
# session_lifecycle.py
# --------------------------------------------------------------------------- #
class TestSessionLifecycleModule:
    def test_module_exists(self):
        assert os.path.isfile(LIFECYCLE_PATH)

    def test_acyclic_lower_layers_only(self):
        imports = _import_lines(LIFECYCLE_PATH)
        assert "writ_session" not in imports and "writ-session" not in imports
        src = open(LIFECYCLE_PATH).read()
        assert "from writ.session.cache import" in src
        assert "from writ.session.friction import" in src
        assert "from writ.session.config import" in src


class TestSessionLifecycleBehavior:
    def test_read_dumps_cache(self, tmp_path, monkeypatch):
        monkeypatch.setenv("WRIT_CACHE_DIR", str(tmp_path))
        f = _load_facade()
        sid = f"sl-{uuid.uuid4().hex[:8]}"
        _seed(sid, mode="work", marker_field="zzz")
        r = _call_json(f.cmd_read, sid)
        assert r.get("marker_field") == "zzz"

    def test_clear_rules_for_compaction_empties_loaded_rules(self, tmp_path, monkeypatch):
        monkeypatch.setenv("WRIT_CACHE_DIR", str(tmp_path))
        f = _load_facade()
        sid = f"sl-{uuid.uuid4().hex[:8]}"
        _seed(sid, mode="work", loaded_rules=[{"rule_id": "A"}, {"rule_id": "B"}])
        r = _call_json(f.cmd_clear_rules_for_compaction, sid)
        assert r["rules_cleared"] == 2
        assert _read(sid)["loaded_rules"] == []

    def test_reset_after_compaction_resets_budget(self, tmp_path, monkeypatch):
        monkeypatch.setenv("WRIT_CACHE_DIR", str(tmp_path))
        f = _load_facade()
        cfg = _imp("writ.session.config")
        sid = f"sl-{uuid.uuid4().hex[:8]}"
        _seed(sid, mode="work", current_phase="implementation", remaining_budget=0)
        r = _call_json(f.cmd_reset_after_compaction, sid)
        assert r["budget_reset"] is True
        assert r["mode"] == "work" and r["phase"] == "implementation"
        assert _read(sid)["remaining_budget"] == cfg.DEFAULT_SESSION_BUDGET


# --------------------------------------------------------------------------- #
# feedback.py
# --------------------------------------------------------------------------- #
class TestFeedbackModule:
    def test_module_exists(self):
        assert os.path.isfile(FEEDBACK_PATH)

    def test_acyclic_imports_config(self):
        imports = _import_lines(FEEDBACK_PATH)
        assert "writ_session" not in imports and "writ-session" not in imports
        src = open(FEEDBACK_PATH).read()
        assert "from writ.session.cache import" in src
        assert "from writ.session.config import" in src

    def test_feedback_url_defined_and_reexported(self):
        fb = _imp("writ.session.feedback")
        assert fb.WRIT_FEEDBACK_URL == "http://localhost:8765/feedback"
        assert _load_facade().WRIT_FEEDBACK_URL == "http://localhost:8765/feedback"

    def test_auto_feedback_early_returns_without_results(self, tmp_path, monkeypatch, capsys):
        monkeypatch.setenv("WRIT_CACHE_DIR", str(tmp_path))
        f = _load_facade()
        sid = f"fb-{uuid.uuid4().hex[:8]}"
        _seed(sid, loaded_rule_ids=["SEC-001"], analysis_results={})
        f.cmd_auto_feedback(sid)  # no analysis_results -> early return, no POST, no output
        assert capsys.readouterr().out.strip() == ""


# --------------------------------------------------------------------------- #
# source shape
# --------------------------------------------------------------------------- #
class TestSourceShape:
    MOVED = [
        "cmd_add_pending_violation", "cmd_clear_pending_violations", "cmd_invalidate_gate",
        "cmd_check_escalation", "cmd_pending_violations", "cmd_read",
        "cmd_clear_rules_for_compaction", "cmd_reset_after_compaction", "cmd_auto_feedback",
    ]

    def test_facade_no_inline_defs(self):
        with open(FACADE_PATH) as f:
            src = f.read()
        for name in self.MOVED:
            assert f"def {name}(" not in src, f"{name} still inline in facade"

    def test_facade_reimports_three_modules(self):
        with open(FACADE_PATH) as f:
            src = f.read()
        assert "from writ.session.violations import" in src
        assert "from writ.session.session_lifecycle import" in src
        assert "from writ.session.feedback import" in src

    def test_modules_define_their_symbols(self):
        viol = open(VIOL_PATH).read()
        for name in ("cmd_add_pending_violation", "cmd_invalidate_gate", "cmd_check_escalation"):
            assert f"def {name}(" in viol
        assert "MAX_CYCLES_BEFORE_ESCALATION" in viol
        life = open(LIFECYCLE_PATH).read()
        for name in ("cmd_read", "cmd_clear_rules_for_compaction", "cmd_reset_after_compaction"):
            assert f"def {name}(" in life
        assert "def cmd_auto_feedback(" in open(FEEDBACK_PATH).read()
