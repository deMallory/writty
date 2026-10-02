"""Regression: a phase advance must record the approved gate in cache['gates_approved'].

Root cause (debug 2026-06-30): two phase-advance paths diverged. The CLI path
(approval_workflow._apply_gate_advance) records the approved gate in
cache['gates_approved'] AND sets current_phase. The live HTTP path
(server.py _advance) advanced current_phase but never touched gates_approved.
The work-mode write gate (gates._check_work_gate) authorizes writes from
gates_approved (deny ENF-GATE-PLAN when 'phase-a' is absent), so on the live
path gates_approved stayed [] no matter how many times the user approved, and
every non-skill-exempt, non-excluded production write was blocked. The writ repo
hid the bug because its writes are skill_exempt; other projects hit the wall.

Fix: both paths now delegate ALL five cache mutations to the shared
apply_phase_advance function in approval_workflow.py, which records the gate via
sorted set-union, sets current_phase, clears denial_counts[target_gate], rolls
loaded_rule_ids_by_phase, and appends a full phase_transitions record.

TestRecordApprovedGate is hermetic (no daemon, no network). The three
add/sorted/preserve cases now drive apply_phase_advance's gates_approved behavior
directly. The non-work and all-approved no-op cases are reframed at the level
where the no-advance decision actually lives: _next_pending_gate returning None
is the signal both callers use to skip apply_phase_advance entirely.

The end-to-end check against the live daemon (TestAdvancePopulatesGatesApproved)
was retired 2026-09-09 because it skipped unconditionally on a server-reachability
probe and so never asserted anything; its property is covered in process by
tests/test_phase_advance_unified.py::TestCrossPathParity, which drives the real
route and asserts gates_approved == ["phase-a", "test-skeletons"].
"""

from __future__ import annotations


# ---------------------------------------------------------------------------
# Hermetic: gates_approved behavior of apply_phase_advance (repointed from
# the removed record_approved_gate helper)
# ---------------------------------------------------------------------------

class TestRecordApprovedGate:
    """Repointed from the removed mode_engine.record_approved_gate.

    Cases (a): gates_approved add/sorted/preserve -- now assert
    apply_phase_advance's gates_approved behavior.
    Cases (b): non-work and all-gates-approved no-op -- now assert that
    _next_pending_gate returns None (the no-advance signal used by both
    callers to skip apply_phase_advance).
    """

    # (a) apply_phase_advance gates_approved behavior -------------------------

    def test_fresh_work_session_records_phase_a_gate(self):
        """apply_phase_advance adds phase-a to an empty gates_approved list."""
        from writ.session.approval_workflow import apply_phase_advance

        cache = {"gates_approved": [], "phase_transitions": []}
        apply_phase_advance(
            cache, "phase-a", "planning", "testing",
            trigger="user-approved", mode="work",
        )
        assert cache["gates_approved"] == ["phase-a"]

    def test_after_phase_a_adding_test_skeletons_preserves_prior_gate(self):
        """apply_phase_advance adds test-skeletons while keeping phase-a present
        and the result sorted."""
        from writ.session.approval_workflow import apply_phase_advance

        cache = {"gates_approved": ["phase-a"], "phase_transitions": []}
        apply_phase_advance(
            cache, "test-skeletons", "testing", "implementation",
            trigger="user-approved", mode="work",
        )
        assert cache["gates_approved"] == ["phase-a", "test-skeletons"]

