"""User-only Writ commands in a mistty session (writ/harness/vibe_user.py, bin/mistty).

The user types `!mistty approve|replan|grant manual-test|mode <mode>` inside Vibe. Each
command finds the session, then hands Writ's own prompt hook the phrase the user would
have typed in Claude, or runs Writ's mode command. Stub tests use a throwaway plugin root;
the real-hook tests run Writ's scripts against a temp cache with the daemon port closed.
"""

from __future__ import annotations

import contextlib
import json
import os
import socket
import subprocess
import sys
from pathlib import Path

import pytest

from tests.test_harness_vibe import Plugin
from writ.harness import vibe_context, vibe_user

REPO = Path(__file__).resolve().parent.parent
LAUNCHER = REPO / "bin" / "mistty"
sys.path.insert(0, str(REPO / "bin" / "lib"))
import approval_match  # noqa: E402
import manual_test_grant  # noqa: E402

HEADER = "[mistty: Vibe session sid-1]"


@pytest.fixture(autouse=True)
def _vibe_home(tmp_path, monkeypatch):
    """Keeps every state refresh off the developer's own Vibe sessions."""
    monkeypatch.setenv("VIBE_HOME", str(tmp_path / "vibe-home"))


def _stub(say: str = "", code: int = 0) -> str:
    return (f"printf '%s\\n' {json.dumps(say)}\n" if say else "") + f"exit {code}\n"


def _plugin(tmp_path: Path, *, approve: str | None = None, grant: str | None = None,
            timeout: int | None = None) -> Plugin:
    """The three UserPromptSubmit scripts hooks.json lists, as stubs."""
    scripts = {
        "writ-manual-test-grant": grant if grant is not None else _stub("GRANT LIVE"),
        "auto-approve-gate": approve if approve is not None else _stub("GATE SAYS HI"),
        "writ-rag-inject": _stub("RAG BLOCK"),
    }
    entry: dict = {"matcher": "", "scripts": scripts}
    if timeout is not None:
        entry["timeout"] = timeout
    plugin = Plugin(tmp_path, {"UserPromptSubmit": [entry]})
    lib = plugin.root / "bin" / "lib"
    lib.mkdir(parents=True)
    # Records its argv; rejects any mode but work, as Writ's own helper rejects bad modes.
    (lib / "writ-session.py").write_text(
        "import json, os, sys\n"
        "with open(os.path.join(os.environ['VIBE_TEST_LOG'], 'mode.argv.json'), 'w') as f:\n"
        "    json.dump(sys.argv[1:], f)\n"
        "if sys.argv[3] != 'work':\n"
        "    print('Invalid mode: ' + sys.argv[3], file=sys.stderr)\n"
        "    sys.exit(1)\n"
        "print('set: work')\n"
    )
    return plugin


def _run(plugin: Plugin, capsys, *argv: str, sid: str | None = "sid-1") -> tuple[int, str]:
    rc = vibe_user.main(list(argv), plugin_root=str(plugin.root), base_env=plugin.env(),
                        session_resolver=lambda: sid)
    return rc, capsys.readouterr().out


# --------------------------------------------------------------------------- #
# What each command hands Writ
# --------------------------------------------------------------------------- #
def test_approve_sends_the_override_phrase_to_the_approval_hook_only(tmp_path, capsys, monkeypatch):
    plugin = _plugin(tmp_path)
    project = tmp_path / "project"
    project.mkdir()
    monkeypatch.chdir(project)
    rc, _ = _run(plugin, capsys, "approve")
    assert rc == 0
    [seen] = plugin.runs("auto-approve-gate")
    assert seen == {
        "session_id": "sid-1",
        "prompt": "approved anyway",
        "transcript_path": "",
        "cwd": os.getcwd(),
        "hook_event_name": "UserPromptSubmit",
    }
    assert plugin.runs("writ-manual-test-grant") == []
    assert plugin.runs("writ-rag-inject") == []


def test_replan_sends_the_replan_phrase_to_the_approval_hook(tmp_path, capsys):
    plugin = _plugin(tmp_path)
    rc, _ = _run(plugin, capsys, "replan")
    assert rc == 0
    [seen] = plugin.runs("auto-approve-gate")
    assert seen["prompt"] == "replan approved"
    assert plugin.runs("writ-manual-test-grant") == []


def test_grant_sends_the_grant_phrase_to_the_grant_hook_only(tmp_path, capsys):
    plugin = _plugin(tmp_path)
    rc, _ = _run(plugin, capsys, "grant", "manual-test")
    assert rc == 0
    [seen] = plugin.runs("writ-manual-test-grant")
    assert seen["prompt"] == "manual test approved"
    assert seen["session_id"] == "sid-1"
    assert plugin.runs("auto-approve-gate") == []
    assert plugin.runs("writ-rag-inject") == []


def test_the_phrases_come_from_the_modules_that_match_them(tmp_path, capsys):
    plugin = _plugin(tmp_path)
    for argv in (["approve"], ["replan"], ["grant", "manual-test"]):
        assert _run(plugin, capsys, *argv)[0] == 0
    approve, replan = (r["prompt"] for r in plugin.runs("auto-approve-gate"))
    [grant] = (r["prompt"] for r in plugin.runs("writ-manual-test-grant"))
    assert approve == approval_match.OVERRIDE_PHRASE
    assert approval_match.classify(approve) == "override"
    assert replan == approval_match.REPLAN_PHRASE
    assert approval_match.classify(replan) == "replan"
    assert grant in manual_test_grant.GRANT_PHRASES
    assert manual_test_grant.is_grant_phrase(grant)


def test_output_names_the_session_then_relays_the_hook(tmp_path, capsys):
    plugin = _plugin(tmp_path)
    rc, out = _run(plugin, capsys, "approve")
    assert rc == 0
    assert out.splitlines()[0] == HEADER
    assert "GATE SAYS HI" in out


# --------------------------------------------------------------------------- #
# Refusals and failures
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("argv", [["approve"], ["replan"], ["grant", "manual-test"], ["mode", "work"]])
def test_no_live_session_refuses_and_runs_nothing(tmp_path, capsys, argv):
    plugin = _plugin(tmp_path)
    rc, out = _run(plugin, capsys, *argv, sid=None)
    assert rc == 1
    assert "!mistty" in out
    assert plugin.runs("auto-approve-gate") == []
    assert plugin.runs("writ-manual-test-grant") == []
    assert not (plugin.log / "mode.argv.json").exists()


def test_hook_exiting_non_zero_fails_with_the_reason(tmp_path, capsys):
    plugin = _plugin(tmp_path, approve=_stub("half done", code=3))
    rc, out = _run(plugin, capsys, "approve")
    assert rc == 1
    assert "auto-approve-gate" in out
    assert "3" in out


def test_hook_timing_out_fails_with_the_reason(tmp_path, capsys):
    plugin = _plugin(tmp_path, approve="sleep 5\n", timeout=1)
    rc, out = _run(plugin, capsys, "approve")
    assert rc == 1
    assert "timed out" in out


def test_hook_missing_from_hooks_json_fails(tmp_path, capsys):
    plugin = Plugin(tmp_path, {"UserPromptSubmit": [
        {"matcher": "", "scripts": {"writ-rag-inject": _stub("RAG BLOCK")}}]})
    rc, out = _run(plugin, capsys, "approve")
    assert rc == 1
    assert "auto-approve-gate" in out
    assert plugin.runs("writ-rag-inject") == []


def test_grant_with_no_directive_fails(tmp_path, capsys):
    plugin = _plugin(tmp_path, grant=_stub())
    rc, out = _run(plugin, capsys, "grant", "manual-test")
    assert rc == 1
    assert "grant" in out.lower()


# --------------------------------------------------------------------------- #
# Mode
# --------------------------------------------------------------------------- #
def test_mode_runs_writ_mode_set_and_relays_its_output(tmp_path, capsys):
    plugin = _plugin(tmp_path)
    rc, out = _run(plugin, capsys, "mode", "work")
    assert rc == 0
    assert json.loads((plugin.log / "mode.argv.json").read_text()) == ["mode", "set", "work", "sid-1"]
    assert out.splitlines()[0] == HEADER
    assert "set: work" in out


def test_invalid_mode_passes_writs_refusal_through(tmp_path, capsys):
    plugin = _plugin(tmp_path)
    rc, out = _run(plugin, capsys, "mode", "bogus")
    assert rc != 0
    assert "Invalid mode: bogus" in out


# --------------------------------------------------------------------------- #
# Writ's state file in the scratchpad
# --------------------------------------------------------------------------- #
@pytest.fixture
def refreshes(monkeypatch):
    """Records every state refresh instead of running it."""
    calls: list[tuple[str, dict]] = []

    def fake(sid, **kwargs):
        calls.append((sid, kwargs))
        return True
    monkeypatch.setattr(vibe_context, "refresh", fake)
    return calls


@pytest.mark.parametrize("argv, ran", [
    (["approve"], "auto-approve-gate"),
    (["replan"], "auto-approve-gate"),
    (["grant", "manual-test"], "writ-manual-test-grant"),
    (["mode", "work"], "mode"),
])
def test_each_command_refreshes_the_state_file_after_it_runs(tmp_path, capsys, monkeypatch,
                                                             argv, ran):
    plugin = _plugin(tmp_path)
    seen = []

    def fake(sid, **kwargs):
        done = ((plugin.log / "mode.argv.json").exists() if ran == "mode"
                else bool(plugin.runs(ran)))
        seen.append((sid, kwargs["plugin_root"], kwargs["base_env"], done))
        return True
    monkeypatch.setattr(vibe_context, "refresh", fake)
    _run(plugin, capsys, *argv)
    assert seen == [("sid-1", str(plugin.root), plugin.env(), True)]


def test_a_failed_command_still_refreshes(tmp_path, capsys, refreshes):
    plugin = _plugin(tmp_path)
    rc, _ = _run(plugin, capsys, "mode", "bogus")
    assert rc != 0
    assert [sid for sid, _ in refreshes] == ["sid-1"]


def test_no_live_session_refreshes_nothing(tmp_path, capsys, refreshes):
    plugin = _plugin(tmp_path)
    _run(plugin, capsys, "approve", sid=None)
    assert refreshes == []


# --------------------------------------------------------------------------- #
# Real Writ hooks against a temp cache
# --------------------------------------------------------------------------- #
def _closed_port() -> int:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]
    finally:
        s.close()


@pytest.fixture
def real(tmp_path, monkeypatch):
    """Writ's real scripts with the cache in tmp_path, HOME pinned, and the daemon port
    closed, so nothing reaches the developer's live daemon or session state."""
    cache, home, project = tmp_path / "cache", tmp_path / "home", tmp_path / "project"
    for d in (cache, home / ".claude", project):
        d.mkdir(parents=True)
    monkeypatch.chdir(project)
    env = {**os.environ, "WRIT_CACHE_DIR": str(cache), "WRIT_HOST": "127.0.0.1",
           "WRIT_PORT": str(_closed_port()), "HOME": str(home)}
    return {"cache": cache, "env": env}


def _real(real: dict, capsys, sid: str, *argv: str) -> tuple[int, str]:
    rc = vibe_user.main(list(argv), base_env=real["env"], session_resolver=lambda: sid)
    return rc, capsys.readouterr().out


@contextlib.contextmanager
def _token_cleanup(sid: str):
    from writ.session.gate_token import gate_token_path

    try:
        yield gate_token_path(sid)
    finally:
        with contextlib.suppress(OSError):
            os.remove(gate_token_path(sid))


def test_real_approve_on_pending_phase_a_mints_a_phase_a_token(real, capsys):
    sid = "mistty-approve-real-1"
    (real["cache"] / f"writ-session-{sid}.json").write_text(
        json.dumps({"mode": "work", "current_phase": "planning", "gates_approved": []}))
    with _token_cleanup(sid) as token:
        rc, out = _real(real, capsys, sid, "approve")
        assert rc == 0, out
        assert os.path.exists(token), out
        with open(token) as f:
            assert f.read().split("\n")[1] == "phase-a"


def test_real_grant_writes_a_live_grant(real, capsys):
    sid = "mistty-grant-real-1"
    rc, out = _real(real, capsys, sid, "grant", "manual-test")
    assert rc == 0, out
    assert "manual-testing grant is live" in out
    assert (real["cache"] / f"writ-grant-{sid}.json").exists()


def test_real_mode_work_leaves_the_session_in_planning(real, capsys):
    sid = "mistty-mode-real-1"
    rc, out = _real(real, capsys, sid, "mode", "work")
    assert rc == 0, out
    state = json.loads((real["cache"] / f"writ-session-{sid}.json").read_text())
    assert state["mode"] == "work"
    assert state["current_phase"] == "planning"


# --------------------------------------------------------------------------- #
# Launcher dispatch
# --------------------------------------------------------------------------- #
def _launcher_env(tmp_path: Path) -> tuple[Path, dict]:
    """A symlinked launcher, as ~/.local/bin/mistty is, and a fake Rust client to exec."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    link = bin_dir / "mistty"
    link.symlink_to(LAUNCHER)
    fake = bin_dir / "vibe-rs"
    fake.write_text('#!/bin/sh\necho FAKE-VIBE\nprintf \'%s\\n\' "$@"\n')
    fake.chmod(0o755)
    env = {**os.environ, "PATH": f"{bin_dir}:{os.environ['PATH']}", "HOME": str(tmp_path),
           "MISTTY_RUST_BIN": str(fake)}
    env.pop("MISTTY_HOME", None)
    return link, env


def test_launcher_sends_approve_to_the_user_commands(tmp_path):
    link, env = _launcher_env(tmp_path)
    proc = subprocess.run([str(link), "approve"], cwd=tmp_path, env=env,
                          capture_output=True, text=True, timeout=30)
    # No mistty session owns this process, so the command refuses; a fake vibe would
    # have printed FAKE-VIBE and exited 0.
    assert proc.returncode == 1, proc.stdout + proc.stderr
    assert "FAKE-VIBE" not in proc.stdout
    assert "!mistty" in proc.stdout


@pytest.mark.parametrize("arg", ["approver", "approve this"])
def test_launcher_sends_anything_else_to_vibe(tmp_path, arg):
    link, env = _launcher_env(tmp_path)
    proc = subprocess.run([str(link), arg], cwd=tmp_path, env=env,
                          capture_output=True, text=True, timeout=30)
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.splitlines() == ["FAKE-VIBE", arg]
