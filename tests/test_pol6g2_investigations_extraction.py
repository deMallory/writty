"""POL-6g-2: the investigation engine -> writ/session/investigations.py.

The coverage / audit-fanout / research-triangulation / lens cluster (15 fns + 6 constants)
moves to investigations.py, importing only lower layers. EXT_TO_DOMAIN relocates to config
(shared with 6g-3 feedback). RED until the move lands.

Per TEST-TDD-001: skeletons approved before implementation. Deep INV behavior is already
covered by test_inv*.py via the re-export; this pins the extraction + representative behavior.
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
INV_PATH = os.path.join(SKILL_ROOT, "writ", "session", "investigations.py")
CONFIG_PATH = os.path.join(SKILL_ROOT, "writ", "session", "config.py")

MOVED_FNS = [
    "cmd_coverage", "_examined_files", "cmd_coverage_map", "_parse_findings",
    "cmd_record_analysis", "cmd_synthesis_gate", "_file_loc", "cmd_scope_estimate",
    "cmd_partition_scope", "cmd_coverage_rollup", "cmd_aggregate_findings",
    "_independent_domain", "cmd_triangulation_gate", "cmd_staleness_check", "cmd_lens",
]
MOVED_CONSTS = [
    "_COVERAGE_SAMPLE_MAX", "_AUDIT_BUDGET_LOC", "_AUDIT_BUDGET_FILES",
    "_ATTENTION_ERROR_WEIGHT", "_TRIANGULATION_MIN_DOMAINS", "_LENS_TABLE",
]


def _load_facade():
    spec = importlib.util.spec_from_file_location("writ_session_pol6g2", FACADE_PATH)
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


def _call_json(fn, *args, stdin=None, monkeypatch=None):
    if stdin is not None:
        monkeypatch.setattr("sys.stdin", io.StringIO(stdin))
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        fn(*args)
    return json.loads(buf.getvalue().strip())


# --------------------------------------------------------------------------- #
# module + acyclic
# --------------------------------------------------------------------------- #
class TestInvestigationsModule:
    def test_module_exists(self):
        assert os.path.isfile(INV_PATH)

    def test_imports(self):
        assert _imp("writ.session.investigations") is not None

    def test_acyclic_no_facade_import(self):
        imports = _import_lines(INV_PATH)
        assert "writ_session" not in imports and "writ-session" not in imports
        with open(INV_PATH) as f:
            assert "spec_from_file_location" not in f.read()

    def test_imports_lower_layers(self):
        with open(INV_PATH) as f:
            src = f.read()
        assert "from writ.session.cache import" in src
        assert "from writ.session.citations import" in src
        assert "from writ.session.mode_engine import" in src
        assert "from writ.session.config import" in src


class TestExtToDomainRelocated:
    def test_config_owns_ext_to_domain(self):
        cfg = _imp("writ.session.config")
        assert cfg.EXT_TO_DOMAIN[".py"] == "python"
        assert cfg.EXT_TO_DOMAIN[".ts"] == "typescript"

    def test_facade_reexports_ext_to_domain(self):
        f = _load_facade()
        assert f.EXT_TO_DOMAIN[".go"] == "go"

    def test_facade_has_no_inline_ext_to_domain(self):
        with open(FACADE_PATH) as f:
            assert "EXT_TO_DOMAIN = {" not in f.read()


# --------------------------------------------------------------------------- #
# representative behavior (through the facade)
# --------------------------------------------------------------------------- #
class TestCoverage:
    def test_coverage_no_files(self, tmp_path, monkeypatch):
        monkeypatch.setenv("WRIT_CACHE_DIR", str(tmp_path))
        f = _load_facade()
        sid = f"inv-{uuid.uuid4().hex[:8]}"
        _seed(sid, files_written=[])
        r = _call_json(f.cmd_coverage, sid)
        assert r["status"] == "no_files"

    def test_coverage_map_no_scope(self, tmp_path, monkeypatch):
        monkeypatch.setenv("WRIT_CACHE_DIR", str(tmp_path))
        f = _load_facade()
        sid = f"inv-{uuid.uuid4().hex[:8]}"
        _seed(sid)
        r = _call_json(f.cmd_coverage_map, sid)
        assert r["status"] == "no_scope"

    def test_coverage_map_counts_frozen_scope(self, tmp_path, monkeypatch):
        monkeypatch.setenv("WRIT_CACHE_DIR", str(tmp_path))
        f = _load_facade()
        sid = f"inv-{uuid.uuid4().hex[:8]}"
        _seed(
            sid,
            coverage_scope={"frozen_at": "2026-01-01T00:00:00Z", "files": ["a.py", "b.py"]},
            pretool_queried_files=["a.py"],
        )
        r = _call_json(f.cmd_coverage_map, sid)
        assert r["status"] == "coverage_map"
        assert r["scope_total"] == 2
        assert r["examined_in_scope"] == 1
        assert r["coverage_pct"] == 50


class TestRecordAnalysisAndSynthesis:
    def test_record_analysis_appends_file_citation(self, tmp_path, monkeypatch):
        monkeypatch.setenv("WRIT_CACHE_DIR", str(tmp_path))
        f = _load_facade()
        sid = f"inv-{uuid.uuid4().hex[:8]}"
        _seed(sid)
        r = _call_json(
            f.cmd_record_analysis, sid, "x.py",
            stdin=json.dumps([{"severity": "error", "rule": "SEC-001"}]),
            monkeypatch=monkeypatch,
        )
        assert r["status"] == "recorded" and r["findings"] == 1 and r["errors"] == 1
        cache = _imp("writ.session.cache")._read_cache(sid)
        assert "x.py" in cache["pretool_queried_files"]
        assert any(c.get("ref") == "x.py" and c.get("artifact_type") == "file"
                   for c in cache["citation_log"])

    def test_synthesis_gate_not_ready_without_scope(self, tmp_path, monkeypatch):
        monkeypatch.setenv("WRIT_CACHE_DIR", str(tmp_path))
        f = _load_facade()
        sid = f"inv-{uuid.uuid4().hex[:8]}"
        _seed(sid)
        r = _call_json(f.cmd_synthesis_gate, sid)
        assert r["status"] == "synthesis_gate" and r["ready"] is False


class TestTriangulation:
    def test_blocked_under_min_domains(self, tmp_path, monkeypatch):
        monkeypatch.setenv("WRIT_CACHE_DIR", str(tmp_path))
        f = _load_facade()
        sid = f"inv-{uuid.uuid4().hex[:8]}"
        _seed(sid, citation_log=[{"artifact_type": "url", "ref": "https://www.python.org/a"}])
        r = _call_json(f.cmd_triangulation_gate, sid)
        assert r["blocked"] is True and r["domain_count"] == 1

    def test_triangulated_at_min_domains(self, tmp_path, monkeypatch):
        monkeypatch.setenv("WRIT_CACHE_DIR", str(tmp_path))
        f = _load_facade()
        sid = f"inv-{uuid.uuid4().hex[:8]}"
        _seed(sid, citation_log=[
            {"artifact_type": "url", "ref": "https://docs.python.org/3/x"},
            {"artifact_type": "url", "ref": "https://realpython.com/y"},
        ])
        r = _call_json(f.cmd_triangulation_gate, sid)
        assert r["triangulated"] is True and r["domain_count"] == 2

    def test_independent_domain_collapses_subdomains(self):
        inv = _imp("writ.session.investigations")
        assert inv._independent_domain("https://www.python.org/a") == "python.org"
        assert inv._independent_domain("https://docs.python.org/b") == "python.org"


class TestLens:
    def test_no_lens_when_unset(self, tmp_path, monkeypatch):
        monkeypatch.setenv("WRIT_CACHE_DIR", str(tmp_path))
        f = _load_facade()
        sid = f"inv-{uuid.uuid4().hex[:8]}"
        _seed(sid, mode="investigate")
        r = _call_json(f.cmd_lens, sid)
        assert r["status"] == "no_lens"

    def test_web_lens_maps_to_triangulation_gate(self, tmp_path, monkeypatch):
        monkeypatch.setenv("WRIT_CACHE_DIR", str(tmp_path))
        f = _load_facade()
        sid = f"inv-{uuid.uuid4().hex[:8]}"
        _seed(sid, mode="investigate", source_type="web")
        r = _call_json(f.cmd_lens, sid)
        assert r["status"] == "lens"
        assert r["lens"] == "research"
        assert r["enforcing_gate"] == "triangulation-gate"
        assert r["gate_strictness"] == "hard"


# --------------------------------------------------------------------------- #
# main()'s constant refs + source shape
# --------------------------------------------------------------------------- #
class TestFacadeReexports:
    def test_audit_budget_constants_reexported(self):
        f = _load_facade()
        assert f._AUDIT_BUDGET_LOC == 2000
        assert f._AUDIT_BUDGET_FILES == 30

    def test_lens_table_and_samples_reexported(self):
        f = _load_facade()
        assert f._COVERAGE_SAMPLE_MAX == 50
        assert f._TRIANGULATION_MIN_DOMAINS == 2
        assert "web" in f._LENS_TABLE


class TestSourceShape:
    def test_facade_no_inline_defs(self):
        with open(FACADE_PATH) as f:
            src = f.read()
        for name in MOVED_FNS:
            assert f"def {name}(" not in src, f"{name} still inline in facade"

    def test_facade_reimports_investigations(self):
        with open(FACADE_PATH) as f:
            assert "from writ.session.investigations import" in f.read()

    def test_module_defines_symbols(self):
        with open(INV_PATH) as f:
            src = f.read()
        for name in MOVED_FNS:
            assert f"def {name}(" in src, f"{name} missing from investigations.py"
        for const in MOVED_CONSTS:
            assert const in src, f"{const} missing from investigations.py"
