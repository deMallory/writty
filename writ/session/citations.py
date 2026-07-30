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


def _append_citation(cache: dict, row: dict, session_id: str = "") -> None:
    """INV-2: append a typed artifact citation to the bounded citation_log.

    Stamps `ts`, truncates `excerpt` to the cap, and trims the log to the cap.
    Shared by --add-citation (file/url/...) and --add-command-run (command).

    Also mirrors the row to the durable `audit` stream (audit item F). The cache copy is
    bounded by _CITATION_LOG_MAX, so the OLDEST citations are dropped from it as soon as
    the cap is reached, and the whole log dies with the cache: the evidence behind a claim
    was the most perishable thing Writ recorded. The stream copy makes the trim a working-
    set decision instead of data loss.

    `session_id` is optional because the two `cmd_update` handlers that cite reach this
    through a dispatch table that passes only (cache, args, index); a row without it is
    still durable, it just cannot be grouped by run. Callers that have it should pass it.
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

    # Imported here, not at module scope: this module is loaded on hook spawns where the
    # citation path is never taken, and shared.logging pulls in enough to be worth the
    # ~ms (the same reason `import traceback` was moved inside emit_exception).
    from writ.shared.logging import emit

    emit("audit", "citation_recorded", session_id, None, **entry)
