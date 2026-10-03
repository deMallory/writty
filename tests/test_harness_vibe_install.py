"""The mistty installer and launcher: a separate Vibe home that carries Writ's hooks.

Every install runs against tmp_path homes with --no-check, except the loader tests, which
use a fake interpreter or, when Vibe is installed, Vibe's own hook loader.
"""

from __future__ import annotations

import json
import os
import re
import shlex
import socket
import stat
import subprocess
import tomllib
from pathlib import Path

import pytest

from writ.harness import vibe, vibe_install
from writ.retrieval.prompt_bundle import render_always_on

REPO = Path(__file__).resolve().parent.parent
HOOK = REPO / "bin" / "writ-vibe-hook"
LAUNCHER = REPO / "bin" / "mistty"
BOOTSTRAP = REPO / "scripts" / "bootstrap-vibe.sh"

RULES = ("=== ALWAYS-ACTIVE RULES ===\n[TEST-RULE-001] WHEN: always\n"
         "  Say what you tested.\n=== END ALWAYS-ACTIVE RULES ===")
# The real fetch, kept before the autouse stub below replaces it.
_FETCH = vibe_install.fetch_rules


class _Rules:
    text: str | None = RULES


@pytest.fixture(autouse=True)
def rules(monkeypatch) -> _Rules:
    """No test reaches the live daemon: fetch_rules answers from here. Set .text to None
    for a daemon that is down."""
    stub = _Rules()
    monkeypatch.setattr(vibe_install, "fetch_rules", lambda: stub.text)
    return stub


@pytest.fixture
def dirs(tmp_path: Path) -> dict[str, Path]:
    source = tmp_path / "vibe"
    source.mkdir()
    (source / ".env").write_text("MISTRAL_API_KEY=test\n")
    (source / "config.toml").write_text('active_model = "test"\n')
    return {"home": tmp_path / "mistty", "source": source, "bin": tmp_path / "bin"}


def _flags(dirs: dict[str, Path], *, check: bool = False) -> list[str]:
    flags = ["--home", str(dirs["home"]), "--source-home", str(dirs["source"]),
             "--bin-dir", str(dirs["bin"])]
    return flags if check else [*flags, "--no-check"]


def _install(dirs, capsys, *extra: str, check: bool = False) -> tuple[int, str]:
    rc = vibe_install.main([*_flags(dirs, check=check), *extra])
    return rc, capsys.readouterr().out


def _hooks(home: Path) -> dict[str, dict]:
    data = tomllib.loads((home / "hooks.toml").read_text())
    return {h["name"]: h for h in data["hooks"]}


def _snapshot(*roots: Path) -> dict[str, str]:
    """Every path under the roots, with a symlink's target or a file's bytes."""
    seen: dict[str, str] = {}
    for root in roots:
        if not root.exists() and not root.is_symlink():
            continue
        for p in [root, *root.rglob("*")]:
            if p.is_symlink():
                seen[str(p)] = "-> " + os.readlink(p)
            elif p.is_file():
                seen[str(p)] = p.read_text()
            else:
                seen[str(p)] = "dir"
    return seen


# --------------------------------------------------------------------------- #
# Home and shared files
# --------------------------------------------------------------------------- #
def test_fresh_install_creates_home_owner_only(dirs, capsys):
    rc, _ = _install(dirs, capsys)
    assert rc == 0
    assert stat.S_IMODE(dirs["home"].stat().st_mode) == 0o700


def test_env_and_config_link_to_the_source_home(dirs, capsys):
    rc, out = _install(dirs, capsys)
    assert rc == 0
    for name in (".env", "config.toml"):
        target = dirs["home"] / name
        assert target.is_symlink(), name
        assert target.resolve() == (dirs["source"] / name).resolve()
        assert f"link {name}" in out


def test_missing_source_file_is_skipped_and_reported(dirs, capsys):
    (dirs["source"] / ".env").unlink()
    rc, out = _install(dirs, capsys)
    assert rc == 0
    assert not (dirs["home"] / ".env").exists()
    assert not (dirs["home"] / ".env").is_symlink()
    assert "skip .env" in out


def test_existing_target_is_left_alone_and_reported(dirs, capsys):
    dirs["home"].mkdir(mode=0o700)
    (dirs["home"] / "config.toml").write_text("mine = true\n")
    rc, out = _install(dirs, capsys)
    assert rc == 0
    target = dirs["home"] / "config.toml"
    assert not target.is_symlink()
    assert target.read_text() == "mine = true\n"
    assert "keep config.toml" in out


# --------------------------------------------------------------------------- #
# hooks.toml and the matcher
# --------------------------------------------------------------------------- #
def test_hooks_file_holds_exactly_the_three_writ_entries(dirs, capsys):
    rc, _ = _install(dirs, capsys)
    assert rc == 0
    hooks = _hooks(dirs["home"])
    assert set(hooks) == {"writ-pre", "writ-post", "writ-stop"}

    pre, post = hooks["writ-pre"], hooks["writ-post"]
    assert pre["type"] == "pre_tool"
    assert pre["strict"] is True
    assert pre["command"] == f"{shlex.quote(str(HOOK))} pre_tool"
    assert post["type"] == "post_tool"
    assert post.get("strict", False) is False
    assert post["command"] == f"{shlex.quote(str(HOOK))} post_tool"
    assert pre["match"] == post["match"] == vibe_install.matcher()


def test_the_stop_entry_runs_the_bridge_at_every_turn_end(dirs, capsys):
    assert _install(dirs, capsys)[0] == 0
    stop = _hooks(dirs["home"])["writ-stop"]
    assert stop["type"] == "post_agent"
    assert stop["command"] == f"{shlex.quote(str(HOOK))} post_agent"
    # Vibe's loader refuses both on post_agent.
    assert "match" not in stop
    assert "strict" not in stop
    # Vibe accepts the turn when its own timeout fires, so it must outlast the bridge's.
    assert stop["timeout"] > vibe.STOP_SCRIPT_TIMEOUT_S


def test_matcher_covers_every_bridge_tool_in_any_case():
    pattern = vibe_install.matcher()
    assert pattern.startswith("re:")
    rx = re.compile(pattern.removeprefix("re:"), re.IGNORECASE)
    for name in [*vibe._TOOLS, *vibe._BRIDGE_TOOLS]:
        assert rx.fullmatch(name), name
        assert rx.fullmatch(name.upper()), name


@pytest.mark.parametrize("name", ["process.write", "PROCESS.WRITE", "Process.Write"])
def test_matcher_covers_process_write_which_the_bridge_decides_itself(name):
    rx = re.compile(vibe_install.matcher().removeprefix("re:"), re.IGNORECASE)
    assert rx.fullmatch(name)


@pytest.mark.parametrize("name", [
    "vibe.unified_harness_scratchpad", "VIBE.UNIFIED_HARNESS_SCRATCHPAD",
])
def test_matcher_covers_the_scratchpad_tool_which_holds_writs_state_file(name):
    rx = re.compile(vibe_install.matcher().removeprefix("re:"), re.IGNORECASE)
    assert rx.fullmatch(name)


@pytest.mark.parametrize("name", [
    "subagent.spawn", "subagent.send_message", "SUBAGENT.SPAWN",
])
def test_matcher_covers_the_subagent_calls_that_hand_a_child_work(name):
    rx = re.compile(vibe_install.matcher().removeprefix("re:"), re.IGNORECASE)
    assert rx.fullmatch(name)


@pytest.mark.parametrize("name", [
    "subagent.list", "subagent.wait", "subagent.interrupt", "subagent.stop",
    "subagent.spawn_extra", "task", "skill.read", "file_system.read_file_extra", "xbash",
])
def test_matcher_rejects_tools_the_bridge_does_not_map(name):
    rx = re.compile(vibe_install.matcher().removeprefix("re:"), re.IGNORECASE)
    assert rx.fullmatch(name) is None


# --------------------------------------------------------------------------- #
# AGENTS.md
# --------------------------------------------------------------------------- #
def _agents(home: Path) -> str:
    return (home / "AGENTS.md").read_text()


def test_install_writes_agents_md_with_the_commands_and_the_rules(dirs, capsys):
    rc, out = _install(dirs, capsys)
    assert rc == 0
    text = _agents(dirs["home"])
    assert text.splitlines()[0] == vibe_install.AGENTS_MARKER
    for needle in ("!mistty approve", "!mistty replan", "!mistty grant manual-test",
                   "!mistty mode", "0-writ.md",
                   "tool_skipped: Tool execution was skipped by Runtime policy.",
                   "process.write", RULES):
        assert needle in text, needle
    assert f"write {dirs['home'] / 'AGENTS.md'}" in out


def test_agents_md_says_a_failing_end_of_turn_check_sends_the_turn_back(dirs, capsys):
    assert _install(dirs, capsys)[0] == 0
    text = _agents(dirs["home"])
    section = text[text.index("## End of turn"):]
    for needle in ("unresolved rule violations", "failing tests", "below 3",
                   "sends your turn back", "at most 3 times"):
        assert needle in section, needle


def test_agents_md_says_where_subagents_are_refused(dirs, capsys):
    assert _install(dirs, capsys)[0] == 0
    text = _agents(dirs["home"])
    section = text[text.index("## Subagents"):]
    section = section[:section.index("\n## ", 1)]
    for needle in ("`subagent.spawn`", "`subagent.send_message`", "work mode", "debug mode",
                   "no mode set", "do not retry"):
        assert needle in section, needle


def test_a_rerun_picks_up_changed_rules(dirs, capsys, rules):
    assert _install(dirs, capsys)[0] == 0
    rules.text = RULES.replace("TEST-RULE-001", "TEST-RULE-002")
    assert _install(dirs, capsys)[0] == 0
    text = _agents(dirs["home"])
    assert "TEST-RULE-002" in text
    assert "TEST-RULE-001" not in text


def test_daemon_down_keeps_an_owned_agents_md(dirs, capsys, rules):
    assert _install(dirs, capsys)[0] == 0
    before = _agents(dirs["home"])
    rules.text = None
    rc, out = _install(dirs, capsys)
    assert rc == 0
    assert _agents(dirs["home"]) == before
    assert "rules not refreshed" in out


def test_daemon_down_on_a_first_install_writes_agents_md_without_rules(dirs, capsys, rules):
    rules.text = None
    rc, out = _install(dirs, capsys)
    assert rc == 0
    text = _agents(dirs["home"])
    assert text.splitlines()[0] == vibe_install.AGENTS_MARKER
    assert "!mistty approve" in text
    assert "ALWAYS-ACTIVE" not in text
    [line] = [li for li in out.splitlines() if "AGENTS.md" in li]
    assert "rules" in line
    assert "skipped" in line


@pytest.mark.parametrize("content", ["my own notes\n", ""])
def test_foreign_agents_md_stops_the_install_before_any_write(dirs, capsys, content):
    dirs["home"].mkdir(mode=0o700)
    (dirs["home"] / "AGENTS.md").write_text(content)
    before = _snapshot(dirs["home"], dirs["bin"])
    rc, out = _install(dirs, capsys)
    assert rc == 1
    assert "AGENTS.md" in out
    assert _snapshot(dirs["home"], dirs["bin"]) == before


class _Daemon:
    def __init__(self, status: int, body: str):
        self.status, self.body = status, body
        self.calls: list[tuple[str, float]] = []

    def __call__(self, path, socket_path=None, base_url=None, timeout=0.5):
        self.calls.append((path, timeout))
        return self.status, self.body


_ALWAYS_ON = {"rules": [{"rule_id": "TEST-RULE-001", "trigger": "always",
                         "statement": "Say what you tested."}], "total_tokens": 10}


def test_fetch_rules_renders_the_daemons_always_on_bundle(monkeypatch):
    daemon = _Daemon(200, json.dumps(_ALWAYS_ON))
    monkeypatch.setattr(vibe_install.writ_daemon_client, "get_json", daemon)
    assert _FETCH() == render_always_on(_ALWAYS_ON)[0]
    assert daemon.calls == [("/always-on", 5.0)]


@pytest.mark.parametrize("status, body", [
    (0, ""), (500, "boom"), (200, "not json"), (200, "[]"), (200, json.dumps({"rules": []})),
])
def test_fetch_rules_is_none_when_the_daemon_gives_no_rules(monkeypatch, status, body):
    monkeypatch.setattr(vibe_install.writ_daemon_client, "get_json", _Daemon(status, body))
    assert _FETCH() is None


# --------------------------------------------------------------------------- #
# Idempotence and conflicts
# --------------------------------------------------------------------------- #
def test_second_install_changes_nothing(dirs, capsys):
    assert _install(dirs, capsys)[0] == 0
    before = _snapshot(dirs["home"], dirs["bin"])
    assert _install(dirs, capsys)[0] == 0
    assert _snapshot(dirs["home"], dirs["bin"]) == before


@pytest.mark.parametrize("hooks_toml", [
    '[[hooks]]\nname = "other"\ntype = "pre_tool"\ncommand = "true"\n',
    "this is = = not toml\n",
])
def test_foreign_hooks_file_stops_the_install_before_any_write(dirs, capsys, hooks_toml):
    dirs["home"].mkdir(mode=0o700)
    (dirs["home"] / "hooks.toml").write_text(hooks_toml)
    before = _snapshot(dirs["home"], dirs["bin"])
    rc, out = _install(dirs, capsys)
    assert rc == 1
    assert "hooks.toml" in out
    assert _snapshot(dirs["home"], dirs["bin"]) == before


@pytest.mark.parametrize("kind", ["file", "symlink"])
def test_foreign_launcher_stops_the_install_before_any_write(dirs, capsys, tmp_path, kind):
    dirs["bin"].mkdir()
    foreign = dirs["bin"] / "mistty"
    if kind == "file":
        foreign.write_text("#!/bin/sh\necho old\n")
    else:
        foreign.symlink_to(tmp_path / "elsewhere")
    before = _snapshot(dirs["home"], dirs["bin"])
    rc, out = _install(dirs, capsys)
    assert rc == 1
    assert "mistty" in out
    assert not dirs["home"].exists()
    assert _snapshot(dirs["home"], dirs["bin"]) == before


# --------------------------------------------------------------------------- #
# Launcher
# --------------------------------------------------------------------------- #
def test_launcher_is_linked_onto_the_bin_dir(dirs, capsys):
    rc, _ = _install(dirs, capsys)
    assert rc == 0
    link = dirs["bin"] / "mistty"
    assert link.is_symlink()
    assert Path(os.readlink(link)) == LAUNCHER


def _fake_vibe(tmp_path: Path) -> Path:
    fake_bin = tmp_path / "fakebin"
    fake_bin.mkdir()
    fake = fake_bin / "vibe"
    fake.write_text('#!/bin/sh\nprintf \'%s\\n\' "$VIBE_HOME" "$@"\n')
    fake.chmod(0o755)
    return fake_bin


@pytest.mark.parametrize("mistty_home", [None, "/opt/elsewhere"])
def test_launcher_runs_vibe_in_the_mistty_home_with_args_unchanged(tmp_path, mistty_home):
    env = {"PATH": f"{_fake_vibe(tmp_path)}:/usr/bin:/bin", "HOME": str(tmp_path)}
    if mistty_home:
        env["MISTTY_HOME"] = mistty_home
    proc = subprocess.run([str(LAUNCHER), "-p", "hello world", ""],
                          capture_output=True, text=True, env=env, timeout=10)
    assert proc.returncode == 0, proc.stderr
    expected_home = mistty_home or str(tmp_path / ".mistty")
    assert proc.stdout.split("\n")[:4] == [expected_home, "-p", "hello world", ""]


# --------------------------------------------------------------------------- #
# Vibe's own loader
# --------------------------------------------------------------------------- #
_LOAD = (
    "import json, sys\n"
    "from pathlib import Path\n"
    "from vibe.core.hooks.config import load_hooks_file\n"
    "r = load_hooks_file(Path(sys.argv[1]), strict=True)\n"
    "print(json.dumps({'issues': [i.message for i in r.issues],"
    " 'names': [h.name for h in r.hooks]}))\n"
)


def test_generated_file_passes_vibes_own_loader(dirs, capsys):
    python = vibe_install.vibe_python()
    if not python:
        pytest.skip("Mistral Vibe is not installed")
    assert _install(dirs, capsys)[0] == 0
    proc = subprocess.run([python, "-c", _LOAD, str(dirs["home"] / "hooks.toml")],
                          capture_output=True, text=True, timeout=60)
    assert proc.returncode == 0, proc.stderr
    result = json.loads(proc.stdout)
    assert result["issues"] == []
    assert sorted(result["names"]) == ["writ-post", "writ-pre", "writ-stop"]


def test_installer_check_reports_zero_issues_with_real_vibe(dirs, capsys):
    if not vibe_install.vibe_python():
        pytest.skip("Mistral Vibe is not installed")
    rc, out = _install(dirs, capsys, check=True)
    assert rc == 0
    assert "0 issues" in out


def test_loader_issue_fails_the_install(dirs, capsys, tmp_path):
    fake = tmp_path / "fake-python"
    fake.write_text('#!/bin/sh\necho \'{"issues": ["writ-pre - bad field"], "names": []}\'\n')
    fake.chmod(0o755)
    rc, out = _install(dirs, capsys, "--vibe-python", str(fake), check=True)
    assert rc == 1
    assert "writ-pre - bad field" in out


def test_check_is_skipped_when_vibe_is_not_on_path(dirs, capsys, tmp_path, monkeypatch):
    empty = tmp_path / "empty-bin"
    empty.mkdir()
    monkeypatch.setenv("PATH", str(empty))
    rc, out = _install(dirs, capsys, check=True)
    assert rc == 0
    assert "skipped" in out


# --------------------------------------------------------------------------- #
# Bootstrap script
# --------------------------------------------------------------------------- #
def _no_daemon(tmp_path: Path) -> dict:
    """The bootstrap runs in a subprocess, out of the stub's reach, so the daemon client
    gets a socket and a port that nothing listens on."""
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    finally:
        s.close()
    return {**os.environ, "WRIT_SOCKET": str(tmp_path / "no-daemon.sock"),
            "WRIT_SESSION_BASE": f"http://127.0.0.1:{port}"}


def test_bootstrap_runs_from_any_cwd_and_forwards_flags(dirs, tmp_path):
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    proc = subprocess.run(["bash", str(BOOTSTRAP), *_flags(dirs)], env=_no_daemon(tmp_path),
                          cwd=elsewhere, capture_output=True, text=True, timeout=60)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert set(_hooks(dirs["home"])) == {"writ-pre", "writ-post", "writ-stop"}
    assert _agents(dirs["home"]).splitlines()[0] == vibe_install.AGENTS_MARKER


def test_bootstrap_forwards_the_installer_exit_code(dirs, tmp_path):
    dirs["bin"].mkdir()
    (dirs["bin"] / "mistty").write_text("#!/bin/sh\n")
    proc = subprocess.run(["bash", str(BOOTSTRAP), *_flags(dirs)], env=_no_daemon(tmp_path),
                          cwd=tmp_path, capture_output=True, text=True, timeout=60)
    assert proc.returncode == 1
