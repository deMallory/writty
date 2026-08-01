#!/usr/bin/env python3
"""PostToolUse(Bash) result rewriter for the updatedToolOutput surface.

Reads the hook envelope on stdin. When tool_response.stdout/stderr contain
secret-shaped strings or stdout exceeds size limits, emits a
hookSpecificOutput.updatedToolOutput reply (2.1.183 force-swap family) that
replaces the result the model sees. The original text never reaches the
model and the swap costs zero prompt tokens. Emits nothing when the
response is already clean and small.

Stdlib only -- no external dependencies.
"""

import json
import re
import sys

MAX_CHARS = 30000
MAX_LINES = 400
HEAD_LINES = 200
TAIL_LINES = 100

REDACTED = "[REDACTED:writ-output-rewrite]"

# Conservative, low-false-positive secret shapes. The keyed pattern (last)
# keeps the key name and separator, redacting only the value.
SECRET_PATTERNS = [
    re.compile(
        r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----",
        re.S,
    ),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(r"\bghp_[A-Za-z0-9]{36}\b"),
    re.compile(r"\bgithub_pat_[A-Za-z0-9_]{22,}\b"),
    re.compile(r"\bsk-ant-[A-Za-z0-9-]{20,}\b"),
    re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}\b"),
    re.compile(r"\beyJ[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{10,}\b"),
    re.compile(
        r"(?i)\b(api[_-]?key|secret|token|password|passwd)"
        r"([\"']?\s*[=:]\s*[\"']?)[A-Za-z0-9_+/.\-]{12,}"
    ),
]


def scrub(text: str) -> tuple[str, bool]:
    changed = False
    for pat in SECRET_PATTERNS:
        if pat.groups:
            new = pat.sub(lambda m: m.group(1) + m.group(2) + REDACTED, text)
        else:
            new = pat.sub(REDACTED, text)
        if new != text:
            changed = True
            text = new
    return text, changed


def truncate(text: str) -> tuple[str, bool]:
    lines = text.split("\n")
    if len(text) <= MAX_CHARS and len(lines) <= MAX_LINES:
        return text, False
    elided = len(lines) - HEAD_LINES - TAIL_LINES
    if elided <= 0:
        return (
            text[:MAX_CHARS]
            + f"\n[writ-output-rewrite: {len(text) - MAX_CHARS} characters elided]",
            True,
        )
    marker = f"[writ-output-rewrite: {elided} of {len(lines)} lines elided]"
    return "\n".join(lines[:HEAD_LINES] + [marker] + lines[-TAIL_LINES:]), True


def main() -> None:
    try:
        envelope = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        return
    resp = envelope.get("tool_response")
    if not isinstance(resp, dict) or resp.get("isImage"):
        return
    changed = False
    for key in ("stdout", "stderr"):
        val = resp.get(key)
        if not isinstance(val, str) or not val:
            continue
        val, scrubbed = scrub(val)
        truncated = False
        if key == "stdout":
            val, truncated = truncate(val)
        if scrubbed or truncated:
            resp[key] = val
            changed = True
    if not changed:
        return
    json.dump(
        {
            "hookSpecificOutput": {
                "hookEventName": "PostToolUse",
                "updatedToolOutput": resp,
            }
        },
        sys.stdout,
    )


if __name__ == "__main__":
    main()
