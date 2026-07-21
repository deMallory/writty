"""INV-2: unified citation_log + the mode-agnostic _validate_citations detector.

command_log (7a) becomes a partition of one citation_log (artifact_type=command);
audit/explore/research add file/url rows. _validate_phase_a's cited-loaded
set-difference is extracted into _validate_citations(cited, available) -- the same
hallucination machine for every lens. Backward-compat: --add-command-run is
preserved (now a command-type citation), old command_log caches migrate.

Loads writ-session.py as a module (mirrors tests/test_mode_engine.py).
"""
from __future__ import annotations

import importlib.util
import json
import os

import pytest

HELPER_PATH = os.path.join(os.path.dirname(__file__), os.pardir, "bin", "lib", "writ-session.py")
_spec = importlib.util.spec_from_file_location("writ_session_inv2", HELPER_PATH)
writ_session = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(writ_session)

SID = "test-inv2-citations"

PLAN_CONTENT = """\
## Files
- service.py

## Analysis
Implement the thing with care.

## Rules Applied
- TEST-CI-001: all tests pass before merge.

## Capabilities
- [ ] the thing works
"""


def _seed(monkeypatch, tmp_path, **overrides):
    monkeypatch.setenv("WRIT_CACHE_DIR", str(tmp_path))
    cache = {
        "session_id": SID, "mode": "debug", "is_subagent": False, "current_phase": None,
        "loaded_rule_ids": [], "loaded_rule_ids_by_phase": {}, "gates_approved": [],
    }
    cache.update(overrides)
    with open(writ_session._cache_path(SID), "w") as f:
        json.dump(cache, f)


class TestValidateCitations:
    def test_exists(self) -> None:
        assert hasattr(writ_session, "_validate_citations") and callable(writ_session._validate_citations)

    def test_returns_cited_minus_available(self) -> None:
        assert hasattr(writ_session, "_validate_citations"), "_validate_citations not defined yet"
        assert writ_session._validate_citations({"A", "B"}, {"A"}) == {"B"}

    def test_empty_available_flags_nothing(self) -> None:
        """Mirrors _validate_phase_a's `if loaded_ids:` guard -- no available set, no false positives."""
        assert hasattr(writ_session, "_validate_citations"), "_validate_citations not defined yet"
        assert writ_session._validate_citations({"A"}, set()) == set()

    def test_subset_flags_nothing(self) -> None:
        assert hasattr(writ_session, "_validate_citations"), "_validate_citations not defined yet"
        assert writ_session._validate_citations({"A", "B"}, {"A", "B", "C"}) == set()


class TestValidatePhaseARegression:
    """The refactor onto _validate_citations must not change _validate_phase_a behavior."""

    def test_loaded_rule_passes(self, tmp_path, monkeypatch) -> None:
        _seed(monkeypatch, tmp_path, loaded_rule_ids=["TEST-CI-001"])
        (tmp_path / "plan.md").write_text(PLAN_CONTENT)
        assert writ_session._validate_phase_a(str(tmp_path), SID) is None

    def test_unloaded_rule_flagged_as_hallucinated(self, tmp_path, monkeypatch) -> None:
        _seed(monkeypatch, tmp_path, loaded_rule_ids=["OTHER-RULE-001"])
        (tmp_path / "plan.md").write_text(PLAN_CONTENT)
        err = writ_session._validate_phase_a(str(tmp_path), SID)
        assert err is not None and "TEST-CI-001" in err and "hallucinat" in err.lower()


class TestCitationLog:
    def test_add_citation_appends_typed_row(self, tmp_path, monkeypatch) -> None:
        _seed(monkeypatch, tmp_path)
        writ_session.cmd_update(SID, ["--add-citation", json.dumps(
            {"artifact_type": "file", "ref": "src/app.py:42", "excerpt": "raw SQL"})])
        log = writ_session._read_cache(SID).get("citation_log", [])
        assert len(log) == 1
        row = log[0]
        assert row.get("artifact_type") == "file"
        assert row.get("ref") == "src/app.py:42"
        assert "excerpt" in row and "ts" in row

    def test_add_citation_bounded_and_truncated(self, tmp_path, monkeypatch) -> None:
        _seed(monkeypatch, tmp_path)
        for i in range(15):
            writ_session.cmd_update(SID, ["--add-citation", json.dumps(
                {"artifact_type": "url", "ref": f"https://e/{i}", "excerpt": "z" * 5000})])
        log = writ_session._read_cache(SID).get("citation_log", [])
        assert len(log) <= 10
        assert len(log[-1]["excerpt"]) <= 500

    def test_add_command_run_is_a_command_citation(self, tmp_path, monkeypatch) -> None:
        """Backward-compat: --add-command-run still works, now writing a command-type citation."""
        _seed(monkeypatch, tmp_path)
        writ_session.cmd_update(SID, ["--add-command-run", json.dumps(
            {"command": "grep -rn X src/", "exit_code": 0, "output_excerpt": "src/x.py:1: X"})])
        log = writ_session._read_cache(SID).get("citation_log", [])
        cmd_rows = [r for r in log if r.get("artifact_type") == "command"]
        assert cmd_rows, "a command run must appear as a command-type citation"
        assert cmd_rows[-1].get("exit_code") == 0


class TestMigration:
    def test_old_command_log_migrates_to_citation_log(self, tmp_path, monkeypatch) -> None:
        monkeypatch.setenv("WRIT_CACHE_DIR", str(tmp_path))
        # Old (7a) cache shape: command_log, no citation_log.
        with open(writ_session._cache_path(SID), "w") as f:
            json.dump({
                "session_id": SID, "mode": "debug",
                "command_log": [{"command": "ls", "exit_code": 0, "output_excerpt": "a", "ts": "t"}],
            }, f)
        cache = writ_session._read_cache(SID)
        log = cache.get("citation_log", [])
        cmd_rows = [r for r in log if r.get("artifact_type") == "command"]
        assert cmd_rows, "old command_log rows must migrate into citation_log tagged command"
        assert cmd_rows[0].get("ref") == "ls" or cmd_rows[0].get("command") == "ls"
