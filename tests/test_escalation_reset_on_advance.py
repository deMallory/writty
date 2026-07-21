"""tests/test_escalation_reset_on_advance.py

Wave 1 Cycle 5 -- Decision G2: escalation.needed never resets.

cmd_invalidate_gate sets cache["escalation"] = {gate, needed: True, diagnosis,
feedback_sent: False} once a gate reaches MAX_CYCLES_BEFORE_ESCALATION, but
nothing ever clears it today, so cmd_check_escalation reports needed: True
forever. The fix adds mutation #6 (escalation reset) to the shared
apply_phase_advance unit, gated on `escalation["gate"] == target_gate` -- only
the gate that actually resolves the escalation clears it.

TestApplyPhaseAdvanceClearsMatchingEscalation is hermetic (plain dict, no
cache files). TestCmdCheckEscalationReportsResolved drives the real
cmd_invalidate_gate / cmd_check_escalation facade commands against a real
(tmp_path-isolated) session cache, matching the end-to-end contract a real
gate resolution must satisfy.

RED today: apply_phase_advance has no escalation-reset mutation at all, so
every "matching gate clears" assertion below fails (needed stays True).

Per TEST-TDD-001: skeletons approved before implementation.
"""

from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import os
import uuid

SKILL_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
FACADE_PATH = os.path.join(SKILL_ROOT, "bin", "lib", "writ-session.py")


def _load_facade():
    spec = importlib.util.spec_from_file_location("writ_session_g2", FACADE_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _call_json(fn, *args):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        fn(*args)
    return json.loads(buf.getvalue().strip())


def _escalated_cache(gate: str = "phase-a", **overrides) -> dict:
    """Minimal cache carrying an active escalation for `gate`."""
    cache = {
        "phase_transitions": [],
        "escalation": {
            "gate": gate,
            "needed": True,
            "diagnosis": "same-rule",
            "feedback_sent": False,
        },
    }
    cache.update(overrides)
    return cache


# ---------------------------------------------------------------------------
# Hermetic: apply_phase_advance's escalation mutation, in isolation
# ---------------------------------------------------------------------------


class TestApplyPhaseAdvanceClearsMatchingEscalation:
    """Drive apply_phase_advance directly on a plain dict cache."""

    def test_matching_gate_clears_needed(self):
        from writ.session.approval_workflow import apply_phase_advance

        cache = _escalated_cache(gate="phase-a")
        apply_phase_advance(
            cache, "phase-a", "planning", "testing",
            trigger="user-approved", mode="work",
        )
        assert cache["escalation"]["needed"] is False

    def test_matching_gate_clears_gate_field(self):
        from writ.session.approval_workflow import apply_phase_advance

        cache = _escalated_cache(gate="phase-a")
        apply_phase_advance(
            cache, "phase-a", "planning", "testing",
            trigger="user-approved", mode="work",
        )
        assert cache["escalation"]["gate"] is None

    def test_matching_gate_clears_feedback_sent(self):
        from writ.session.approval_workflow import apply_phase_advance

        cache = _escalated_cache(gate="phase-a", escalation={
            "gate": "phase-a", "needed": True, "diagnosis": "same-rule", "feedback_sent": True,
        })
        apply_phase_advance(
            cache, "phase-a", "planning", "testing",
            trigger="user-approved", mode="work",
        )
        assert cache["escalation"]["feedback_sent"] is False

    def test_non_matching_gate_leaves_escalation_untouched(self):
        """Guards the 'only reset the matching gate' decision: gates advance in
        sequence, so an escalation on a still-unapproved LATER gate must not be
        cleared by advancing an EARLIER one."""
        from writ.session.approval_workflow import apply_phase_advance

        cache = _escalated_cache(gate="test-skeletons")
        apply_phase_advance(
            cache, "phase-a", "planning", "testing",
            trigger="user-approved", mode="work",
        )
        assert cache["escalation"]["needed"] is True
        assert cache["escalation"]["gate"] == "test-skeletons"

    def test_no_escalation_seeded_is_a_noop(self):
        """The guard (isinstance dict + needed) must be a no-op for the many
        callers that seed no escalation at all -- must not raise or fabricate
        an escalation dict where none existed."""
        from writ.session.approval_workflow import apply_phase_advance

        cache = {"phase_transitions": []}
        apply_phase_advance(
            cache, "phase-a", "planning", "testing",
            trigger="user-approved", mode="work",
        )
        assert "escalation" not in cache

    def test_already_resolved_escalation_is_left_alone(self):
        """needed already False (a previously-resolved escalation) must not be
        disturbed -- 'gate' stays as-is, not reset to None on every advance."""
        from writ.session.approval_workflow import apply_phase_advance

        cache = _escalated_cache(gate="phase-a", escalation={
            "gate": "phase-a", "needed": False, "diagnosis": None, "feedback_sent": False,
        })
        apply_phase_advance(
            cache, "phase-a", "planning", "testing",
            trigger="user-approved", mode="work",
        )
        assert cache["escalation"]["needed"] is False
        assert cache["escalation"]["gate"] == "phase-a"


# ---------------------------------------------------------------------------
# End-to-end: cmd_invalidate_gate escalates, a resolving advance clears it
# ---------------------------------------------------------------------------


class TestCmdCheckEscalationReportsResolved:
    """After cmd_invalidate_gate escalates a gate, a successful advance through
    that SAME gate must make cmd_check_escalation report needed=False; an
    advance through a DIFFERENT gate must not."""

    def _escalate(self, ws, sid: str, gate: str) -> None:
        for _ in range(ws.MAX_CYCLES_BEFORE_ESCALATION):
            ws.cmd_invalidate_gate(sid, [gate, "--rule", "ENF-001", "--file", "a.py"])

    def test_escalation_resets_after_matching_advance(self, tmp_path, monkeypatch):
        monkeypatch.setenv("WRIT_CACHE_DIR", str(tmp_path))
        ws = _load_facade()
        sid = f"g2-match-{uuid.uuid4().hex[:8]}"
        self._escalate(ws, sid, "phase-a")

        pre = _call_json(ws.cmd_check_escalation, sid)
        assert pre["needed"] is True  # sanity: the escalation really landed

        from writ.session.approval_workflow import apply_phase_advance
        from writ.session.cache import _read_cache, _write_cache

        cache = _read_cache(sid)
        apply_phase_advance(
            cache, "phase-a", "planning", "testing",
            trigger="user-approved", mode="work",
        )
        _write_cache(sid, cache)

        post = _call_json(ws.cmd_check_escalation, sid)
        assert post["needed"] is False, (
            "a successful advance through the escalated gate must clear "
            "cmd_check_escalation's needed flag"
        )

    def test_escalation_survives_advance_on_different_gate(self, tmp_path, monkeypatch):
        monkeypatch.setenv("WRIT_CACHE_DIR", str(tmp_path))
        ws = _load_facade()
        sid = f"g2-other-{uuid.uuid4().hex[:8]}"
        self._escalate(ws, sid, "test-skeletons")

        pre = _call_json(ws.cmd_check_escalation, sid)
        assert pre["needed"] is True

        from writ.session.approval_workflow import apply_phase_advance
        from writ.session.cache import _read_cache, _write_cache

        cache = _read_cache(sid)
        apply_phase_advance(
            cache, "phase-a", "planning", "testing",
            trigger="user-approved", mode="work",
        )
        _write_cache(sid, cache)

        post = _call_json(ws.cmd_check_escalation, sid)
        assert post["needed"] is True, (
            "advancing a gate OTHER than the escalated one must not clear the "
            "escalation banner"
        )
