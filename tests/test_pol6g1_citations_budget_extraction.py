"""POL-6g-1: citations + budget_tracking -> writ/session/{citations,budget_tracking}.py.

Two cohesive moves in one increment (citations is the lowest new layer; budget_tracking's
cmd_update depends on it). `_VALID_SOURCE_TYPES` relocates to mode_engine (source-type
vocabulary, cmd_update's only cross-cluster ref). RED until the move lands.

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
CITATIONS_PATH = os.path.join(SKILL_ROOT, "writ", "session", "citations.py")
BUDGET_PATH = os.path.join(SKILL_ROOT, "writ", "session", "budget_tracking.py")
MODE_ENGINE_PATH = os.path.join(SKILL_ROOT, "writ", "session", "mode_engine.py")


def _load_facade():
    spec = importlib.util.spec_from_file_location("writ_session_pol6g1", FACADE_PATH)
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


def _run_update(facade, sid, args):
    facade.cmd_update(sid, args)
    cache = _imp("writ.session.cache")
    return cache._read_cache(sid)


# --------------------------------------------------------------------------- #
# citations.py
# --------------------------------------------------------------------------- #
class TestCitationsModule:
    def test_module_exists(self):
        assert os.path.isfile(CITATIONS_PATH)

    def test_imports(self):
        assert _imp("writ.session.citations") is not None

    def test_acyclic_no_facade_import(self):
        imports = _import_lines(CITATIONS_PATH)
        assert "writ_session" not in imports and "writ-session" not in imports
        with open(CITATIONS_PATH) as f:
            assert "spec_from_file_location" not in f.read()

    def test_imports_config_bounds(self):
        with open(CITATIONS_PATH) as f:
            src = f.read()
        assert "from writ.session.config import" in src

    def test_append_citation_stamps_and_truncates(self):
        cit = _imp("writ.session.citations")
        cache = {}
        cit._append_citation(cache, {"artifact_type": "file", "ref": "x.py", "excerpt": "z" * 600})
        log = cache["citation_log"]
        assert len(log) == 1
        entry = log[0]
        assert len(entry["excerpt"]) == 500  # _CITATION_EXCERPT_MAX
        assert "excerpt_hash" in entry and len(entry["excerpt_hash"]) == 16
        assert "ts" in entry

    def test_append_citation_trims_to_log_cap(self):
        cit = _imp("writ.session.citations")
        cache = {}
        for n in range(12):
            cit._append_citation(cache, {"ref": f"r{n}", "excerpt": str(n)})
        assert len(cache["citation_log"]) == 10  # _CITATION_LOG_MAX


# --------------------------------------------------------------------------- #
# budget_tracking.py
# --------------------------------------------------------------------------- #
class TestBudgetTrackingModule:
    def test_module_exists(self):
        assert os.path.isfile(BUDGET_PATH)

    def test_imports(self):
        assert _imp("writ.session.budget_tracking") is not None

    def test_acyclic_no_facade_import(self):
        imports = _import_lines(BUDGET_PATH)
        assert "writ_session" not in imports and "writ-session" not in imports
        with open(BUDGET_PATH) as f:
            assert "spec_from_file_location" not in f.read()

    def test_imports_lower_layers(self):
        with open(BUDGET_PATH) as f:
            src = f.read()
        assert "from writ.session.cache import" in src
        assert "from writ.session.citations import" in src
        assert "from writ.session.mode_engine import" in src


class TestCmdUpdate:
    def test_cost_decrements_budget(self, tmp_path, monkeypatch):
        monkeypatch.setenv("WRIT_CACHE_DIR", str(tmp_path))
        f = _load_facade()
        sid = f"bt-{uuid.uuid4().hex[:8]}"
        _seed(sid, remaining_budget=1000)
        data = _run_update(f, sid, ["--cost", "300"])
        assert data["remaining_budget"] == 700

    def test_cost_floors_at_zero(self, tmp_path, monkeypatch):
        monkeypatch.setenv("WRIT_CACHE_DIR", str(tmp_path))
        f = _load_facade()
        sid = f"bt-{uuid.uuid4().hex[:8]}"
        _seed(sid, remaining_budget=100)
        data = _run_update(f, sid, ["--cost", "9999"])
        assert data["remaining_budget"] == 0

    def test_add_citation_routes_through_citations(self, tmp_path, monkeypatch):
        monkeypatch.setenv("WRIT_CACHE_DIR", str(tmp_path))
        f = _load_facade()
        sid = f"bt-{uuid.uuid4().hex[:8]}"
        _seed(sid)
        data = _run_update(
            f, sid, ["--add-citation", json.dumps({"artifact_type": "file", "ref": "a.py", "excerpt": "hi"})]
        )
        assert len(data["citation_log"]) == 1
        assert data["citation_log"][0]["ref"] == "a.py"

    def test_set_source_type_valid_accepted(self, tmp_path, monkeypatch):
        monkeypatch.setenv("WRIT_CACHE_DIR", str(tmp_path))
        f = _load_facade()
        sid = f"bt-{uuid.uuid4().hex[:8]}"
        _seed(sid)
        data = _run_update(f, sid, ["--set-source-type", "web"])
        assert data["source_type"] == "web"

    def test_set_source_type_invalid_ignored(self, tmp_path, monkeypatch):
        monkeypatch.setenv("WRIT_CACHE_DIR", str(tmp_path))
        f = _load_facade()
        sid = f"bt-{uuid.uuid4().hex[:8]}"
        _seed(sid)
        data = _run_update(f, sid, ["--set-source-type", "bogus"])
        assert "source_type" not in data or data["source_type"] != "bogus"

    def test_reset_task_phase_lands_at_planning(self, tmp_path, monkeypatch):
        monkeypatch.setenv("WRIT_CACHE_DIR", str(tmp_path))
        f = _load_facade()
        sid = f"bt-{uuid.uuid4().hex[:8]}"
        _seed(sid, current_phase="implementation", gates_approved=["phase-a", "test-skeletons"])
        data = _run_update(f, sid, ["--reset-task-phase"])
        assert data["current_phase"] == "planning"
        assert data["gates_approved"] == []

    def test_set_last_injected_rule_ids_replaces(self, tmp_path, monkeypatch):
        # A3: the new flag replaces the rag-inject hook's separate raw read-write.
        monkeypatch.setenv("WRIT_CACHE_DIR", str(tmp_path))
        f = _load_facade()
        sid = f"bt-{uuid.uuid4().hex[:8]}"
        _seed(sid, last_injected_rule_ids=["OLD-1"])
        data = _run_update(f, sid, ["--set-last-injected-rule-ids", json.dumps(["ENF-A", "ENF-B"])])
        assert data["last_injected_rule_ids"] == ["ENF-A", "ENF-B"]

    def test_set_last_injected_rule_ids_empty_clears(self, tmp_path, monkeypatch):
        monkeypatch.setenv("WRIT_CACHE_DIR", str(tmp_path))
        f = _load_facade()
        sid = f"bt-{uuid.uuid4().hex[:8]}"
        _seed(sid, last_injected_rule_ids=["OLD-1"])
        data = _run_update(f, sid, ["--set-last-injected-rule-ids", "[]"])
        assert data["last_injected_rule_ids"] == []

    def test_add_rule_objects_empty_is_noop(self, tmp_path, monkeypatch):
        # A3 relies on --add-rule-objects "[]" being a safe no-op so the hook can
        # pass it unconditionally in the merged call.
        monkeypatch.setenv("WRIT_CACHE_DIR", str(tmp_path))
        f = _load_facade()
        sid = f"bt-{uuid.uuid4().hex[:8]}"
        _seed(sid)
        before = _run_update(f, sid, []).get("loaded_rules", [])
        data = _run_update(f, sid, ["--add-rule-objects", "[]"])
        assert data.get("loaded_rules", []) == before

    def test_a3_combined_update_one_call(self, tmp_path, monkeypatch):
        # A3: rag-inject now folds add-rules + cost + inc-queries + set-last-injected
        # + add-rule-objects into ONE cmd_update call. Final cache must match what the
        # 3 separate mutations produced.
        monkeypatch.setenv("WRIT_CACHE_DIR", str(tmp_path))
        f = _load_facade()
        sid = f"bt-{uuid.uuid4().hex[:8]}"
        _seed(sid, remaining_budget=1000)
        ids = json.dumps(["ENF-A"])
        objs = json.dumps([{"rule_id": "ENF-A", "trigger": "t", "statement": "s"}])
        data = _run_update(f, sid, [
            "--add-rules", ids, "--cost", "50", "--inc-queries",
            "--set-last-injected-rule-ids", ids, "--add-rule-objects", objs,
        ])
        assert data["remaining_budget"] == 950
        assert data["queries"] == 1
        assert "ENF-A" in data["loaded_rule_ids"]
        assert data["last_injected_rule_ids"] == ["ENF-A"]
        assert any(r["rule_id"] == "ENF-A" for r in data["loaded_rules"])


class TestCmdShouldSkipAndCost:
    def test_should_skip_budget_exhausted(self, tmp_path, monkeypatch):
        monkeypatch.setenv("WRIT_CACHE_DIR", str(tmp_path))
        f = _load_facade()
        sid = f"bt-{uuid.uuid4().hex[:8]}"
        _seed(sid, remaining_budget=0)
        assert f.cmd_should_skip(sid) is True

    def test_should_skip_under_threshold_proceeds(self, tmp_path, monkeypatch):
        monkeypatch.setenv("WRIT_CACHE_DIR", str(tmp_path))
        f = _load_facade()
        sid = f"bt-{uuid.uuid4().hex[:8]}"
        _seed(sid, remaining_budget=5000, context_percent=10)
        assert f.cmd_should_skip(sid) is False

    def test_should_skip_subagent_never_skips(self, tmp_path, monkeypatch):
        monkeypatch.setenv("WRIT_CACHE_DIR", str(tmp_path))
        f = _load_facade()
        sid = f"bt-{uuid.uuid4().hex[:8]}"
        _seed(sid, remaining_budget=0, is_subagent=True)
        assert f.cmd_should_skip(sid) is False

    def test_estimate_cost_scales_with_rule_count(self):
        bt = _imp("writ.session.budget_tracking")
        rules = [{}, {}, {}]
        assert bt._estimate_cost(rules, "full") == bt._estimate_cost(rules, "full")
        assert bt._estimate_cost(rules, "full") >= bt._estimate_cost(rules, "summary")
        assert bt._estimate_cost([], "full") == 0


class TestCmdFormat:
    def test_format_emits_rule_block_and_meta(self, monkeypatch, capsys):
        f = _load_facade()
        response = {"rules": [{"rule_id": "FOO-001", "statement": "do it", "score": 0.9}], "mode": "standard"}
        monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(response)))
        f.cmd_format()
        out = capsys.readouterr().out
        assert "--- WRIT RULES" in out
        assert "FOO-001" in out
        assert "WRIT_META:" in out

    def test_format_empty_rules_exits_silently(self, monkeypatch):
        f = _load_facade()
        monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps({"rules": []})))
        with pytest.raises(SystemExit):
            f.cmd_format()


# --------------------------------------------------------------------------- #
# _VALID_SOURCE_TYPES relocated to mode_engine
# --------------------------------------------------------------------------- #
class TestSourceTypeVocabRelocated:
    def test_mode_engine_owns_valid_source_types(self):
        me = _imp("writ.session.mode_engine")
        assert me._VALID_SOURCE_TYPES == {"code", "web", "runtime"}

    def test_facade_reexports_valid_source_types(self):
        f = _load_facade()
        assert f._VALID_SOURCE_TYPES == {"code", "web", "runtime"}

    def test_facade_has_no_inline_valid_source_types(self):
        with open(FACADE_PATH) as f:
            src = f.read()
        assert '_VALID_SOURCE_TYPES = {' not in src


# --------------------------------------------------------------------------- #
# source shape
# --------------------------------------------------------------------------- #
class TestSourceShape:
    def test_facade_no_inline_defs(self):
        with open(FACADE_PATH) as f:
            src = f.read()
        for name in ("_append_citation", "cmd_update", "cmd_should_skip", "_estimate_cost", "cmd_format"):
            assert f"def {name}(" not in src, f"{name} still inline in facade"

    def test_facade_reimports_new_modules(self):
        with open(FACADE_PATH) as f:
            src = f.read()
        assert "from writ.session.citations import" in src
        assert "from writ.session.budget_tracking import" in src

    def test_modules_define_their_symbols(self):
        with open(CITATIONS_PATH) as f:
            assert "def _append_citation(" in f.read()
        with open(BUDGET_PATH) as f:
            bsrc = f.read()
        for name in ("cmd_update", "cmd_should_skip", "_estimate_cost", "cmd_format"):
            assert f"def {name}(" in bsrc
