"""RED tests: writ.analysis.friction.aggregate_session / render_audit_json /
render_audit_text (Wave 2 Cycle 2, branch refactor/w2-cli-split).

plan.md moves the pure audit-session aggregation + rendering logic out of
writ/cli.py's private `_aggregate_session` / `_render_audit_json` /
`_render_audit_text` (cli.py:190-418) into public functions of the same
shape at `writ/analysis/friction.py`:

    aggregate_session(session_events: list[dict]) -> dict
    render_audit_json(session_id: str, session_events: list[dict], agg: dict) -> str
    render_audit_text(session_id: str, session_events: list[dict], agg: dict) -> str

The move is VERBATIM (behavior-preserving relocation, no logic changes), so
this file is a parity guard: the expected dict/JSON/text values below were
captured by IMPORTING AND RUNNING the CURRENT writ.cli private functions
(which exist today, pre-extraction) on the synthetic `session_events` in
this file, then hardcoding the exact output. Repro (already run once while
authoring this file, .venv/bin/python):

    from writ.cli import _aggregate_session, _render_audit_json, _render_audit_text
    agg = _aggregate_session(_synthetic_session_events())
    _render_audit_json("SID-1", _synthetic_session_events(), agg)
    _render_audit_text("SID-1", _synthetic_session_events(), agg)

RED now: `writ.analysis.friction` does not yet define `aggregate_session`,
`render_audit_json`, or `render_audit_text` (they only exist as the private
`_aggregate_session` / `_render_audit_*` names inside writ/cli.py), so every
import below raises ImportError. Each test performs its own local import (as
tests/test_cli_pr_sync.py does for `_write_commit_notes`) so pytest reports a
distinct, per-test ImportError instead of one whole-module collection error.
GREEN once the implementer moves the three functions (plus the private
`_agg_*` handlers and `_SESSION_EVENT_HANDLERS` dispatch dict, kept private)
to writ/analysis/friction.py and extends its `__all__`.

Synthetic input exercises multiple `_agg_*` handlers in one session:
  - phase_advance      -> _agg_phase_advance
  - rag_query          -> _agg_rag_query (classify_delivery path; SKL-/PBK- ids)
  - always_on_inject   -> _agg_always_on_inject (classify_delivery path)
  - gate_denial        -> _agg_gate_denial
  - unrecognized_event -> no handler; folds into event_counts only

Run: .venv/bin/python -m pytest tests/test_friction_audit_session.py -v
"""

from __future__ import annotations

import pytest


def _synthetic_session_events() -> list[dict]:
    """One session's worth of friction events covering several _agg_* handlers.

    Deliberately minimal (TEST-FIXTURE-002): one event per handler under test,
    plus one unrecognized event type to exercise the event_counts-only path.
    """
    return [
        {"ts": "2026-07-01T10:00:00Z", "session": "SID-1", "mode": "work",
         "event": "phase_advance", "from_phase": "planning", "to_phase": "testing",
         "confirmation_source": "tool"},
        {"ts": "2026-07-01T10:00:01Z", "session": "SID-1", "mode": "work",
         "event": "rag_query", "query_source": "broad", "tokens_injected": 200,
         "rule_ids": ["SKL-PROC-PLAN-001", "PBK-PROC-PLAN-001", "ARCH-TYPE-001"]},
        {"ts": "2026-07-01T10:00:02Z", "session": "SID-1", "mode": "work",
         "event": "always_on_inject", "tokens": 150},
        {"ts": "2026-07-01T10:00:03Z", "session": "SID-1", "mode": "work",
         "event": "gate_denial", "rule_id": "ENF-PROC-TDD-001"},
        {"ts": "2026-07-01T10:00:04Z", "session": "SID-1", "mode": "work",
         "event": "unrecognized_event", "foo": "bar"},
    ]


# --- Captured expected values (parity fixtures) -----------------------------
# Produced by running the CURRENT writ.cli._aggregate_session /
# _render_audit_json / _render_audit_text on _synthetic_session_events().
# Do NOT re-derive these from writ.cli inside the test itself -- a parity
# test that regenerates its own "expected" from the same moving source can
# never catch a divergence introduced by the move.

EXPECTED_AGG = {
    "event_counts": {
        "phase_advance": 1,
        "rag_query": 1,
        "always_on_inject": 1,
        "gate_denial": 1,
        "unrecognized_event": 1,
    },
    "phase_transitions": [
        {"ts": "2026-07-01T10:00:00Z", "from": "planning", "to": "testing", "source": "tool"},
    ],
    "rule_loads": {
        "SKL-PROC-PLAN-001": 1,
        "PBK-PROC-PLAN-001": 1,
        "ARCH-TYPE-001": 1,
    },
    "skill_loads": {"SKL-PROC-PLAN-001": 1},
    "playbook_loads": {"PBK-PROC-PLAN-001": 1},
    "gate_denials": [
        {"ts": "2026-07-01T10:00:03Z", "rule_id": "ENF-PROC-TDD-001"},
    ],
    "subagents": [],
    "tokens_by_source": {"broad": 200},
    "tokens_by_delivery": {"unknown": 350},
    "always_on_injects": 1,
    "always_on_tokens": 150,
    "playbook_completions": [],
    "mode_changes": [],
    "push_by_action": {},
    "push_channel_counts": {},
}

EXPECTED_EMPTY_AGG = {
    "event_counts": {},
    "phase_transitions": [],
    "rule_loads": {},
    "skill_loads": {},
    "playbook_loads": {},
    "gate_denials": [],
    "subagents": [],
    "tokens_by_source": {},
    "tokens_by_delivery": {},
    "always_on_injects": 0,
    "always_on_tokens": 0,
    "playbook_completions": [],
    "mode_changes": [],
    "push_by_action": {},
    "push_channel_counts": {},
}

EXPECTED_JSON = '{\n  "session": "SID-1",\n  "event_count": 5,\n  "first_ts": "2026-07-01T10:00:00Z",\n  "last_ts": "2026-07-01T10:00:04Z",\n  "event_counts": {\n    "phase_advance": 1,\n    "rag_query": 1,\n    "always_on_inject": 1,\n    "gate_denial": 1,\n    "unrecognized_event": 1\n  },\n  "phase_transitions": [\n    {\n      "ts": "2026-07-01T10:00:00Z",\n      "from": "planning",\n      "to": "testing",\n      "source": "tool"\n    }\n  ],\n  "mode_changes": [],\n  "rule_loads": {\n    "SKL-PROC-PLAN-001": 1,\n    "PBK-PROC-PLAN-001": 1,\n    "ARCH-TYPE-001": 1\n  },\n  "skill_loads": {\n    "SKL-PROC-PLAN-001": 1\n  },\n  "playbook_loads": {\n    "PBK-PROC-PLAN-001": 1\n  },\n  "gate_denials": [\n    {\n      "ts": "2026-07-01T10:00:03Z",\n      "rule_id": "ENF-PROC-TDD-001"\n    }\n  ],\n  "subagents": [],\n  "playbook_completions": [],\n  "always_on_injects": 1,\n  "always_on_tokens": 150,\n  "tokens_by_source": {\n    "broad": 200\n  },\n  "tokens_by_delivery": {\n    "unknown": 350\n  },\n  "push_by_action": {},\n  "push_channels": {}\n}'

EXPECTED_TEXT = '=== Session audit: SID-1 ===\nEvents: 5 (first=2026-07-01T10:00:00Z, last=2026-07-01T10:00:04Z)\n\nPhase progression:\n  2026-07-01T10:00:00Z  planning -> testing  (tool)\n\nTokens injected by source:\n  always_on           150  (1 injects)\n  broad               200\n\nTokens by delivery (#7):\n  -> unknown         350\n\nSkill loads:\n  SKL-PROC-PLAN-001                1\n\nPlaybook loads:\n  PBK-PROC-PLAN-001                1\n\nGate denials: 1\n  2026-07-01T10:00:03Z  denied: ENF-PROC-TDD-001\n\nTop event types:\n  phase_advance                1\n  rag_query                    1\n  always_on_inject             1\n  gate_denial                  1\n  unrecognized_event           1'


class TestAggregateSessionParity:
    """aggregate_session must match _aggregate_session exactly (dict/list in,
    dict of Counters/lists out; Counter compares equal to a plain dict)."""

    def test_aggregate_session_matches_current(self) -> None:
        # RED: ImportError -- writ.analysis.friction has no aggregate_session yet.
        from writ.analysis.friction import aggregate_session

        agg = aggregate_session(_synthetic_session_events())

        assert agg == EXPECTED_AGG, (
            f"aggregate_session output diverges from the captured writ.cli."
            f"_aggregate_session parity fixture.\ngot={agg!r}\nexpected={EXPECTED_AGG!r}"
        )

    def test_aggregate_session_empty_events(self) -> None:
        # Edge case: empty session_events -> the zeroed/empty aggregate skeleton,
        # matching writ.cli._aggregate_session([]) exactly.
        # RED: ImportError -- writ.analysis.friction has no aggregate_session yet.
        from writ.analysis.friction import aggregate_session

        agg = aggregate_session([])

        assert agg == EXPECTED_EMPTY_AGG, (
            f"aggregate_session([]) diverges from the captured empty-input "
            f"parity fixture.\ngot={agg!r}\nexpected={EXPECTED_EMPTY_AGG!r}"
        )


class TestRenderAuditJsonParity:
    def test_render_audit_json_matches_current(self) -> None:
        # RED: ImportError -- writ.analysis.friction has no render_audit_json
        # (or aggregate_session) yet.
        from writ.analysis.friction import aggregate_session, render_audit_json

        events = _synthetic_session_events()
        agg = aggregate_session(events)
        out = render_audit_json("SID-1", events, agg)

        assert out == EXPECTED_JSON, (
            f"render_audit_json output is not byte-identical to the captured "
            f"writ.cli._render_audit_json parity fixture.\ngot={out!r}"
        )

    def test_render_audit_json_empty_events_raises_index_error(self) -> None:
        # Parity edge case: the CURRENT _render_audit_json unconditionally
        # dereferences session_events[0] (for first_ts), so an empty list
        # raises IndexError today. The verbatim extraction must preserve
        # that exact (crashing) behavior, not silently guard it -- guarding
        # it would be a behavior change out of scope for this cycle.
        # RED: ImportError -- writ.analysis.friction has no render_audit_json
        # (or aggregate_session) yet.
        from writ.analysis.friction import aggregate_session, render_audit_json

        agg = aggregate_session([])
        with pytest.raises(IndexError):
            render_audit_json("SID-EMPTY", [], agg)


class TestRenderAuditTextParity:
    def test_render_audit_text_matches_current(self) -> None:
        # RED: ImportError -- writ.analysis.friction has no render_audit_text
        # (or aggregate_session) yet.
        from writ.analysis.friction import aggregate_session, render_audit_text

        events = _synthetic_session_events()
        agg = aggregate_session(events)
        out = render_audit_text("SID-1", events, agg)

        assert out == EXPECTED_TEXT, (
            f"render_audit_text output is not byte-identical to the captured "
            f"writ.cli._render_audit_text parity fixture.\ngot={out!r}"
        )

    def test_render_audit_text_empty_events_raises_index_error(self) -> None:
        # Parity edge case, mirrors test_render_audit_json_empty_events_raises_index_error:
        # _render_audit_text also dereferences session_events[0] unconditionally.
        # RED: ImportError -- writ.analysis.friction has no render_audit_text
        # (or aggregate_session) yet.
        from writ.analysis.friction import aggregate_session, render_audit_text

        agg = aggregate_session([])
        with pytest.raises(IndexError):
            render_audit_text("SID-EMPTY", [], agg)


class TestFrictionAllExports:
    """Post-extraction contract: the three new public names are exported from
    writ.analysis.friction.__all__ (the _agg_* handlers and
    _SESSION_EVENT_HANDLERS stay private/unexported, per plan.md)."""

    def test_new_public_names_are_defined_and_exported(self) -> None:
        # RED now: writ.analysis.friction currently exposes "load_events" et al.
        # but not aggregate_session / render_audit_json / render_audit_text.
        # This import of the *module* succeeds today (it does not name the
        # missing attributes), so this test's RED reason is an AssertionError,
        # not an ImportError -- documented separately from the parity tests
        # above, which fail with ImportError.
        import writ.analysis.friction as friction_mod

        for name in ("aggregate_session", "render_audit_json", "render_audit_text"):
            assert hasattr(friction_mod, name), (
                f"writ.analysis.friction has no attribute {name!r} yet "
                f"(extraction not landed)"
            )
            assert name in friction_mod.__all__, (
                f"{name!r} must be added to writ.analysis.friction.__all__"
            )

    def test_agg_handlers_stay_private(self) -> None:
        # plan.md: the _agg_* handlers and _SESSION_EVENT_HANDLERS dispatch dict
        # move to friction.py but stay PRIVATE (not in __all__). This guards
        # against accidentally over-exporting internals during the move.
        import writ.analysis.friction as friction_mod

        assert "_SESSION_EVENT_HANDLERS" not in friction_mod.__all__
        for name in friction_mod.__all__:
            assert not name.startswith("_agg_"), (
                f"{name!r} is a private aggregation handler and must not be "
                f"exported from writ.analysis.friction.__all__"
            )
