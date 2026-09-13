#!/usr/bin/env python3
"""Parse Claude Code hook stdin envelope into normalized fields.

Claude Code dispatches hooks with a JSON envelope on stdin containing
structured tool metadata. This parser normalizes the envelope and falls
back to the CLAUDE_TOOL_INPUT environment variable when the envelope is
missing or incomplete.

Stdin: the full JSON envelope from Claude Code's hook dispatch.
Stdout: normalized JSON with top-level fields for easy consumption.

Envelope format (from Claude Code internals):
{
    "hook_event_name": "PreToolUse",
    "tool_name": "Write",
    "tool_input": {"file_path": "...", "content": "..."},
    "tool_input_json": "{...}",
    "tool_output": null,
    "tool_result_is_error": false
}

Stdlib only -- no external dependencies. Grok camelCase is accepted via
writ.harness.envelope.normalize; the emitted key set is unchanged so the
jq arm can stay byte-equivalent on Claude envelopes.
"""

import json
import os
import shlex
import sys

_SKILL_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _SKILL_ROOT not in sys.path:
    sys.path.insert(0, _SKILL_ROOT)

from writ.harness.envelope import _as_object, normalize  # noqa: E402

_EMIT_KEYS = (
    "session_id",
    "agent_id",
    "agent_type",
    "event",
    "tool_name",
    "tool_input",
    "tool_output",
    "is_error",
    "file_path",
    "content",
    "old_string",
    "new_string",
    "command",
)


def parse() -> None:
    raw = sys.stdin.read()

    try:
        envelope = _as_object(json.loads(raw))
    except (json.JSONDecodeError, ValueError):
        envelope = {}

    normalized = normalize(envelope)
    result = {key: normalized[key] for key in _EMIT_KEYS}

    if "--shell" in sys.argv:
        _emit_shell(result)
    else:
        json.dump(result, sys.stdout)


def _emit_shell(result: dict) -> None:
    """Emit shlex-quoted shell assignments for the scalar fields + HOOK_ENVELOPE.

    One `eval` of this output sets all HOOK_* vars in a single python3 spawn, so
    hooks read fields as bash variables instead of re-spawning python per field.
    shlex.quote guarantees envelope values cannot be shell-executed by the eval.
    """
    def _q(v: object) -> str:
        # Non-strings collapse to "" here and in parse-hook-stdin.jq's q(), which is the
        # ONLY way the two arms agree without reimplementing python's repr in jq: they
        # disagreed on booleans (True vs true), containers ([1, 2] vs [1,2]) and floats
        # (1.0 vs 1). Every field below is a string in CC's schema, so a non-string is
        # malformed input and "" is already how hooks spell absent. HOOK_ENVELOPE below
        # still carries the raw JSON, so nothing is actually lost.
        return shlex.quote(v if isinstance(v, str) else "")

    # Mirror detect_session_id's preference: agent_id (sub-agent isolation) else session_id.
    session_id = result["agent_id"] or result["session_id"]
    is_error = "1" if result["is_error"] else "0"
    lines = [
        f"HOOK_SESSION_ID={_q(session_id)}",
        f"HOOK_SESSION_ID_RAW={_q(result['session_id'])}",
        f"HOOK_AGENT_ID={_q(result['agent_id'])}",
        f"HOOK_AGENT_TYPE={_q(result['agent_type'])}",
        f"HOOK_EVENT={_q(result['event'])}",
        f"HOOK_TOOL_NAME={_q(result['tool_name'])}",
        f"HOOK_FILE_PATH={_q(result['file_path'])}",
        f"HOOK_COMMAND={_q(result['command'])}",
        f"HOOK_IS_ERROR={_q(is_error)}",
        f"HOOK_ENVELOPE={_q(json.dumps(result))}",
    ]
    sys.stdout.write("\n".join(lines) + "\n")


if __name__ == "__main__":
    parse()
