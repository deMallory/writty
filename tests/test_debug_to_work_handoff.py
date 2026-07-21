"""Increment 6: Debug -> Work root-cause handoff.

When a session goes debug -> work and lands in planning, a populated debug.md
'## Root cause' is promoted into plan.md as a '## Root Cause Evidence' section,
and a debug_to_work_handoff friction event records evidence_present. The handoff
must never break the mode transition (graceful), is idempotent, and is skipped
when _mode_switch restores a paused (implementation) Work state.

Loads writ-session.py as a module (mirrors tests/test_mode_engine.py) and drives
real cmd_mode transitions with cwd chdir'd to a tmp project so the handoff's
cwd-based project-root detection resolves.
"""
from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir)))
from writ.shared.logging import read_streams, resolve_project  # noqa: E402

# Exercises the router's cwd-based project-scope resolution to a tmp subdir;
# opt out of the autouse WRIT_FRICTION_LOG redirect so events route to the
# split per-project streams under WRIT_LOG_ROOT (Phase 1.2 / P1 router).
pytestmark = pytest.mark.no_friction_isolation

HELPER_PATH = os.path.join(os.path.dirname(__file__), os.pardir, "bin", "lib", "writ-session.py")
_spec = importlib.util.spec_from_file_location("writ_session_handoff", HELPER_PATH)
writ_session = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(writ_session)

SID = "test-debug-handoff"

POPULATED = (
    "## Symptom\nSaves are slow for one SKU pattern.\n\n"
    "## Root cause\nThe guard compares the wrong field, so the fan-out fires "
    "8 times instead of once.\n\n## Fix\nCompare the canonical field.\n"
)
EMPTY_ROOT_CAUSE = "## Symptom\nSlow.\n\n## Root cause\n\n## Fix\n\n"


@pytest.fixture()
def session_id(tmp_path, monkeypatch):
    monkeypatch.setenv("WRIT_CACHE_DIR", str(tmp_path))
    return SID


@pytest.fixture()
def project(tmp_path, monkeypatch):
    root = tmp_path / "proj"
    (root / ".git").mkdir(parents=True)
    monkeypatch.chdir(root)  # handoff resolves project_root from cwd
    return root


def _events(project: Path) -> list[dict]:
    # debug_to_work_handoff routes to the P1 router's `friction` stream under
    # <WRIT_LOG_ROOT>/<project>/friction.jsonl; the project scope derives from
    # the tmp project cwd, so resolve it the same way the router does.
    return read_streams(resolve_project(str(project)), ["friction"])


def _handoff_events(project: Path) -> list[dict]:
    return [e for e in _events(project) if e.get("event") == "debug_to_work_handoff"]


def _set(session_id, mode):
    writ_session.cmd_mode(session_id, "set", mode)


class TestHandoffHelpers:
    def test_promote_helper_exists(self) -> None:
        assert hasattr(writ_session, "_promote_root_cause_to_plan")
        assert callable(writ_session._promote_root_cause_to_plan)

    def test_extract_root_cause_exists(self) -> None:
        assert hasattr(writ_session, "_extract_root_cause")

    def test_extract_root_cause_returns_body_when_populated(self, tmp_path) -> None:
        assert hasattr(writ_session, "_extract_root_cause"), "_extract_root_cause not defined yet"
        p = tmp_path / "debug.md"
        p.write_text(POPULATED)
        body = writ_session._extract_root_cause(str(p))
        assert body and "wrong field" in body

    def test_extract_root_cause_none_when_empty(self, tmp_path) -> None:
        assert hasattr(writ_session, "_extract_root_cause"), "_extract_root_cause not defined yet"
        p = tmp_path / "debug.md"
        p.write_text(EMPTY_ROOT_CAUSE)
        assert writ_session._extract_root_cause(str(p)) is None


class TestHandoffPromotion:
    def test_root_cause_promoted_into_plan(self, session_id, project) -> None:
        _set(session_id, "debug")
        (project / "debug.md").write_text(POPULATED)
        _set(session_id, "work")
        plan = (project / "plan.md")
        assert plan.exists(), "plan.md should be created/seeded by the handoff"
        body = plan.read_text()
        assert "## Root Cause Evidence" in body
        assert "wrong field" in body
        handoffs = _handoff_events(project)
        assert handoffs and handoffs[-1].get("evidence_present") is True

    def test_no_debug_md_is_graceful_noop(self, session_id, project) -> None:
        _set(session_id, "debug")
        _set(session_id, "work")
        # Transition still completed:
        assert writ_session._read_cache(session_id).get("mode") == "work"
        # plan.md not seeded:
        plan = project / "plan.md"
        assert (not plan.exists()) or ("## Root Cause Evidence" not in plan.read_text())
        handoffs = _handoff_events(project)
        assert handoffs and handoffs[-1].get("evidence_present") is False

    def test_empty_root_cause_not_promoted(self, session_id, project) -> None:
        _set(session_id, "debug")
        (project / "debug.md").write_text(EMPTY_ROOT_CAUSE)
        _set(session_id, "work")
        plan = project / "plan.md"
        assert (not plan.exists()) or ("## Root Cause Evidence" not in plan.read_text())
        handoffs = _handoff_events(project)
        assert handoffs and handoffs[-1].get("evidence_present") is False

    def test_handoff_is_idempotent(self, session_id, project) -> None:
        _set(session_id, "debug")
        (project / "debug.md").write_text(POPULATED)
        _set(session_id, "work")
        _set(session_id, "debug")
        _set(session_id, "work")
        body = (project / "plan.md").read_text()
        assert body.count("## Root Cause Evidence") == 1

    def test_transition_completes_to_work(self, session_id, project) -> None:
        """The mode change always completes (handoff is best-effort)."""
        _set(session_id, "debug")
        (project / "debug.md").write_text(POPULATED)
        _set(session_id, "work")
        assert writ_session._read_cache(session_id).get("mode") == "work"


class TestHandoffSkippedOnRestore:
    def test_switch_restore_does_not_seed(self, session_id, project) -> None:
        """_mode_switch restoring a paused implementation phase must NOT seed."""
        # Seed a debug session that has a paused Work state in implementation.
        cache = writ_session._read_cache(session_id)
        cache["mode"] = "debug"
        cache["current_phase"] = None
        cache["paused_work_state"] = {
            "phase": "implementation",
            "gates_approved": ["phase-a", "test-skeletons"],
            "loaded_rule_ids_by_phase": {},
        }
        writ_session._write_cache(session_id, cache)
        (project / "debug.md").write_text(POPULATED)

        writ_session.cmd_mode(session_id, "switch", "work")

        restored = writ_session._read_cache(session_id)
        assert restored.get("current_phase") == "implementation"
        plan = project / "plan.md"
        assert (not plan.exists()) or ("## Root Cause Evidence" not in plan.read_text())
