"""Vibe bridge against the REAL hooks/hooks.json scripts and an isolated daemon.

The unit tests in test_harness_vibe.py pin the translation with stub scripts. This module
proves the translated envelopes are ones Writ's own gates understand: a Vibe write in the
planning phase meets the same ENF-GATE-PLAN deny a Claude Write meets.
"""

from __future__ import annotations

import contextlib
import json
import os
import subprocess
import uuid
from pathlib import Path

from tests._hook_runner import hook_env, isolated_daemon, seed_session_cache  # noqa: F401
from writ.harness import vibe

REPO = Path(__file__).resolve().parent.parent


def _run(daemon: dict, sid: str, event: str, envelope: dict) -> str:
    return vibe.handle(
        event, json.dumps(envelope),
        plugin_root=str(REPO),
        base_env=hook_env(daemon),
        session_resolver=lambda _env: sid,
        context_dir=str(Path(envelope["cwd"]) / ".vibe-ctx"),
    )


def _planning_session(daemon: dict) -> str:
    sid = f"vibe-{uuid.uuid4().hex[:8]}"
    seed_session_cache(daemon["health"]["cache_dir"], sid, "work", current_phase="planning")
    return sid


def test_unified_write_in_planning_phase_is_denied(tmp_path, isolated_daemon):  # noqa: F811
    (tmp_path / "src").mkdir()
    sid = _planning_session(isolated_daemon)
    out = _run(isolated_daemon, sid, "pre_tool", {
        "cwd": str(tmp_path), "hook_event_name": "pre_tool",
        "tool_name": "file_system.write_file", "tool_call_id": "w1",
        "tool_input": {"path": "src/app.py", "content": "x = 1\n"},
    })
    data = json.loads(out)
    assert data["decision"] == "deny", data
    assert "ENF-GATE-PLAN" in data["reason"], data
    assert not (tmp_path / "src" / "app.py").exists()


def test_unified_read_in_planning_phase_is_allowed(tmp_path, isolated_daemon):  # noqa: F811
    (tmp_path / "notes.txt").write_text("hello\n")
    sid = _planning_session(isolated_daemon)
    out = _run(isolated_daemon, sid, "pre_tool", {
        "cwd": str(tmp_path), "hook_event_name": "pre_tool",
        "tool_name": "file_system.read_file", "tool_call_id": "r1",
        "tool_input": {"path": "notes.txt"},
    })
    if out:
        assert json.loads(out)["decision"] != "deny", out


def _session(daemon: dict, mode: str, **cache: object) -> str:
    sid = f"vibe-{uuid.uuid4().hex[:8]}"
    path = Path(seed_session_cache(daemon["health"]["cache_dir"], sid, mode,
                                   current_phase="planning" if mode == "work" else None))
    path.write_text(json.dumps({**json.loads(path.read_text()), **cache}))
    return sid


def _turn_end(cwd: Path) -> dict:
    return {"cwd": str(cwd), "hook_event_name": "post_agent"}


def test_unified_turn_with_pending_violations_is_sent_back(tmp_path, isolated_daemon):  # noqa: F811
    sid = _session(isolated_daemon, "work", pending_violations=[
        {"rule_id": "TEST-VIOL-001"}, {"rule_id": "TEST-VIOL-002"}])
    out = _run(isolated_daemon, sid, "post_agent", _turn_end(tmp_path))
    data = json.loads(out)
    assert data["decision"] == "deny", data
    assert data["reason"].startswith(vibe._STOP_HEADER), data
    assert "TEST-VIOL-001, TEST-VIOL-002" in data["reason"], data


def test_unified_turn_in_conversation_mode_ends(tmp_path, isolated_daemon):  # noqa: F811
    sid = _session(isolated_daemon, "conversation")
    assert _run(isolated_daemon, sid, "post_agent", _turn_end(tmp_path)) == ""


def _prompt(cwd: Path, sid: str, prompt: str, last_assistant_message: str | None) -> dict:
    return {"cwd": str(cwd), "hook_event_name": "user_prompt", "session_id": sid,
            "prompt": prompt, "last_assistant_message": last_assistant_message}


def _context(out: str) -> str:
    return json.loads(out)["hook_specific_output"]["additional_context"]


def test_a_requested_chat_approval_advances_phase_a_in_that_prompt(tmp_path, isolated_daemon):  # noqa: F811
    from writ.session.gate_token import gate_token_path

    (tmp_path / ".git").mkdir()
    (tmp_path / "plan.md").write_text(
        "# Plan\n\n## Files\n\n- `src/app.py` (create) -- the entry point\n\n"
        "## Analysis\n\nOne new file.\n\n## Rules Applied\n\nNo matching rules.\n\n"
        "## Capabilities\n\n- [ ] the app starts\n")
    sid = _planning_session(isolated_daemon)
    try:
        out = _run(isolated_daemon, sid, "user_prompt", _prompt(
            tmp_path, sid, "approved", "Plan written to plan.md.\n\nSay approved to proceed."))
    finally:
        with contextlib.suppress(OSError):
            os.remove(gate_token_path(sid))
    assert "[Writ: planning gate approved -> " in _context(out), out
    cache = Path(isolated_daemon["health"]["cache_dir"]) / f"writ-session-{sid}.json"
    assert "phase-a" in json.loads(cache.read_text())["gates_approved"]


def test_the_first_prompt_carries_writs_rules(tmp_path, isolated_daemon):  # noqa: F811
    sid = _planning_session(isolated_daemon)
    out = _run(isolated_daemon, sid, "user_prompt", _prompt(
        tmp_path, sid, "add a dry-run flag to the export command", None))
    context = _context(out)
    assert "--- WRIT RULES (" in context, out
    assert context.rstrip().endswith("--- END WRIT RULES ---"), out


def test_an_auto_routed_work_prompt_keeps_writs_rules(tmp_path, isolated_daemon):  # noqa: F811
    (tmp_path / ".git").mkdir()
    sid = f"vibe-{uuid.uuid4().hex[:8]}"
    out = _run(isolated_daemon, sid, "user_prompt", _prompt(
        tmp_path, sid, "implement the export endpoint from the approved plan", None))
    context = _context(out)
    assert "do each step yourself" in context, out
    assert "--- WRIT RULES (" in context, out
    cache = Path(isolated_daemon["health"]["cache_dir"]) / f"writ-session-{sid}.json"
    assert json.loads(cache.read_text())["is_orchestrator"] is False


def test_the_model_sets_the_mode_writs_context_asks_for(tmp_path, isolated_daemon):  # noqa: F811
    sid = f"vibe-{uuid.uuid4().hex[:8]}"
    command = f"writ mode set work {sid}"
    out = _run(isolated_daemon, sid, "pre_tool", {
        "cwd": str(tmp_path), "hook_event_name": "pre_tool",
        "tool_name": "bash", "tool_call_id": "m1", "tool_input": {"command": command},
    })
    assert not out or json.loads(out)["decision"] != "deny", out
    # bin/mistty puts this bin/ first on the session's PATH.
    env = {**hook_env(isolated_daemon),
           "PATH": f"{REPO / 'bin'}:{os.environ['PATH']}"}
    proc = subprocess.run(command, shell=True, cwd=tmp_path, env=env,
                          capture_output=True, text=True, timeout=60, check=False)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    cache = Path(isolated_daemon["health"]["cache_dir"]) / f"writ-session-{sid}.json"
    assert json.loads(cache.read_text())["mode"] == "work"
