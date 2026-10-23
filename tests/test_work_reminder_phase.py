"""tests/test_work_reminder_phase.py

Pins plan.md "report one phase per session". A worker in a git worktree was told "plan
gate pending" by writ-rag-inject.sh while its session cache, the authority every gate
reads, said `testing`. The reminder decided from `.claude/gates/<sid>/*.approved`, which
a daemon older than the artifact writer never created. Both reminder hooks now read the
cache phase, so every hook reports the same phase whatever is on disk.

RED today: writ-rag-inject.sh says "plan gate pending" for a `testing` or
`implementation` session with no gate files, and inject-tier-workflow.sh prints the
workflow instructions for a session past planning when the gate file is missing.

Phase mapping, from plan.md: `planning` names the plan gate, `testing` the
test-skeletons gate, anything later prints nothing.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from tests.fixtures.session_state import sandbox_cwd  # noqa: F401
import tests.test_session_scoped_gate_artifacts as scoped
from tests.test_peer_prompt_trace import _git_worktree
from tests.test_session_scoped_gate_artifacts import (
    INJECT_TIER_WORKFLOW,
    RAG_INJECT,
    _env,
    _seed_work_cache,
    _sid,
    _stub_daemon,
)

PLAN_REMINDER = "plan gate pending"
SKEL_REMINDER = "test-skeletons gate pending"


def _gate_files(project_root: Path, sid: str, *gates: str) -> None:
    d = project_root / ".claude" / "gates" / sid
    d.mkdir(parents=True, exist_ok=True)
    for gate in gates:
        (d / f"{gate}.approved").write_text(sid + "\n")


@pytest.fixture()
def project(tmp_path):
    """A worker's shape from the live failure: cwd is a git worktree of the repo."""
    wt = _git_worktree(tmp_path)
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir()
    return wt, cache_dir, _sid("phase")


def _reminder(project_root: Path, cache_dir: Path, sid: str, phase: str) -> str:
    # Through the module, not a name import: a Test* class in this namespace is collected
    # and its tests would run twice.
    helper = scoped.TestWorkModeReminderIsSessionScoped()
    routes = helper._routes(sid)
    # The hook reads the cache from the daemon first, so the stub serves the seeded phase.
    routes[f"/session/{sid}"][1]["current_phase"] = phase
    with _stub_daemon(routes) as (host, port):
        proc = subprocess.run(
            ["bash", str(RAG_INJECT)], input=helper._envelope(sid),
            capture_output=True, text=True, timeout=30,
            env={**_env(cache_dir), "WRIT_HOST": host, "WRIT_PORT": port},
            cwd=str(project_root),
        )
    assert proc.returncode == 0, proc.stderr
    assert "server unavailable" not in proc.stdout, proc.stdout
    return proc.stdout


def _workflow_text(project_root: Path, cache_dir: Path, sid: str) -> str:
    envelope = json.dumps({
        "session_id": sid, "tool_name": "Bash",
        "tool_input": {"command": f"python3 bin/lib/writ-session.py mode set work {sid}"},
        "tool_output": "set: work\n",
    })
    proc = subprocess.run(
        ["bash", str(INJECT_TIER_WORKFLOW)], input=envelope,
        capture_output=True, text=True, timeout=30,
        env=_env(cache_dir), cwd=str(project_root),
    )
    assert proc.returncode == 0, proc.stderr
    out = json.loads(proc.stdout) if proc.stdout.strip() else {}
    return out.get("hookSpecificOutput", {}).get("additionalContext", "")


class TestRagInjectReminderFollowsTheCachePhase:
    @pytest.mark.parametrize("with_files", [False, True])
    def test_planning_names_the_plan_gate(self, project, with_files):
        wt, cache_dir, sid = project
        _seed_work_cache(cache_dir, sid, wt, current_phase="planning")
        if with_files:
            _gate_files(wt, sid, "phase-a")  # a stale file must not hide the gate
        out = _reminder(wt, cache_dir, sid, "planning")
        assert PLAN_REMINDER in out, out

    def test_testing_names_the_test_skeletons_gate_with_no_gate_files(self, project):
        wt, cache_dir, sid = project
        _seed_work_cache(cache_dir, sid, wt, current_phase="testing",
                         gates_approved=["phase-a"])
        out = _reminder(wt, cache_dir, sid, "testing")
        assert SKEL_REMINDER in out, out
        assert PLAN_REMINDER not in out, out

    def test_implementation_is_silent_with_no_gate_files(self, project):
        wt, cache_dir, sid = project
        _seed_work_cache(cache_dir, sid, wt, current_phase="implementation",
                         gates_approved=["phase-a", "test-skeletons"])
        out = _reminder(wt, cache_dir, sid, "implementation")
        assert PLAN_REMINDER not in out and SKEL_REMINDER not in out, out


class TestInjectTierWorkflowFollowsTheCachePhase:
    def test_planning_prints_the_workflow_instructions(self, project):
        wt, cache_dir, sid = project
        _seed_work_cache(cache_dir, sid, wt, current_phase="planning")
        assert "STOP. Do NOT write any code yet" in _workflow_text(wt, cache_dir, sid)

    def test_a_later_phase_skips_them_with_no_gate_files(self, project):
        wt, cache_dir, sid = project
        _seed_work_cache(cache_dir, sid, wt, current_phase="testing",
                         gates_approved=["phase-a"])
        assert "STOP. Do NOT write any code yet" not in _workflow_text(wt, cache_dir, sid)
