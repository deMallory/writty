#!/usr/bin/env python3
"""Snapshot workflow-friction.log and emit the delta.

Used during manual pressure runs (docs/pressure-runs/README.md):

    python scripts/friction-log-delta.py snapshot       # before run
    # ... do the work ...
    python scripts/friction-log-delta.py since-snapshot # after run → paste to Claude
    python scripts/friction-log-delta.py reset          # clear marker

State is a single .friction-snapshot file holding the byte offset at
snapshot time. Subcommands are idempotent and safe on missing files.
"""
from __future__ import annotations

import argparse
import hashlib
import sys
from pathlib import Path

LOG = Path("workflow-friction.log")
MARKER = Path(".friction-snapshot")


def _log_size() -> int:
    return LOG.stat().st_size if LOG.exists() else 0


def _content_fingerprint(size: int) -> str:
    """SHA1 of the current log's content up to `size` bytes. Empty string if
    log missing or size=0. Used to detect rotation: if content changes, we
    can't trust the stored offset."""
    if size == 0 or not LOG.exists():
        return ""
    h = hashlib.sha1()
    with LOG.open("rb") as f:
        remaining = size
        while remaining > 0:
            chunk = f.read(min(65536, remaining))
            if not chunk:
                break
            h.update(chunk)
            remaining -= len(chunk)
    return h.hexdigest()


def cmd_snapshot() -> int:
    size = _log_size()
    MARKER.write_text(f"{size}:{_content_fingerprint(size)}")
    return 0


def cmd_since_snapshot() -> int:
    if not MARKER.exists():
        print("error: no snapshot to diff from (run `snapshot` first)", file=sys.stderr)
        return 1
    raw = MARKER.read_text().strip()
    # Back-compat: old marker format was just the offset integer.
    if ":" in raw:
        offset_str, expected_fp = raw.split(":", 1)
    else:
        offset_str, expected_fp = raw, ""
    try:
        offset = int(offset_str)
    except ValueError:
        print("error: corrupt snapshot marker", file=sys.stderr)
        return 1
    if not LOG.exists():
        return 0
    size = _log_size()
    # Detect rotation: shrink, OR content at pre-snapshot region changed.
    rotated = size < offset
    if not rotated and expected_fp:
        current_fp = _content_fingerprint(min(offset, size))
        if current_fp != expected_fp:
            rotated = True
    start = 0 if rotated else offset
    with LOG.open("rb") as f:
        f.seek(start)
        data = f.read()
    sys.stdout.write(data.decode("utf-8", errors="replace"))
    return 0


def cmd_reset() -> int:
    if MARKER.exists():
        MARKER.unlink()
    return 0


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        prog="friction-log-delta",
        description="Snapshot workflow-friction.log and emit the delta. "
                    "Subcommands: snapshot, since-snapshot, reset.",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("snapshot", help="Record current log size as baseline.")
    sub.add_parser("since-snapshot", help="Emit bytes appended since snapshot.")
    sub.add_parser("reset", help="Remove the snapshot marker.")
    args = parser.parse_args(argv)
    if args.cmd == "snapshot":
        return cmd_snapshot()
    if args.cmd == "since-snapshot":
        return cmd_since_snapshot()
    if args.cmd == "reset":
        return cmd_reset()
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
