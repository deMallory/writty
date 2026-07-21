"""Typed artifact citations for the session helper (INV-2).

POL-6g-1 extracts `_append_citation` out of bin/lib/writ-session.py. It is the lowest
new layer in the 6g cluster: budget_tracking's `cmd_update` (--add-citation /
--add-command-run) and investigations' `cmd_record_analysis` both append through it.
Depends only on config (the citation bounds) and the stdlib -- never on the facade --
so the dependency graph stays acyclic.
"""

import hashlib
from datetime import datetime, timezone

from writ.session.config import _CITATION_LOG_MAX, _CITATION_EXCERPT_MAX


def _append_citation(cache: dict, row: dict) -> None:
    """INV-2: append a typed artifact citation to the bounded citation_log.

    Stamps `ts`, truncates `excerpt` to the cap, and trims the log to the cap.
    Shared by --add-citation (file/url/...) and --add-command-run (command).
    """
    entry = dict(row)
    entry.setdefault("artifact_type", "")
    entry["excerpt"] = str(entry.get("excerpt", ""))[:_CITATION_EXCERPT_MAX]
    # INV-7a: stamp a deterministic content hash so a re-captured source whose excerpt
    # changed is detectable (staleness drift) without comparing against a clock.
    entry["excerpt_hash"] = hashlib.sha256(entry["excerpt"].encode("utf-8")).hexdigest()[:16]
    entry["ts"] = datetime.now(timezone.utc).isoformat()
    log = cache.get("citation_log", [])
    log.append(entry)
    cache["citation_log"] = log[-_CITATION_LOG_MAX:]
