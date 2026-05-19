"""Regression tests for the log_friction_event bash function in common.sh.

The function previously dropped JSON extras silently because the
`${4:-{}}` default-value syntax appended a stray `}` to the 4th argument,
breaking `json.loads` on the Python side. Tests here invoke the bash
function in a subprocess against an isolated cwd (with a project marker
so the function's log-resolution finds its workflow-friction.log) and
inspect the resulting log entry.
"""
from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
COMMON_SH = REPO / "bin" / "lib" / "common.sh"


def _make_project(tmp_path: Path) -> Path:
    """Create a tmp project root with a .git marker so log_friction_event
    walks up from tmp_path and writes to <tmp_path>/workflow-friction.log."""
    (tmp_path / ".git").mkdir()
    return tmp_path


def _invoke_log_friction(project: Path, sid: str, mode: str, event: str,
                         extras_json: str | None = None) -> subprocess.CompletedProcess:
    """Source common.sh and call log_friction_event in a clean subshell."""
    if extras_json is None:
        cmd = f'source "{COMMON_SH}" && log_friction_event "{sid}" "{mode}" "{event}"'
    else:
        cmd = (f'source "{COMMON_SH}" && '
               f"log_friction_event '{sid}' '{mode}' '{event}' '{extras_json}'")
    return subprocess.run(
        ["bash", "-c", cmd],
        cwd=str(project), capture_output=True, text=True,
    )


def _last_log_entry(project: Path) -> dict | None:
    log_path = project / "workflow-friction.log"
    if not log_path.is_file():
        return None
    lines = [ln for ln in log_path.read_text().splitlines() if ln.strip()]
    if not lines:
        return None
    return json.loads(lines[-1])


def test_extras_with_values_merge_into_entry(tmp_path):
    project = _make_project(tmp_path)
    extras = json.dumps({"hook_name": "writ-mark-pending-test", "file_path": "/foo/bar.php"})
    result = _invoke_log_friction(project, "sid-1", "work", "hook_execution", extras)
    assert result.returncode == 0, result.stderr

    entry = _last_log_entry(project)
    assert entry is not None, "no log entry written"
    assert entry["session"] == "sid-1"
    assert entry["mode"] == "work"
    assert entry["event"] == "hook_execution"
    assert entry["hook_name"] == "writ-mark-pending-test"
    assert entry["file_path"] == "/foo/bar.php"


def test_extras_with_nested_object_preserved(tmp_path):
    project = _make_project(tmp_path)
    extras = json.dumps({"result": {"code": 0, "files": ["a.php", "b.php"]}})
    result = _invoke_log_friction(project, "sid-2", "work", "hook_execution", extras)
    assert result.returncode == 0

    entry = _last_log_entry(project)
    assert entry is not None
    assert entry["result"] == {"code": 0, "files": ["a.php", "b.php"]}


def test_no_fourth_argument_writes_entry_without_extras(tmp_path):
    project = _make_project(tmp_path)
    result = _invoke_log_friction(project, "sid-3", "work", "hook_execution")
    assert result.returncode == 0

    entry = _last_log_entry(project)
    assert entry is not None
    assert entry["session"] == "sid-3"
    assert entry["event"] == "hook_execution"
    # Only the standard fields, nothing extra.
    assert set(entry.keys()) == {"ts", "session", "mode", "event"}


def test_empty_fourth_argument_writes_entry_without_extras(tmp_path):
    project = _make_project(tmp_path)
    result = _invoke_log_friction(project, "sid-4", "work", "hook_execution", "")
    assert result.returncode == 0

    entry = _last_log_entry(project)
    assert entry is not None
    assert set(entry.keys()) == {"ts", "session", "mode", "event"}


def test_malformed_extras_json_does_not_crash(tmp_path):
    project = _make_project(tmp_path)
    result = _invoke_log_friction(project, "sid-5", "work", "hook_execution",
                                  "{ not valid json")
    assert result.returncode == 0, result.stderr
    # No traceback in stderr from the inline Python.
    assert "Traceback" not in result.stderr

    entry = _last_log_entry(project)
    assert entry is not None
    # Standard fields only; the bad extras parse-fail is swallowed.
    assert set(entry.keys()) == {"ts", "session", "mode", "event"}


def test_extras_with_unicode_characters(tmp_path):
    project = _make_project(tmp_path)
    extras = json.dumps({"message": "café — done"})
    result = _invoke_log_friction(project, "sid-6", "work", "hook_execution", extras)
    assert result.returncode == 0

    entry = _last_log_entry(project)
    assert entry is not None
    assert entry["message"] == "café — done"


def test_empty_mode_normalized_to_null(tmp_path):
    project = _make_project(tmp_path)
    extras = json.dumps({"k": "v"})
    result = _invoke_log_friction(project, "sid-7", "", "subagent_complete", extras)
    assert result.returncode == 0

    entry = _last_log_entry(project)
    assert entry is not None
    assert entry["mode"] is None
    assert entry["k"] == "v"
