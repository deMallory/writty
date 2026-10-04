"""An auto-routed work session runs as an orchestrator and is told which workers to dispatch."""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
HOOK = REPO / "hooks" / "scripts" / "writ-rag-inject.sh"
HELPER = REPO / "bin" / "lib" / "writ-session.py"
BUILD = "implement the export endpoint from the approved plan"
AUDIT = "audit the codebase for security issues"
WORKERS = ("writ-planner", "writ-test-writer", "writ-implementer", "writ-reviewer")
AGENT_FILES = ("writ-explorer",) + WORKERS
# What the Mistty bridge sets: Vibe cannot dispatch Writ's roles.
NO_WORKERS = {"WRIT_WORKER_AGENTS": "none"}


def _home(tmp_path: Path) -> Path:
    """Hermetic HOME: empty unless _install_agents ran, so a bootstrap.sh install on the
    developer machine cannot flip the announced names to the bare form."""
    home = tmp_path / "home"
    home.mkdir(exist_ok=True)
    return home


def _install_agents(tmp_path: Path, roles=AGENT_FILES) -> None:
    agents = _home(tmp_path).joinpath(".claude", "agents")
    agents.mkdir(parents=True, exist_ok=True)
    for role in roles:
        (agents / f"{role}.md").write_text(f"---\nname: {role}\n---\n")


def _env(tmp_path: Path) -> dict:
    return {**os.environ, "HOME": str(_home(tmp_path)), "WRIT_CACHE_DIR": str(tmp_path / "cache"), "WRIT_PORT": "59995",
            "WRIT_HOST": "localhost", "WRIT_FRICTION_LOG": str(tmp_path / "friction.log"),
            "WRIT_LOG_ROOT": str(tmp_path / "logs"), "WRIT_NO_AUTOSTART": "1"}


def _sandbox(tmp_path: Path) -> Path:
    sandbox = tmp_path / "sandbox"
    (sandbox / ".claude" / "gates").mkdir(parents=True, exist_ok=True)
    (sandbox / ".git").mkdir(exist_ok=True)
    return sandbox


def _helper(tmp_path, *args):
    subprocess.run([sys.executable, str(HELPER), *args], env=_env(tmp_path), check=True,
                   capture_output=True, text=True, cwd=str(_sandbox(tmp_path)))


def _hook(tmp_path, sid, prompt, host_env=None) -> subprocess.CompletedProcess:
    r = subprocess.run(["bash", str(HOOK)], input=json.dumps({"session_id": sid, "prompt": prompt}),
                       env={**_env(tmp_path), **(host_env or {})}, capture_output=True, text=True, timeout=30,
                       cwd=str(_sandbox(tmp_path)))
    assert r.returncode == 0, r.stderr
    return r


def _cache(tmp_path, sid) -> dict:
    return json.loads((tmp_path / "cache" / f"writ-session-{sid}.json").read_text())


class TestTheHookOrchestratesWork:
    def test_a_first_route_into_work_marks_the_session_orchestrator(self, tmp_path):
        _hook(tmp_path, "ao-first", BUILD)
        cache = _cache(tmp_path, "ao-first")
        assert cache["mode"] == "work" and cache["is_orchestrator"] is True

    def test_an_investigate_route_does_not(self, tmp_path):
        _hook(tmp_path, "ao-inv", AUDIT)
        cache = _cache(tmp_path, "ao-inv")
        assert cache["mode"] == "investigate" and cache["is_orchestrator"] is False

    def test_a_switch_into_work_marks_the_session_orchestrator(self, tmp_path):
        _helper(tmp_path, "mode", "set", "investigate", "ao-switch")
        _hook(tmp_path, "ao-switch", BUILD)
        cache = _cache(tmp_path, "ao-switch")
        assert cache["mode"] == "work" and cache["is_orchestrator"] is True

    def test_the_announcement_names_the_four_workers_in_order(self, tmp_path):
        out = _hook(tmp_path, "ao-order", BUILD).stdout
        positions = [out.index(w) for w in WORKERS]
        assert positions == sorted(positions), positions
        assert "present them for approval" in out

    def test_the_override_is_the_path_free_command_with_the_real_id(self, tmp_path):
        out = _hook(tmp_path, "ao-override", BUILD).stdout
        assert "writ mode set conversation ao-override" in out

    def test_the_restore_announcement_names_the_next_workers(self, tmp_path):
        sid = "ao-restore"
        sandbox = _sandbox(tmp_path)
        (sandbox / "plan.md").write_text("# Plan: unchanged across the detour\n")
        _helper(tmp_path, "mode", "set", "work", sid)
        path = tmp_path / "cache" / f"writ-session-{sid}.json"
        data = json.loads(path.read_text())
        data["gates_approved"] = ["phase-a"]
        path.write_text(json.dumps(data))
        _hook(tmp_path, sid, AUDIT)
        out = _hook(tmp_path, sid, BUILD).stdout
        assert "paused work mode restored automatically" in out
        assert "writ-test-writer" in out and "writ-implementer" in out and "writ-reviewer" in out
        assert "present them for approval" not in out
        assert "writ mode set conversation ao-restore" in out


def _restore_announcement(tmp_path, sid, host_env=None) -> str:
    sandbox = _sandbox(tmp_path)
    (sandbox / "plan.md").write_text("# Plan: unchanged across the detour\n")
    _helper(tmp_path, "mode", "set", "work", sid)
    path = tmp_path / "cache" / f"writ-session-{sid}.json"
    data = json.loads(path.read_text())
    data["gates_approved"] = ["phase-a"]
    path.write_text(json.dumps(data))
    _hook(tmp_path, sid, AUDIT, host_env)
    return _hook(tmp_path, sid, BUILD, host_env).stdout


class TestAnnouncementsNameTheDispatchableRoles:
    def test_investigate_names_the_prefixed_explorer_under_an_empty_home(self, tmp_path):
        out = _hook(tmp_path, "an-inv", AUDIT).stdout
        assert "writ:writ-explorer" in out

    def test_work_names_the_prefixed_workers_in_order_under_an_empty_home(self, tmp_path):
        out = _hook(tmp_path, "an-work", BUILD).stdout
        names = [f"writ:{w}" for w in WORKERS]
        assert all(n in out for n in names), out
        positions = [out.index(n) for n in names]
        assert positions == sorted(positions), positions

    def test_restore_names_the_prefixed_next_workers_under_an_empty_home(self, tmp_path):
        out = _restore_announcement(tmp_path, "an-restore")
        assert "paused work mode restored automatically" in out
        for w in ("writ-test-writer", "writ-implementer", "writ-reviewer"):
            assert f"writ:{w}" in out, (w, out)

    def test_installed_agents_yield_bare_names_everywhere(self, tmp_path):
        _install_agents(tmp_path)
        inv = _hook(tmp_path, "an-bare-inv", AUDIT).stdout
        work = _hook(tmp_path, "an-bare-work", BUILD).stdout
        restore = _restore_announcement(tmp_path, "an-bare-restore")
        assert "writ-explorer" in inv and "writ:writ-" not in inv
        assert all(w in work for w in WORKERS) and "writ:writ-" not in work
        assert "writ-reviewer" in restore and "writ:writ-" not in restore


class TestAHostWithoutWorkerAgents:
    """The session does the work itself, so it is no orchestrator and is told no role."""

    def test_a_first_route_into_work_does_not_mark_the_session_orchestrator(self, tmp_path):
        _hook(tmp_path, "nw-first", BUILD, NO_WORKERS)
        cache = _cache(tmp_path, "nw-first")
        assert cache["mode"] == "work" and cache["is_orchestrator"] is False

    def test_a_switch_into_work_does_not_either(self, tmp_path):
        _helper(tmp_path, "mode", "set", "investigate", "nw-switch")
        _hook(tmp_path, "nw-switch", BUILD, NO_WORKERS)
        cache = _cache(tmp_path, "nw-switch")
        assert cache["mode"] == "work" and cache["is_orchestrator"] is False

    @pytest.mark.parametrize("prompt", [BUILD, AUDIT])
    def test_the_announcement_names_no_role(self, tmp_path, prompt):
        out = _hook(tmp_path, "nw-names", prompt, NO_WORKERS).stdout
        assert "mode set automatically" in out
        assert not any(role in out for role in AGENT_FILES), out

    def test_the_work_announcement_hands_each_step_to_the_session(self, tmp_path):
        out = _hook(tmp_path, "nw-steps", BUILD, NO_WORKERS).stdout
        assert "do each step yourself" in out
        assert "/templates/plan-template.md" in out
        assert "present them for approval and stop" in out
        assert "writ mode set conversation nw-steps" in out

    def test_the_restore_announcement_names_no_role(self, tmp_path):
        out = _restore_announcement(tmp_path, "nw-restore", NO_WORKERS)
        assert "paused work mode restored automatically" in out
        assert "Continue that cycle yourself" in out
        assert not any(role in out for role in AGENT_FILES), out


class TestTheModeEngineHonoursTheFlag:
    @pytest.fixture(autouse=True)
    def _iso(self, tmp_path, monkeypatch):
        monkeypatch.setenv("WRIT_CACHE_DIR", str(tmp_path / "cache"))
        monkeypatch.chdir(_sandbox(tmp_path))

    def test_switch_with_the_flag_sets_it(self):
        from writ.session import mode_engine
        from writ.session.cache import _read_cache
        mode_engine._mode_set("me-1", "investigate")
        mode_engine._mode_switch("me-1", "work", is_orchestrator=True)
        assert _read_cache("me-1")["is_orchestrator"] is True

    @pytest.mark.parametrize("before", [True, False])
    def test_switch_without_the_flag_leaves_it_alone(self, before):
        from writ.session import mode_engine
        from writ.session.cache import _read_cache
        mode_engine._mode_set("me-2", "investigate", is_orchestrator=before)
        mode_engine._mode_switch("me-2", "work")
        assert _read_cache("me-2")["is_orchestrator"] is before

    def test_an_init_that_declines_does_not_touch_it(self):
        from writ.session import mode_engine
        from writ.session.cache import _read_cache
        mode_engine._mode_set("me-3", "work")
        mode_engine._mode_init("me-3", "work", is_orchestrator=True)
        assert _read_cache("me-3")["is_orchestrator"] is False

    def test_the_cli_forwards_the_flag_for_switch(self, tmp_path):
        from writ.session.cache import _read_cache
        _helper(tmp_path, "mode", "set", "investigate", "me-4")
        _helper(tmp_path, "mode", "switch", "work", "me-4", "--orchestrator")
        assert _read_cache("me-4")["is_orchestrator"] is True
