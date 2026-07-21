"""Shared friction-event base record (DUP-KEYSTONE-PY consolidation).

Both Python friction writers (writ.analysis.friction.log_friction_event for the
server, writ.session.friction._log_friction_event for the session helper) build
the same base entry {ts, session, mode, event} with the same UTC ts format. Only
their path resolution and extra-field handling differ (by design), so just the
base record is shared here. stdlib only; lowest layer so both packages import it.
"""

from datetime import datetime, timezone


def base_friction_entry(session_id: str, mode: str | None, event: str) -> dict:
    """The common {ts, session, mode, event} prefix of a friction log line.

    Single source of the friction entry schema + UTC timestamp format; callers
    add their own extra fields (with their own None-handling) and write it out.
    """
    return {
        "ts": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "session": session_id,
        "mode": mode,
        "event": event,
    }
