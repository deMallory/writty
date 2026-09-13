"""Grok and Claude hook envelopes normalize to the same snake_case result."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

from writ.harness.envelope import normalize

REPO = Path(__file__).resolve().parent.parent
PY_PARSER = REPO / "bin" / "lib" / "parse-hook-stdin.py"

CLAUDE_WRITE = {
    "session_id": "s-claude",
    "hook_event_name": "PreToolUse",
    "tool_name": "Write",
    "tool_input": {"file_path": "/tmp/a.py", "content": "x = 1\n"},
}

GROK_WRITE = {
    "sessionId": "s-grok",
    "hookEventName": "pre_tool_use",
    "toolName": "write",
    "toolInput": {"file_path": "/tmp/a.py", "content": "x = 1\n"},
}


def test_claude_envelope_keeps_snake_case_fields():
    result = normalize(CLAUDE_WRITE)
    assert result["session_id"] == "s-claude"
    assert result["event"] == "PreToolUse"
    assert result["tool_name"] == "Write"
    assert result["file_path"] == "/tmp/a.py"
    assert result["content"] == "x = 1\n"


def test_grok_envelope_maps_camel_case_to_same_fields():
    result = normalize(GROK_WRITE)
    assert result["session_id"] == "s-grok"
    assert result["event"] == "pre_tool_use"
    assert result["tool_name"] == "write"
    assert result["file_path"] == "/tmp/a.py"


def test_snake_case_wins_when_both_spellings_present():
    result = normalize({**GROK_WRITE, "session_id": "s-snake", "sessionId": "s-camel"})
    assert result["session_id"] == "s-snake"


def test_target_file_is_accepted_as_file_path():
    result = normalize(
        {"session_id": "s", "tool_input": {"target_file": "/tmp/t.py"}}
    )
    assert result["file_path"] == "/tmp/t.py"


def test_empty_payload_does_not_read_session_env(monkeypatch):
    monkeypatch.setenv("GROK_SESSION_ID", "sid-from-grok-env")
    monkeypatch.setenv("CLAUDE_SESSION_ID", "sid-from-claude-env")
    result = normalize({"toolName": "write"})
    assert result["session_id"] == ""


def test_stop_hook_active_accepts_camel_case():
    assert normalize({"stopHookActive": True})["stop_hook_active"] is True
    assert normalize({"stop_hook_active": True})["stop_hook_active"] is True
    assert normalize({})["stop_hook_active"] is False


def test_last_assistant_message_accepts_camel_case():
    result = normalize({"lastAssistantMessage": "hello"})
    assert result["last_assistant_message"] == "hello"


def test_parser_shell_output_agrees_on_grok_write():
    proc = subprocess.run(
        ["python3", str(PY_PARSER), "--shell"],
        input=json.dumps(GROK_WRITE),
        capture_output=True,
        text=True,
        timeout=30,
        cwd=str(REPO),
        env={**os.environ, "PYTHONPATH": str(REPO)},
    )
    assert proc.returncode == 0, proc.stderr
    assert "HOOK_SESSION_ID=s-grok" in proc.stdout
    assert "HOOK_TOOL_NAME=write" in proc.stdout
    assert "HOOK_FILE_PATH=/tmp/a.py" in proc.stdout
