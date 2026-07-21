#!/usr/bin/env python3
"""Single friction-log writer, delegating to the P1 logging router.

Every hook and session module routes writes through this so classification,
path resolution, WRIT_FRICTION_LOG back-compat, and the durable fallback all
live in one place (writ.shared.logging). Each entry is classified into a typed
stream (audit / friction / metrics) by its `event` via STREAM_MAP, unless
`--stream STREAM` forces the destination. When the primary write fails the
router preserves the event in `<root>/_fallback.jsonl` (off /tmp) so security
audit trails like memory_policy_deny are never silently dropped.

Modes:
  friction-append.py [--stream S] SESSION MODE EVENT [EXTRA_JSON]  # builds entry
  friction-append.py [--stream S] --stdin-json                     # one entry dict
  friction-append.py [--stream S] --stdin-jsonl                    # one entry per line
"""
from __future__ import annotations

import json
import os
import sys

# Ensure the skill root is importable so `import writ.shared.logging` resolves
# whether this file is run as a script by absolute path (hooks) or spawned in
# tests. The skill root is three levels above this file (bin/lib/friction-append.py).
_SKILL_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _SKILL_ROOT not in sys.path:
    sys.path.insert(0, _SKILL_ROOT)

from writ.shared.logging import emit  # noqa: E402


def _emit_entry(entry: dict, stream: str | None) -> None:
    """Route one full entry dict through the router.

    Pulls session/mode/event out of the entry and forwards the remaining keys as
    fields; the router rebuilds the base schema (fresh ts) and classifies by event
    when `stream` is None. `ts` is dropped here because the router owns it.
    """
    session = entry.get("session", "")
    mode = entry.get("mode")
    event = entry.get("event", "")
    fields = {k: v for k, v in entry.items() if k not in ("session", "mode", "event", "ts")}
    emit(stream, event, session, mode, **fields)


def _pop_stream_flag(argv: list[str]) -> tuple[str | None, list[str]]:
    """Extract `--stream STREAM` from argv, returning (stream_or_None, rest)."""
    if "--stream" not in argv:
        return None, argv
    idx = argv.index("--stream")
    stream = argv[idx + 1] if idx + 1 < len(argv) else None
    rest = argv[:idx] + argv[idx + 2:]
    return stream, rest


def main(argv: list[str]) -> int:
    stream, argv = _pop_stream_flag(argv)

    if "--stdin-jsonl" in argv:
        # Batch: one JSON object per line. Each entry is classified by its own
        # event so a single spawn can emit mixed-stream events.
        for line in sys.stdin:
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
            except (ValueError, json.JSONDecodeError):
                continue
            if isinstance(entry, dict):
                _emit_entry(entry, stream)
        return 0

    if "--stdin-json" in argv:
        try:
            entry = json.load(sys.stdin)
        except (ValueError, json.JSONDecodeError):
            return 0
        if isinstance(entry, dict):
            _emit_entry(entry, stream)
        return 0

    session = argv[1] if len(argv) > 1 else ""
    mode = argv[2] if len(argv) > 2 else ""
    event = argv[3] if len(argv) > 3 else ""
    extra: dict = {}
    if len(argv) > 4 and argv[4]:
        try:
            parsed = json.loads(argv[4])
            if isinstance(parsed, dict):
                extra = parsed
        except (ValueError, json.JSONDecodeError):
            extra = {}
    emit(stream, event, session, mode or None, **extra)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
