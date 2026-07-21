"""INV-5: the audit lens wired for a single region.

The static analyzer's findings flow into the INV-2 citation_log as file
citations; the region's files are the INV-4 frozen coverage denominator; and a
presence synthesis gate refuses a conclusion with no coverage evidence behind it.
run-analysis.sh is reused UNCHANGED -- only invoked by the new orchestrator.

Loads writ-session.py as a module (mirrors tests/test_inv4_coverage_map.py).
"""
from __future__ import annotations

import importlib.util
import io
import json
import os
from pathlib import Path

import pytest

HELPER_PATH = os.path.join(os.path.dirname(__file__), os.pardir, "bin", "lib", "writ-session.py")
_spec = importlib.util.spec_from_file_location("writ_session_inv5", HELPER_PATH)
writ_session = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(writ_session)

SKILL_DIR = Path(__file__).resolve().parent.parent
AUDIT_REGION = SKILL_DIR / "bin" / "audit-region.sh"
SID = "test-inv5-audit"


def _seed(monkeypatch, tmp_path, **overrides):
    monkeypatch.setenv("WRIT_CACHE_DIR", str(tmp_path))
    cache = {
        "session_id": SID, "mode": "investigate", "is_subagent": False, "current_phase": None,
        "loaded_rule_ids": [], "loaded_rule_ids_by_phase": {}, "gates_approved": [],
        "citation_log": [], "pretool_queried_files": [], "coverage_scope": None,
    }
    cache.update(overrides)
    with open(writ_session._cache_path(SID), "w") as f:
        json.dump(cache, f)


def _freeze(files, **extra):
    payload = {"files": files}
    payload.update(extra)
    writ_session.cmd_update(SID, ["--freeze-scope", json.dumps(payload)])


def _record(monkeypatch, file, findings):
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(findings)))
    writ_session.cmd_record_analysis(SID, file)


def _finding(file, severity="error", rule="ENF-POST-007", tool="ruff", message="x"):
    return {"file": file, "line": 1, "severity": severity, "rule": rule, "tool": tool, "message": message}


def _gate(capsys):
    capsys.readouterr()
    writ_session.cmd_synthesis_gate(SID)
    return json.loads(capsys.readouterr().out)


def _file_rows():
    return [r for r in writ_session._read_cache(SID).get("citation_log", [])
            if r.get("artifact_type") == "file"]


class TestRecordAnalysis:
    def test_appends_file_citation_with_counts(self, tmp_path, monkeypatch) -> None:
        _seed(monkeypatch, tmp_path)
        _record(monkeypatch, "svc.py", [_finding("svc.py", "error"), _finding("svc.py", "warning")])
        rows = _file_rows()
        assert len(rows) == 1
        row = rows[0]
        assert row["ref"] == "svc.py"
        assert row.get("findings") == 2
        assert row.get("errors") == 1
        assert "excerpt" in row

    def test_clean_file_still_recorded_as_examined(self, tmp_path, monkeypatch) -> None:
        """A clean file (empty findings) is still examined -- presence of attention."""
        _seed(monkeypatch, tmp_path)
        _record(monkeypatch, "clean.py", [])
        rows = _file_rows()
        assert any(r["ref"] == "clean.py" for r in rows)
        clean = next(r for r in rows if r["ref"] == "clean.py")
        assert clean.get("findings") == 0
        assert clean.get("errors") == 0

    def test_recorded_file_feeds_coverage_map(self, tmp_path, monkeypatch, capsys) -> None:
        _seed(monkeypatch, tmp_path)
        _freeze(["svc.py", "other.py"])
        _record(monkeypatch, "svc.py", [_finding("svc.py")])
        capsys.readouterr()
        writ_session.cmd_coverage_map(SID)
        report = json.loads(capsys.readouterr().out)
        assert report["examined_in_scope"] == 1
        assert report["scope_total"] == 2


class TestSynthesisGate:
    def test_not_ready_without_frozen_scope(self, tmp_path, capsys, monkeypatch) -> None:
        _seed(monkeypatch, tmp_path)
        gate = _gate(capsys)
        assert gate["status"] == "synthesis_gate"
        assert gate["ready"] is False
        assert "scope" in gate["reason"].lower()

    def test_not_ready_with_zero_examined(self, tmp_path, capsys, monkeypatch) -> None:
        _seed(monkeypatch, tmp_path)
        _freeze(["a.py", "b.py"])
        gate = _gate(capsys)
        assert gate["ready"] is False

    def test_ready_once_in_scope_file_examined(self, tmp_path, monkeypatch, capsys) -> None:
        _seed(monkeypatch, tmp_path)
        _freeze(["a.py", "b.py"])
        _record(monkeypatch, "a.py", [_finding("a.py")])
        gate = _gate(capsys)
        assert gate["ready"] is True
        assert gate["coverage_pct"] == 50
        assert gate["unexamined_count"] == 1
        assert gate["full_coverage"] is False

    def test_full_coverage_flag(self, tmp_path, monkeypatch, capsys) -> None:
        _seed(monkeypatch, tmp_path)
        _freeze(["a.py"])
        _record(monkeypatch, "a.py", [])
        gate = _gate(capsys)
        assert gate["ready"] is True
        assert gate["full_coverage"] is True
        assert gate["coverage_pct"] == 100


class TestAuditRegionOrchestrator:
    """Lint-level: the orchestrator wires every stage (no live-linter dependency)."""

    def test_orchestrator_references_all_stages(self) -> None:
        assert AUDIT_REGION.exists(), f"{AUDIT_REGION} does not exist yet"
        body = AUDIT_REGION.read_text(encoding="utf-8")
        for token in ("--freeze-scope", "run-analysis.sh", "record-analysis",
                      "coverage-map", "synthesis-gate"):
            assert token in body, f"audit-region.sh must reference {token}"

    def test_orchestrator_does_not_modify_run_analysis(self) -> None:
        """It INVOKES run-analysis.sh; it must not redefine analyzer internals."""
        assert AUDIT_REGION.exists(), f"{AUDIT_REGION} does not exist yet"
        body = AUDIT_REGION.read_text(encoding="utf-8")
        assert "analyze_php()" not in body and "analyze_python()" not in body


class TestHermeticEndToEnd:
    """Prove the data flow region->citation->coverage->gate without installed linters."""

    def test_two_file_region_reaches_full_coverage_and_ready(self, tmp_path, monkeypatch, capsys) -> None:
        _seed(monkeypatch, tmp_path)
        _freeze(["a.py", "b.py"])
        _record(monkeypatch, "a.py", [_finding("a.py", "error")])
        _record(monkeypatch, "b.py", [])  # clean, still examined
        capsys.readouterr()
        writ_session.cmd_coverage_map(SID)
        cov = json.loads(capsys.readouterr().out)
        assert cov["coverage_pct"] == 100
        gate = _gate(capsys)
        assert gate["ready"] is True
        assert gate["full_coverage"] is True
