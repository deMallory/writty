"""POL-6e: gates -> writ/session/gates.py.

The gate cluster (_can_write_check/_can_read_code_check + cmd_can_write/cmd_can_read_code +
validators/detectors/_log_gate_denial + _CODE_EXTENSIONS) moves to gates.py, importing only
lower layers (cache/friction/locators/mode_engine). _effective_source_type relocates to
mode_engine (shared by the read gate and cmd_lens); the dead _detect_language/_detect_frameworks
are removed. The gate-categories.json fallback path must be rewritten to the skill root (it used
os.path.dirname(__file__), which no longer points at bin/lib from writ/session/gates.py).

Per TEST-TDD-001: skeletons approved before implementation. RED until the move lands.
"""

from __future__ import annotations

import importlib
import importlib.util
import io
import json
import os
import sys

import pytest

SKILL_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
FACADE_PATH = os.path.join(SKILL_ROOT, "bin", "lib", "writ-session.py")
GATES_PATH = os.path.join(SKILL_ROOT, "writ", "session", "gates.py")
MODE_ENGINE_PATH = os.path.join(SKILL_ROOT, "writ", "session", "mode_engine.py")


def _load_facade():
    spec = importlib.util.spec_from_file_location("writ_session_pol6e", FACADE_PATH)
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


def _envelope(file_path, tool_name="Write"):
    return {"tool_name": tool_name, "tool_input": {"file_path": file_path}}


class TestModulesAndAcyclic:
    def test_gates_file_exists(self):
        assert os.path.isfile(GATES_PATH)

    def test_gates_imports(self):
        assert _imp("writ.session.gates") is not None

    def test_gates_does_not_import_facade(self):
        with open(GATES_PATH) as f:
            lines = f.read().splitlines()
        import_lines = "\n".join(l for l in lines if l.strip().startswith(("import ", "from ")))
        assert "writ_session" not in import_lines
        assert "writ-session" not in import_lines
        assert "spec_from_file_location" not in "\n".join(lines)

    def test_gates_imports_lower_layers(self):
        with open(GATES_PATH) as f:
            src = f.read()
        assert "from writ.session.cache import" in src
        assert "from writ.session.friction import" in src
        assert "from writ.session.locators import" in src
        assert "from writ.session.mode_engine import" in src


class TestCanWriteEnforcement:
    """_can_write_check via the facade re-export, on an isolated session + out-of-skill paths."""

    def test_no_mode_denies(self, tmp_path, monkeypatch):
        monkeypatch.setenv("WRIT_CACHE_DIR", str(tmp_path))
        f = _load_facade()
        _seed("g-nomode", mode=None)
        r = f._can_write_check("g-nomode", _envelope("/tmp/proj/src/a.py"), "")
        assert r["can_write"] is False
        assert "ENF-GATE-MODE" in r["reason"]
        # Audit #6: the deny message must list all live modes, including investigate.
        assert "investigate" in r["reason"]

    def test_no_mode_deny_is_logged(self, tmp_path, monkeypatch):
        """Audit #5: the no-mode gate deny must emit a friction event (it logged nothing
        before, so the most security-relevant deny was invisible in telemetry)."""
        monkeypatch.setenv("WRIT_CACHE_DIR", str(tmp_path))
        gates = _imp("writ.session.gates")
        calls = []
        monkeypatch.setattr(
            gates, "_log_friction_event",
            lambda *a, **k: calls.append((a, k)),
        )
        _seed("g-nomode-log", mode=None)
        gates._can_write_check("g-nomode-log", _envelope("/tmp/proj/src/a.py"), "")
        deny_events = [
            (a, k) for (a, k) in calls if k.get("result") == "deny" or "deny" in a
        ]
        assert deny_events, "no-mode deny must log a friction event with result=deny"
        assert any(k.get("gate_status") == "no_mode" for (a, k) in deny_events)

    def test_review_mode_allows(self, tmp_path, monkeypatch):
        monkeypatch.setenv("WRIT_CACHE_DIR", str(tmp_path))
        f = _load_facade()
        _seed("g-review", mode="review")
        assert f._can_write_check("g-review", _envelope("/tmp/proj/src/a.py"), "")["can_write"] is True

    def test_work_blocks_until_phase_a(self, tmp_path, monkeypatch):
        monkeypatch.setenv("WRIT_CACHE_DIR", str(tmp_path))
        f = _load_facade()
        _seed("g-w1", mode="work", gates_approved=[], current_phase="planning")
        r = f._can_write_check("g-w1", _envelope("/tmp/proj/src/a.py"), str(SKILL_ROOT))
        assert r["can_write"] is False
        assert "ENF-GATE-PLAN" in r["reason"]

    def test_work_blocks_until_test_skeletons(self, tmp_path, monkeypatch):
        monkeypatch.setenv("WRIT_CACHE_DIR", str(tmp_path))
        f = _load_facade()
        _seed("g-w2", mode="work", gates_approved=["phase-a"], current_phase="testing")
        r = f._can_write_check("g-w2", _envelope("/tmp/proj/src/a.py"), str(SKILL_ROOT))
        assert r["can_write"] is False
        assert "ENF-GATE-TEST" in r["reason"]

    def test_work_allows_when_both_gates_approved(self, tmp_path, monkeypatch):
        monkeypatch.setenv("WRIT_CACHE_DIR", str(tmp_path))
        f = _load_facade()
        _seed("g-w3", mode="work", gates_approved=["phase-a", "test-skeletons"], current_phase="implementation")
        assert f._can_write_check("g-w3", _envelope("/tmp/proj/src/a.py"), str(SKILL_ROOT))["can_write"] is True

    def test_capabilities_md_always_allowed(self, tmp_path, monkeypatch):
        monkeypatch.setenv("WRIT_CACHE_DIR", str(tmp_path))
        f = _load_facade()
        _seed("g-cap", mode="work", gates_approved=[], current_phase="planning")
        assert f._can_write_check("g-cap", _envelope("/tmp/proj/capabilities.md"), str(SKILL_ROOT))["can_write"] is True

    # --- A7 gate-reorder regression guards -------------------------------------
    def test_work_both_gates_approved_allows_excluded_path(self, tmp_path, monkeypatch):
        """A7: with both gates approved, an excluded path (e.g. __init__.py) is still
        ALLOWED -- decision unchanged after the reorder (the categories read that
        produced the old "excluded" label is skipped; the answer is allow either way)."""
        monkeypatch.setenv("WRIT_CACHE_DIR", str(tmp_path))
        f = _load_facade()
        _seed("g-w-exc", mode="work", gates_approved=["phase-a", "test-skeletons"], current_phase="implementation")
        assert f._can_write_check("g-w-exc", _envelope("/tmp/proj/pkg/__init__.py"), str(SKILL_ROOT))["can_write"] is True

    def test_work_both_gates_approved_skips_categories_read(self, tmp_path, monkeypatch):
        """A7 contract: once both gates are approved (the dominant steady-state path)
        the gate-categories.json disk read is skipped entirely."""
        monkeypatch.setenv("WRIT_CACHE_DIR", str(tmp_path))
        gates = _imp("writ.session.gates")
        calls: list[str] = []
        orig = gates._load_categories
        monkeypatch.setattr(gates, "_load_categories", lambda p: calls.append(p) or orig(p))
        _seed("g-w-skip", mode="work", gates_approved=["phase-a", "test-skeletons"], current_phase="implementation")
        gates._can_write_check("g-w-skip", _envelope("/tmp/proj/src/a.py"), str(SKILL_ROOT))
        assert calls == [], "both-approved path must NOT read gate-categories.json (A7)"

    def test_work_not_approved_still_reads_categories(self, tmp_path, monkeypatch):
        """A7 safety: when gates are NOT both approved, the exclusion check (and its
        categories read) MUST still run BEFORE the deny, so excluded paths (tests,
        migrations, __init__) stay writable pre-approval."""
        monkeypatch.setenv("WRIT_CACHE_DIR", str(tmp_path))
        gates = _imp("writ.session.gates")
        calls: list[str] = []
        orig = gates._load_categories
        monkeypatch.setattr(gates, "_load_categories", lambda p: calls.append(p) or orig(p))
        _seed("g-w-read", mode="work", gates_approved=[], current_phase="planning")
        gates._can_write_check("g-w-read", _envelope("/tmp/proj/src/a.py"), str(SKILL_ROOT))
        assert calls, "not-approved path must still read categories for the exclusion check (A7)"


class TestCategoriesFallbackResolves:
    """The gate-categories.json fallback (skill_dir="") must resolve to bin/lib via the skill root."""

    def test_excluded_path_allowed_via_fallback(self, tmp_path, monkeypatch):
        monkeypatch.setenv("WRIT_CACHE_DIR", str(tmp_path))
        f = _load_facade()
        _seed("g-exc", mode="work", gates_approved=[], current_phase="planning")
        # *__init__.py is an exclusion; with skill_dir="" the fallback must still find it.
        r = f._can_write_check("g-exc", _envelope("/tmp/proj/pkg/__init__.py"), "")
        assert r["can_write"] is True, "the gate-categories fallback failed to resolve exclusions"


class TestCanReadCodeGate:
    def test_non_runtime_mode_allows(self, tmp_path, monkeypatch):
        monkeypatch.setenv("WRIT_CACHE_DIR", str(tmp_path))
        f = _load_facade()
        _seed("g-read", mode="review")
        r = f._can_read_code_check("g-read", _envelope("/tmp/proj/src/a.py", tool_name="Grep"), "")
        assert r["can_read"] is True


class TestCmdEntrypoints:
    def test_cmd_can_write_emits_decision(self, tmp_path, monkeypatch, capsys):
        monkeypatch.setenv("WRIT_CACHE_DIR", str(tmp_path))
        f = _load_facade()
        _seed("g-cmd", mode=None)
        monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(_envelope("/tmp/proj/src/a.py"))))
        f.cmd_can_write("g-cmd", "")
        out = json.loads(capsys.readouterr().out)
        assert out["decision"] == "deny"


class TestEffectiveSourceTypeRelocated:
    def test_in_mode_engine(self):
        me = _imp("writ.session.mode_engine")
        assert hasattr(me, "_effective_source_type")
        assert me._effective_source_type({"mode": "debug"}) == "runtime"
        assert me._effective_source_type({"source_type": "web", "mode": "investigate"}) == "web"

    def test_facade_reexports_it(self):
        assert hasattr(_load_facade(), "_effective_source_type")


class TestSourceShape:
    def test_facade_no_inline_gate_defs(self):
        with open(FACADE_PATH) as f:
            src = f.read()
        assert "def _can_write_check(" not in src
        assert "def cmd_can_read_code(" not in src
        assert "from writ.session.gates import" in src

    def test_gates_defines_core(self):
        with open(GATES_PATH) as f:
            src = f.read()
        assert "def _can_write_check(" in src
        assert "_CODE_EXTENSIONS" in src

    def test_dead_detectors_removed(self):
        with open(FACADE_PATH) as f:
            fsrc = f.read()
        with open(GATES_PATH) as f:
            gsrc = f.read()
        assert "def _detect_language(" not in fsrc and "def _detect_language(" not in gsrc
        assert "def _detect_frameworks(" not in fsrc and "def _detect_frameworks(" not in gsrc
