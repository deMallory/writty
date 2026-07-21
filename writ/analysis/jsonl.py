"""Shared JSONL reader for writ/analysis (friction, token_audit, efficacy_ab).

A dependency-free leaf module (stdlib only) so the analysis modules share one
skip-malformed reader without an import cycle.
"""

import json
from collections.abc import Iterator
from pathlib import Path


def read_jsonl(path: str | Path, *, errors: str | None = None) -> Iterator[dict]:
    """Yield each JSON object from a JSONL file, skipping blank and malformed lines.

    Only the per-line json parse is tolerated: lines raising ValueError/JSONDecodeError are
    skipped. Open-time OSError (missing file, a directory, permission denied) PROPAGATES --
    the reader does not decide the missing/unreadable policy, so each caller keeps its own
    (friction guards with path.exists(); token_audit._read_friction wraps in try/except OSError;
    the required-transcript readers let it raise to fail loud). `errors` passes to open()
    (None = the strict default; "ignore" for CC transcripts that may hold undecodable bytes).
    """
    with open(path, errors=errors) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except (ValueError, json.JSONDecodeError):
                continue
