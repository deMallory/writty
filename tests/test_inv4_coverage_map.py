"""INV-4: frozen file-level coverage map + investigation-span budget.

Replaces the misleading domain-ratio coverage with an honest, ungameable one:
coverage = files examined in scope / files in a FROZEN scope. The denominator is
frozen once (`--freeze-scope`) so it cannot drift toward 100% by never widening
scope. The examined set reuses the INV-2 citation_log file rows UNION the existing
pretool_queried_files -- no new capture path.

Loads writ-session.py as a module (mirrors tests/test_inv2_citations.py).
"""
from __future__ import annotations

import importlib.util
import json
import os

import pytest

HELPER_PATH = os.path.join(os.path.dirname(__file__), os.pardir, "bin", "lib", "writ-session.py")
_spec = importlib.util.spec_from_file_location("writ_session_inv4", HELPER_PATH)
writ_session = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(writ_session)

SID = "test-inv4-coverage"


def _seed(monkeypatch, tmp_path, **overrides):
    monkeypatch.setenv("WRIT_CACHE_DIR", str(tmp_path))
    cache = {
        "session_id": SID, "mode": "investigate", "is_subagent": False, "current_phase": None,
        "loaded_rule_ids": [], "loaded_rule_ids_by_phase": {}, "gates_approved": [],
        "citation_log": [], "pretool_queried_files": [],
    }
    cache.update(overrides)
    with open(writ_session._cache_path(SID), "w") as f:
        json.dump(cache, f)


def _freeze(files, **extra):
    payload = {"files": files}
    payload.update(extra)
    writ_session.cmd_update(SID, ["--freeze-scope", json.dumps(payload)])


def _cite_file(ref):
    writ_session.cmd_update(SID, ["--add-citation", json.dumps(
        {"artifact_type": "file", "ref": ref, "excerpt": ""})])


def _map(capsys):
    capsys.readouterr()  # clear prior output
    writ_session.cmd_coverage_map(SID)
    return json.loads(capsys.readouterr().out)


class TestFreezeScope:
    def test_freeze_writes_frozen_scope(self, tmp_path, monkeypatch) -> None:
        _seed(monkeypatch, tmp_path)
        _freeze(["a.py", "b.py", "c.py"])
        scope = writ_session._read_cache(SID).get("coverage_scope")
        assert scope is not None
        assert sorted(scope.get("files", [])) == ["a.py", "b.py", "c.py"]
        assert scope.get("frozen_at"), "freeze must stamp frozen_at"

    def test_refreeze_without_force_is_noop(self, tmp_path, monkeypatch) -> None:
        """The frozen denominator must not silently grow -- the ungameable invariant."""
        _seed(monkeypatch, tmp_path)
        _freeze(["a.py", "b.py", "c.py"])
        _freeze(["a.py", "b.py", "c.py", "d.py", "e.py"])  # no force
        scope = writ_session._read_cache(SID).get("coverage_scope")
        assert len(scope.get("files", [])) == 3, "re-freeze without force must not change scope"

    def test_refreeze_with_force_overrides(self, tmp_path, monkeypatch) -> None:
        _seed(monkeypatch, tmp_path)
        _freeze(["a.py", "b.py", "c.py"])
        _freeze(["a.py", "b.py", "c.py", "d.py", "e.py"], force=True)
        scope = writ_session._read_cache(SID).get("coverage_scope")
        assert len(scope.get("files", [])) == 5, "force re-freeze must replace the scope"


class TestCoverageMap:
    def test_examined_in_scope_from_citation_and_pretool(self, tmp_path, capsys, monkeypatch) -> None:
        _seed(monkeypatch, tmp_path)
        _freeze(["a.py", "b.py", "c.py"])
        _cite_file("a.py")                                  # citation_log file row
        writ_session.cmd_update(SID, ["--add-pretool-file", "b.py"])  # pretool signal
        report = _map(capsys)
        assert report["status"] == "coverage_map"
        assert report["scope_total"] == 3
        assert report["examined_in_scope"] == 2
        assert report["coverage_pct"] == 67

    def test_out_of_scope_examined_is_drift_not_coverage(self, tmp_path, capsys, monkeypatch) -> None:
        _seed(monkeypatch, tmp_path)
        _freeze(["a.py", "b.py", "c.py"])
        _cite_file("z.py")                                  # examined, NOT in scope
        report = _map(capsys)
        assert report["scope_total"] == 3, "denominator counts only the frozen scope"
        assert report["examined_in_scope"] == 0
        assert "z.py" in report["out_of_scope_examined"]

    def test_frozen_denominator_unmoved_by_out_of_scope(self, tmp_path, capsys, monkeypatch) -> None:
        """Examining files outside scope cannot shrink coverage's denominator."""
        _seed(monkeypatch, tmp_path)
        _freeze(["a.py", "b.py", "c.py"])
        _cite_file("a.py")
        _cite_file("z.py")
        report = _map(capsys)
        assert report["scope_total"] == 3
        assert report["examined_in_scope"] == 1
        assert report["coverage_pct"] == 33

    def test_no_scope_status(self, tmp_path, capsys, monkeypatch) -> None:
        _seed(monkeypatch, tmp_path)
        report = _map(capsys)
        assert report["status"] == "no_scope"


class TestSpanBudget:
    def test_over_span_budget(self, tmp_path, capsys, monkeypatch) -> None:
        _seed(monkeypatch, tmp_path)
        _freeze(["a.py", "b.py", "c.py"], span_budget=2)
        for ref in ("a.py", "b.py", "c.py"):
            _cite_file(ref)
        report = _map(capsys)
        assert report["files_examined_total"] == 3
        assert report["over_span_budget"] is True
        assert report["span_remaining"] == 0

    def test_absent_span_budget_is_null(self, tmp_path, capsys, monkeypatch) -> None:
        _seed(monkeypatch, tmp_path)
        _freeze(["a.py", "b.py", "c.py"])
        _cite_file("a.py")
        report = _map(capsys)
        assert report.get("span_budget") is None
        assert report["over_span_budget"] is False
        assert report.get("span_remaining") is None


class TestLegacyCoverageUnchanged:
    """cmd_coverage keeps its legacy domain-ratio shape (consumers intact)."""

    def test_legacy_coverage_report_shape(self, tmp_path, capsys, monkeypatch) -> None:
        _seed(monkeypatch, tmp_path, files_written=["app.py"], loaded_rule_ids=["PY-STYLE-001"])
        capsys.readouterr()
        writ_session.cmd_coverage(SID)
        report = json.loads(capsys.readouterr().out)
        assert report["status"] == "coverage_report"
        assert "coverage_pct" in report
