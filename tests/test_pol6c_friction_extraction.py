"""POL-6c: friction logging -> writ/session/friction.py (pure re-export).

_log_friction_event moves to writ/session/friction.py. It is self-contained (stdlib only,
no CACHE_DIR/config dependency), so the facade re-exports it directly. The 22 facade callers
and the 3 test files that reference it keep resolving the unchanged facade name.

Per TEST-TDD-001: skeletons approved before implementation. RED until the move lands.
"""

from __future__ import annotations

import importlib
import importlib.util
import json
import os
import sys

import pytest

SKILL_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
FACADE_PATH = os.path.join(SKILL_ROOT, "bin", "lib", "writ-session.py")
FRICTION_PATH = os.path.join(SKILL_ROOT, "writ", "session", "friction.py")


def _load_facade():
    spec = importlib.util.spec_from_file_location("writ_session_pol6c", FACADE_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _load_friction_module():
    if SKILL_ROOT not in sys.path:
        sys.path.insert(0, SKILL_ROOT)
    return importlib.import_module("writ.session.friction")


def _read_log_lines(project_root):
    log = os.path.join(str(project_root), "workflow-friction.log")
    if not os.path.exists(log):
        return []
    with open(log) as f:
        return [json.loads(line) for line in f if line.strip()]


class TestFrictionModuleExists:
    def test_friction_file_exists(self):
        assert os.path.isfile(FRICTION_PATH)

    def test_imports_as_package(self):
        assert _load_friction_module() is not None


class TestFrictionLogger:
    """The logger writes one JSON line at the marker-detected project root."""

    def test_appends_entry_at_project_root(self, tmp_path, monkeypatch):
        (tmp_path / ".git").mkdir()  # a project-root marker
        monkeypatch.chdir(tmp_path)
        friction = _load_friction_module()
        friction._log_friction_event("sid-1", "work", "phase_advance", gate="phase-a")
        lines = _read_log_lines(tmp_path)
        assert len(lines) == 1
        entry = lines[0]
        assert entry["session"] == "sid-1"
        assert entry["mode"] == "work"
        assert entry["event"] == "phase_advance"
        assert entry["gate"] == "phase-a"
        assert "ts" in entry

    def test_no_project_root_is_silent_noop(self, tmp_path, monkeypatch):
        # No marker anywhere up the tree from an isolated dir -> no write, no raise.
        deep = tmp_path / "a" / "b" / "c"
        deep.mkdir(parents=True)
        monkeypatch.chdir(deep)
        friction = _load_friction_module()
        # Guard: if some ancestor of tmp_path happens to carry a marker, skip the assertion.
        friction._log_friction_event("sid-2", None, "noop_test")
        assert not (deep / "workflow-friction.log").exists()


class TestFacadeReExport:
    def test_facade_exposes_logger(self):
        facade = _load_facade()
        assert callable(facade._log_friction_event)

    def test_facade_logger_writes_to_project_root(self, tmp_path, monkeypatch):
        (tmp_path / "pyproject.toml").write_text("[tool]\n")  # marker
        monkeypatch.chdir(tmp_path)
        facade = _load_facade()
        facade._log_friction_event("sid-f", "review", "write_attempt", result="allow")
        lines = _read_log_lines(tmp_path)
        assert any(e["event"] == "write_attempt" and e["result"] == "allow" for e in lines)


class TestSourceShape:
    def test_facade_no_inline_definition(self):
        with open(FACADE_PATH) as f:
            src = f.read()
        assert "def _log_friction_event(" not in src, (
            "the friction logger must move out of the facade"
        )
        assert "from writ.session.friction import _log_friction_event" in src

    def test_friction_defines_logger(self):
        with open(FRICTION_PATH) as f:
            src = f.read()
        assert "def _log_friction_event(" in src
