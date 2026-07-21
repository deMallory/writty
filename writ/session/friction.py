"""Friction-event logging for the session helper.

POL-6c extracted the friction logger out of bin/lib/writ-session.py. It now delegates
to the P1 logging router (writ.shared.logging.emit), which classifies each event into a
typed stream (audit / friction / metrics), honors WRIT_FRICTION_LOG back-compat, and
degrades to a durable fallback on write failure. The public signature stays
(session_id, mode, event, **extra) so every existing caller is unchanged. stdlib only;
fail-soft (the router never raises).
"""

from writ.shared.logging import emit


def _log_friction_event(session_id: str, mode: str | None, event: str, **extra: object) -> None:
    """Append one classified event via the P1 logging router.

    Stream is None so the router classifies `event` through STREAM_MAP (unknown
    events default to friction). WRIT_FRICTION_LOG, if set, still collapses every
    stream to a single file (test-isolation + single-log back-compat).
    """
    emit(None, event, session_id, mode, **extra)
