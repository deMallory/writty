"""Vibe bridge against the REAL hooks/hooks.json scripts and an isolated daemon.

The unit tests in test_harness_vibe.py pin the translation with stub scripts. This module
proves the translated envelopes are ones Writ's own gates understand: a Vibe write in the
planning phase meets the same ENF-GATE-PLAN deny a Claude Write meets.
"""

from __future__ import annotations

import json
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
