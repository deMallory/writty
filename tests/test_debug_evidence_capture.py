"""Increment 7a (INV-2): verifiable debug evidence (no MCP).

Auto-capture each debug-mode Bash run as a command-type citation in the unified
session citation_log ({artifact_type, ref, excerpt, exit_code, ts}), and surface
an advisory `evidence_backed` signal on the debug source-edit gate (the gate's
allow/deny DECISION is unchanged from Increment 4). Moves debug evidence from
free text toward "a command that actually ran" -- the strongest non-MCP step.

INV-2: command_log folded into citation_log (command partition); these 7a
assertions read citation_log command rows against the unified structure.

Loads writ-session.py as a module (mirrors tests/test_mode_engine.py).
"""
from __future__ import annotations

import importlib.util
import json
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir)))
from writ.shared.logging import read_streams, resolve_project  # noqa: E402

# Exercises the router's cwd-based project-scope resolution to a tmp subdir;
# opt out of the autouse WRIT_FRICTION_LOG redirect so gate events route to the
# split per-project streams under WRIT_LOG_ROOT (Phase 1.2 / P1 router).
pytestmark = pytest.mark.no_friction_isolation

HELPER_PATH = os.path.join(os.path.dirname(__file__), os.pardir, "bin", "lib", "writ-session.py")
_spec = importlib.util.spec_from_file_location("writ_session_evidence", HELPER_PATH)
writ_session = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(writ_session)

HOOK = os.path.join(os.path.dirname(__file__), os.pardir, "hooks", "scripts", "inject-tier-workflow.sh")
SID = "test-debug-evidence"

ROOT_CAUSE_MD = "## Symptom\nslow\n\n## Root cause\nOff-by-one in the fan-out guard.\n\n## Fix\nx\n"


def _seed(monkeypatch, tmp_path, **overrides):
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir(exist_ok=True)
    monkeypatch.setenv("WRIT_CACHE_DIR", str(cache_dir))
    cache = {
        "session_id": SID, "mode": "debug", "is_subagent": False, "current_phase": None,
        "remaining_budget": 5000, "loaded_rule_ids": [], "loaded_rule_ids_by_phase": {},
        "gates_approved": [], "denial_counts": {},
    }
    cache.update(overrides)
    with open(writ_session._cache_path(SID), "w") as f:
        json.dump(cache, f)


def _events(project: Path) -> list[dict]:
    # The debug source-edit gate emits debug_gate_root_cause_populated (audit
    # stream) / debug_gate_source_edit_denied (audit stream) via the P1 router.
    # Union the audit + friction streams for the project scope derived from cwd.
    return read_streams(resolve_project(str(project)), ["audit", "friction"])


class TestCommandRunVerb:
    """cmd_update --add-command-run appends a bounded, truncated record."""

    def test_add_command_run_appends_record(self, tmp_path, monkeypatch) -> None:
        _seed(monkeypatch, tmp_path)
        writ_session.cmd_update(SID, ["--add-command-run", json.dumps(
            {"command": "grep -n foo bar.py", "exit_code": 0, "output_excerpt": "12: foo"})])
        log = writ_session._read_cache(SID).get("citation_log", [])
        assert len(log) == 1
        entry = log[0]
        assert entry.get("artifact_type") == "command"
        assert entry.get("ref") == "grep -n foo bar.py"
        assert entry.get("exit_code") == 0
        assert "excerpt" in entry and "ts" in entry

    def test_command_log_is_bounded(self, tmp_path, monkeypatch) -> None:
        _seed(monkeypatch, tmp_path)
        for i in range(15):
            writ_session.cmd_update(SID, ["--add-command-run", json.dumps(
                {"command": f"cmd-{i}", "exit_code": 0, "output_excerpt": "x"})])
        log = writ_session._read_cache(SID).get("citation_log", [])
        assert len(log) <= 10, f"citation_log must be bounded; got {len(log)}"
        assert log[-1]["ref"] == "cmd-14", "newest run must be retained"
        assert all(e["ref"] != "cmd-0" for e in log), "oldest run must be dropped"

    def test_output_excerpt_is_truncated(self, tmp_path, monkeypatch) -> None:
        _seed(monkeypatch, tmp_path)
        writ_session.cmd_update(SID, ["--add-command-run", json.dumps(
            {"command": "noisy", "exit_code": 0, "output_excerpt": "y" * 5000})])
        entry = writ_session._read_cache(SID)["citation_log"][-1]
        assert len(entry["excerpt"]) <= 500, "excerpt must be truncated"


class TestAutoCaptureHookStructure:
    """The PostToolUse Bash hook records commands in debug mode (lint-level)."""

    def test_hook_references_command_capture(self) -> None:
        with open(HOOK) as f:
            body = f.read()
        assert "--add-command-run" in body, (
            "the PostToolUse Bash hook must record runs via --add-command-run"
        )
        assert "debug" in body, "command capture must be gated on debug mode"


class TestEvidenceBackedSignal:
    """The debug source-edit gate logs evidence_backed; its DECISION is unchanged."""

    def test_evidence_backed_true_logged_when_commands_present(self, tmp_path, monkeypatch) -> None:
        _seed(monkeypatch, tmp_path, command_log=[{"command": "psql -c ...", "exit_code": 0, "output_excerpt": "1 row"}])
        project = tmp_path / "proj"
        (project / ".git").mkdir(parents=True)
        (project / "debug.md").write_text(ROOT_CAUSE_MD)
        (project / "src").mkdir()
        monkeypatch.chdir(project)
        result = writ_session._can_write_check(SID, {"tool_input": {"file_path": str(project / "src" / "app.py")}})
        assert result["can_write"] is True, "Inc4 decision unchanged: populated root cause -> allow"
        gate_events = [e for e in _events(project) if "evidence_backed" in e]
        assert gate_events, "a debug-gate friction event must record evidence_backed"
        assert gate_events[-1]["evidence_backed"] is True

    def test_decision_unchanged_deny_without_root_cause(self, tmp_path, monkeypatch) -> None:
        _seed(monkeypatch, tmp_path, command_log=[{"command": "ls", "exit_code": 0, "output_excerpt": ""}])
        project = tmp_path / "proj2"
        (project / ".git").mkdir(parents=True)
        (project / "src").mkdir()
        # chdir so the gate's friction event marker-walks to proj2 (under tmp), not the
        # repo log -- this test is opted out of the env redirect and does not read the log.
        monkeypatch.chdir(project)
        result = writ_session._can_write_check(
            SID, {"tool_input": {"file_path": str(project / "src" / "app.py")}})
        assert result["can_write"] is False
        assert "DEBUG-GATE-ROOT-CAUSE" in (result.get("reason") or "")
