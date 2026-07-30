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


# -- The tab-separated transport the hook parses with `cut` -------------------
#
# The stdout contract grew from 3 fields to 5 (validated + token_spent inserted before
# the error), and auto-approve-gate.sh reads them by position: outcome=-f1, phase=-f2,
# validated=-f3, token_spent=-f4, error=-f5-. A silent position shift would make the hook
# print an artifact path where the error belongs, or claim the wrong token state. Nothing
# tested the emitted line at all, so these pin the wire format itself.

import json  # noqa: E402
import subprocess  # noqa: E402

_SCRIPT = os.path.join(os.path.dirname(__file__), "..", "bin", "lib", "gate_advance_outcome.py")

FIELDS = ("outcome", "phase", "validated", "token_spent", "error")


def _emit(payload: dict) -> list[str]:
    """Run the script the way the hook does and split the first line into fields."""
    proc = subprocess.run(
        [sys.executable, _SCRIPT, json.dumps(payload)],
        capture_output=True, text=True, timeout=30,
    )
    assert proc.returncode == 0, proc.stderr
    return proc.stdout.split("\n")[0].split("\t")


def test_emitted_line_has_five_fields_in_order():
    fields = _emit({"phase": "testing", "project_root": "/p", "root_tier": "cwd",
                    "validated": "/p/plan.md"})
    assert len(fields) == len(FIELDS), f"field count changed: {fields}"
    assert fields[0] == "advanced"
    assert fields[1] == "testing"
    assert "/p/plan.md" in fields[2]
    assert fields[3] == ""          # a successful advance reports no token_spent
    assert fields[4] == ""          # no error


def test_error_is_the_last_field():
    fields = _emit({"advanced": False, "error": "bad plan", "token_spent": True})
    assert fields[0] == "rejected"
    assert fields[3] == "true"
    assert fields[4] == "bad plan"


def test_not_spent_refusal_reports_false():
    fields = _emit({"advanced": False, "error": "no root", "token_spent": False})
    assert fields[3] == "false", "the hook decides its re-approve wording from this field"


def test_missing_token_spent_stays_empty():
    """An older daemon omits the flag; the hook must not infer either state."""
    fields = _emit({"advanced": False, "error": "bad plan"})
    assert fields[3] == ""


def test_validated_never_contains_a_tab_or_newline():
    """A path may legally contain either, and would shift every later field."""
    fields = _emit({"phase": "testing", "project_root": "/p",
                    "validated": "/p/we\tird\nplan.md", "root_tier": "marker"})
    assert len(fields) == len(FIELDS)
    assert "\t" not in fields[2]


def test_multiline_error_keeps_the_fixed_fields_on_line_one():
    """The hook does `head -1 | cut -f4` for token_spent, then `cut -f5-` for the error."""
    proc = subprocess.run(
        [sys.executable, _SCRIPT,
         json.dumps({"advanced": False, "token_spent": True,
                     "error": "line one\nline two\nline three"})],
        capture_output=True, text=True, timeout=30,
    )
    first = proc.stdout.split("\n")[0].split("\t")
    assert first[0] == "rejected"
    assert first[3] == "true"
    assert first[4] == "line one"
    assert "line two" in proc.stdout


def test_hook_cut_positions_match_the_emitter():
    """Parse with the exact cut expressions the hook uses, via a real shell."""
    payload = json.dumps({"advanced": False, "error": "why it failed", "token_spent": False,
                          "project_root": "/p"})
    script = (
        f'RAW=$({sys.executable} {_SCRIPT} {payload!r}); '
        'echo "O=$(printf %s "$RAW" | cut -f1)"; '
        'echo "V=$(printf %s "$RAW" | head -1 | cut -f3)"; '
        'echo "S=$(printf %s "$RAW" | head -1 | cut -f4)"; '
        'echo "E=$(printf %s "$RAW" | cut -f5-)"'
    )
    out = subprocess.run(["bash", "-c", script], capture_output=True, text=True, timeout=30).stdout
    assert "O=rejected" in out
    assert "S=false" in out
    assert "E=why it failed" in out
    assert "project root /p" in out
