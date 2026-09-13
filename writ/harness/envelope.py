"""Normalize Claude Code and Grok Build hook envelopes to one snake_case dict.

Hooks keep reading today's field names. This module is stdlib-only so
`bin/lib/parse-hook-stdin.py` can import it after putting the skill root on
sys.path. Missing keys fall through; an explicitly present null is a value
(python `.get` / jq `getor` semantics), except for the file_path / content
chains which already use python-truthiness fall-through.
"""

from __future__ import annotations

import json
import os
from typing import Any


def _present(obj: dict, *keys: str, default: Any = "") -> Any:
    """First *present* key wins, even when its value is null."""
    for key in keys:
        if key in obj:
            return obj[key]
    return default


def _as_object(value: object) -> dict:
    return value if isinstance(value, dict) else {}


def _parse_tool_input(envelope: dict) -> dict:
    tool_input = _present(envelope, "tool_input", "toolInput", default={})
    if isinstance(tool_input, str):
        try:
            tool_input = json.loads(tool_input)
        except (json.JSONDecodeError, ValueError):
            tool_input = {}
    tool_input = _as_object(tool_input)
    if tool_input:
        return tool_input
    env_input = os.environ.get("CLAUDE_TOOL_INPUT", "")
    if not env_input:
        return {}
    try:
        return _as_object(json.loads(env_input))
    except (json.JSONDecodeError, ValueError):
        return {}


def _truthy_chain(*values: Any) -> Any:
    for value in values:
        if value:
            return value
    return ""


def normalize(envelope: dict | None) -> dict:
    """Return the snake_case result `parse-hook-stdin.py` already emits."""
    env = _as_object(envelope)
    tool_input = _parse_tool_input(env)

    session_id = _present(env, "session_id", "sessionId", default="")

    agent_id = _present(env, "agent_id", "agentId", default="")
    agent_type = _present(env, "agent_type", "agentType", default="")
    event = _present(
        env,
        "hook_event_name",
        "hookEventName",
        default=os.environ.get("HOOK_EVENT", ""),
    )
    tool_name = _present(
        env, "tool_name", "toolName", default=os.environ.get("HOOK_TOOL_NAME", "")
    )
    tool_output = _present(
        env,
        "tool_output",
        "toolOutput",
        "toolResult",
        "tool_result",
        default=os.environ.get("HOOK_TOOL_OUTPUT"),
    )
    is_error = _present(
        env,
        "tool_result_is_error",
        "toolResultIsError",
        default=os.environ.get("HOOK_TOOL_IS_ERROR") == "1",
    )

    return {
        "session_id": session_id,
        "agent_id": agent_id,
        "agent_type": agent_type,
        "event": event,
        "tool_name": tool_name,
        "tool_input": tool_input,
        "tool_output": tool_output,
        "is_error": is_error,
        "file_path": _truthy_chain(
            tool_input.get("file_path"),
            tool_input.get("path"),
            tool_input.get("notebook_path"),
            tool_input.get("target_file"),
            "",
        ),
        "content": tool_input.get("content") or tool_input.get("new_source", ""),
        "old_string": tool_input.get("old_string", ""),
        "new_string": tool_input.get("new_string", ""),
        "command": tool_input.get("command", ""),
        "prompt": _truthy_chain(
            env.get("prompt"), env.get("message"), env.get("content"), ""
        ),
        "stop_hook_active": bool(
            _present(env, "stop_hook_active", "stopHookActive", default=False)
        ),
        "last_assistant_message": _present(
            env, "last_assistant_message", "lastAssistantMessage", default=""
        )
        or "",
        "reason": _present(env, "reason", default=""),
    }
