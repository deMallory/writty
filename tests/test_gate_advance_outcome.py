"""Tests for the advance-phase response classifier (bin/lib/gate_advance_outcome.py)."""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "bin", "lib"))

from gate_advance_outcome import classify  # noqa: E402


# -- Existing tests (must stay GREEN) ----------------------------------------

def test_advanced_response_yields_outcome_and_phase():
    r = classify('{"advanced": true, "phase": "testing"}')
    assert r["outcome"] == "advanced"
    assert r["phase"] == "testing"


def test_rejected_response_yields_reason():
    r = classify('{"advanced": false, "error": "plan.md validation failed: Files section"}')
    assert r["outcome"] == "rejected"
    assert "Files" in r["error"]


def test_error_field_alone_is_rejected():
    r = classify('{"error": "Invalid or missing gate token"}')
    assert r["outcome"] == "rejected"
    assert "token" in r["error"].lower()


def test_empty_response_is_none():
    assert classify("")["outcome"] == "none"
    assert classify("   ")["outcome"] == "none"


def test_malformed_json_is_none_not_raise():
    assert classify("not json at all")["outcome"] == "none"


def test_advanced_without_phase_is_none():
    # advanced:true but no phase -> nothing to confirm, treat as no-op.
    assert classify('{"advanced": true}')["outcome"] == "none"


# -- New noop tests (RED until classify gains the "noop" outcome) -------------

def test_noop_response_with_reason_and_no_error():
    """Server's benign no-advance path: advanced=false + reason, no error key -> noop."""
    r = classify('{"advanced": false, "reason": "No pending gate to advance", "phase": "planning"}')
    assert r["outcome"] == "noop"
    assert r["error"] == ""


def test_noop_passes_phase_through():
    """The phase from the server response is echoed in the noop result."""
    r = classify('{"advanced": false, "reason": "No pending gate to advance", "phase": "implementation"}')
    assert r["outcome"] == "noop"
    assert r["phase"] == "implementation"


def test_noop_with_different_reason():
    """Any truthy reason without error -> noop, regardless of reason text."""
    r = classify('{"advanced": false, "reason": "All gates already approved"}')
    assert r["outcome"] == "noop"


def test_advanced_false_no_reason_no_error_is_rejected():
    """Defensive: unexplained refusal (no reason, no error) -> rejected, fail toward safe."""
    r = classify('{"advanced": false}')
    assert r["outcome"] == "rejected"


def test_error_wins_over_reason():
    """Error key takes priority: advanced=false + reason + error -> rejected, not noop."""
    r = classify('{"advanced": false, "reason": "x", "error": "bad token"}')
    assert r["outcome"] == "rejected"


def test_error_wins_even_with_reason_populated():
    """Confirm the ordering: error present always -> rejected, even if reason is also present."""
    r = classify('{"advanced": false, "error": "x", "reason": "y"}')
    assert r["outcome"] == "rejected"
