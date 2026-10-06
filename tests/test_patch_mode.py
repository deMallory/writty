"""RED-phase skeletons for the patch mode (tier-based routing, ENF-ROUTE-001).

Patch mode is tier-1 routing ported from Phaselock's ENF-ROUTE-001: code writes
allowed with no phase gates, bounded to gates.PATCH_FILE_LIMIT (3) distinct
working files per session. Past the bound the write is refused with
ENF-GATE-PATCH and the session must enter work mode and pass the plan gate.

Every test here fails until the implementation lands (patch is not in
MODE_CONFIG yet); that RED is the skeleton gate. Hermetic: no daemon, no
network; the hook test runs the real script with a stdin envelope and a
sandboxed cache (sandbox_cwd, per this repo's per-module autouse convention).
"""
from __future__ import annotations

import importlib
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

# autouse: pins cwd to a sandbox so a stray cache write cannot touch THIS
# repo's own gate artifacts, and points WRIT_CACHE_DIR at tmp_path.
from tests.fixtures.session_state import sandbox_cwd  # noqa: F401

SKILL_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
HOOKS = Path(SKILL_ROOT) / "hooks" / "scripts"
INJECT_TIER_WORKFLOW = HOOKS / "inject-tier-workflow.sh"


def _imp(name):
    if SKILL_ROOT not in sys.path:
        sys.path.insert(0, SKILL_ROOT)
    return importlib.import_module(name)


def _seed(sid, **fields):
    cache = _imp("writ.session.cache")
    data = cache._read_cache(sid)
    data.update(fields)
    cache._write_cache(sid, data)


def _write_check(sid, path):
    """The same decision the PreToolUse hook curls for: allow or refuse one write."""
    gates = _imp("writ.session.gates")
    return gates._can_write_check(sid, {"tool_input": {"file_path": path}}, SKILL_ROOT)


def _read(sid):
    return _imp("writ.session.cache")._read_cache(sid)


def test_mode_set_patch_is_valid():
    """`writ mode set patch` is accepted and initializes gate-free state."""
    engine = _imp("writ.session.mode_engine")
    assert "patch" in engine.VALID_MODES, "patch must be one MODE_CONFIG entry"
    engine.cmd_mode("patch-valid", "set", "patch")
    cache = _read("patch-valid")
    assert cache["mode"] == "patch"
    assert cache["gates_approved"] == []


def test_patch_allows_source_write_with_no_gates(tmp_path):
    """Tier-1: a source write needs no plan and no test-skeleton approval."""
    sid = "patch-allow"
    _seed(sid, mode="patch", gates_approved=[], project_root=str(tmp_path))
    res = _write_check(sid, str(tmp_path / "src" / "main.py"))
    assert res["can_write"] is True, res["reason"]
    assert res["reason"] is None


def test_patch_denies_fourth_distinct_file(tmp_path):
    """The tier's whole contract: file 4 is refused and names the work-mode exit."""
    sid = "patch-bound"
    _seed(sid, mode="patch", gates_approved=[], project_root=str(tmp_path))
    for name in ("a.py", "b.py", "c.py"):
        res = _write_check(sid, str(tmp_path / name))
        assert res["can_write"] is True, f"{name} must be writable: {res['reason']}"
    res = _write_check(sid, str(tmp_path / "d.py"))
    assert res["can_write"] is False, "the 4th distinct file must be refused"
    assert "ENF-GATE-PATCH" in res["reason"]
    assert "writ mode set work" in res["reason"]


def test_patch_repeat_write_same_file_not_recounted(tmp_path):
    """Edits to an already-counted file stay on the in-memory path (process budget)."""
    sid = "patch-recount"
    _seed(sid, mode="patch", gates_approved=[], project_root=str(tmp_path))
    assert _write_check(sid, str(tmp_path / "a.py"))["can_write"] is True
    assert _write_check(sid, str(tmp_path / "a.py"))["can_write"] is True
    assert _read(sid)["patch_files"] == [str(tmp_path / "a.py")]


def test_patch_budget_resets_on_mode_set_work():
    """Every explicit `mode set` starts a fresh task, so the patch budget clears."""
    engine = _imp("writ.session.mode_engine")
    cache = {
        "mode": "patch",
        "patch_files": ["/proj/a.py"],
        "gates_approved": ["phase-a"],
    }
    engine._apply_mode_set(cache, "work", mode_source=engine.MODE_SOURCE_EXPLICIT)
    assert cache["mode"] == "work"
    assert cache["patch_files"] == []
    assert cache["gates_approved"] == []


def test_patch_project_boundary_pre_approval(tmp_path):
    """A patch has no plan, so nothing outside the project is pre-declared."""
    sid = "patch-boundary"
    _seed(sid, mode="patch", gates_approved=[],
          project_root=str(tmp_path / "proj"),
          scratch_zone=str(tmp_path / "tmp"))
    res = _write_check(sid, str(tmp_path / "elsewhere" / "x.py"))
    assert res["can_write"] is False, "an out-of-project write must be refused"
    assert "ENF-PROJECT-BOUNDARY" in res["reason"]


def test_mode_usage_string_lists_patch(capsys):
    """The hardcoded usage line names every mode; patch must not be missing."""
    engine = _imp("writ.session.mode_engine")
    with pytest.raises(SystemExit) as exc:
        engine.cmd_mode("patch-usage", "set", None)
    assert exc.value.code == 2
    assert "patch" in capsys.readouterr().err


def test_inject_tier_workflow_patch_instructions(tmp_path):
    """`mode set patch` in a Bash call injects the patch workflow text."""
    env = os.environ.copy()
    env["WRIT_CACHE_DIR"] = str(tmp_path / "cache")
    env["WRIT_LOG_ROOT"] = str(tmp_path / "logs")
    env["WRIT_PORT"] = "19999"
    env.pop("WRIT_FRICTION_LOG", None)
    (tmp_path / "cache").mkdir(parents=True, exist_ok=True)
    payload = {
        "session_id": "patch-inject",
        "hook_event_name": "PostToolUse",
        "tool_name": "Bash",
        "tool_input": {"command": "writ mode set patch patch-inject"},
        "tool_output": "set: patch",
    }
    out = subprocess.run(["bash", str(INJECT_TIER_WORKFLOW)],
                         input=json.dumps(payload), capture_output=True,
                         text=True, env=env, timeout=120, check=False)
    assert out.returncode == 0, out.stderr
    assert "Patch mode" in out.stdout, (
        "the hook must deliver the patch workflow via additionalContext"
    )
    assert "3 distinct files" in out.stdout
