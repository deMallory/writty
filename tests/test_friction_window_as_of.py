"""FIX-1: the analyzer retention window is measured from an injectable `as_of`.

The Phase-5 analyzers windowed events against the real wall clock
(`datetime.now()`), so tests anchored to a fixed fixture date silently aged out
of the window once the clock crossed a boundary (the 2026-06-01 time-bomb).
Injecting `as_of` makes the window hermetic: production keeps the real-clock
default; tests measure relative to a fixed reference and never time-bomb.

These tests are deliberately clock-INDEPENDENT -- they assert behavior relative
to a fixed `as_of`, never relative to `datetime.now()` -- so they cannot
themselves rot. One fallback test confirms the omit-`as_of` default still tracks
the real clock.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from writ.analysis.friction import (
    FrictionEvent,
    _within_window,
    analyze_rule_effectiveness,
)

# A fixed reference with no relation to the wall clock -- the whole point.
ASOF = datetime(2026, 5, 1, 12, 0, 0, tzinfo=timezone.utc)


def _ev(event: str, ts: datetime, **fields) -> FrictionEvent:
    return FrictionEvent(
        ts=ts.isoformat().replace("+00:00", "Z"),
        session=fields.pop("session", "s"),
        event=event,
        mode=fields.pop("mode", "work"),
        **fields,
    )


class TestWithinWindowAsOf:
    """_within_window honors as_of and falls back to datetime.now() when omitted."""

    def test_event_at_as_of_is_kept(self) -> None:
        events = [_ev("rag_query", ASOF, rule_id="R")]
        kept = _within_window(events, since_days=30, as_of=ASOF)
        assert len(kept) == 1

    def test_event_just_outside_window_is_dropped(self) -> None:
        old = _ev("rag_query", ASOF - timedelta(days=31), rule_id="R")
        kept = _within_window([old], since_days=30, as_of=ASOF)
        assert kept == []

    def test_event_just_inside_window_is_kept(self) -> None:
        recent = _ev("rag_query", ASOF - timedelta(days=29), rule_id="R")
        kept = _within_window([recent], since_days=30, as_of=ASOF)
        assert len(kept) == 1

    def test_omitting_as_of_falls_back_to_real_now(self) -> None:
        """Production default unchanged: an event stamped 'now' is retained."""
        now_ev = _ev("rag_query", datetime.now(timezone.utc), rule_id="R")
        kept = _within_window([now_ev], since_days=30)
        assert len(kept) == 1

    def test_since_days_zero_disables_window_regardless_of_as_of(self) -> None:
        old = _ev("rag_query", ASOF - timedelta(days=9999), rule_id="R")
        assert len(_within_window([old], since_days=0, as_of=ASOF)) == 1


class TestAnalyzerAsOfThreading:
    """A representative analyzer threads as_of into its window -- clock-independent."""

    def test_rule_effectiveness_respects_as_of(self) -> None:
        events = [
            _ev("rag_query", ASOF, rule_id="ENF-NEW"),
            _ev("gate_denial", ASOF + timedelta(seconds=5), rule_id="ENF-NEW"),
            _ev("rag_query", ASOF - timedelta(days=31), rule_id="ENF-OLD"),
        ]
        rows = analyze_rule_effectiveness(events, since_days=30, as_of=ASOF)
        ids = {r.rule_id for r in rows}
        assert "ENF-NEW" in ids
        assert "ENF-OLD" not in ids
