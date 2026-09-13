"""Dual-format deny/ask/block payloads honor both Claude and Grok contracts."""

from __future__ import annotations

from writ.harness.decisions import dualize_pretool, pretool_payload, stop_payload


def test_deny_has_both_claude_and_grok_fields():
    payload = pretool_payload("deny", "blocked by plan gate")
    assert payload["decision"] == "deny"
    assert payload["reason"] == "blocked by plan gate"
    hso = payload["hookSpecificOutput"]
    assert hso["permissionDecision"] == "deny"
    assert hso["permissionDecisionReason"] == "blocked by plan gate"
    assert hso["hookEventName"] == "PreToolUse"


def test_ask_maps_to_grok_deny():
    payload = pretool_payload("ask", "confirm this write")
    assert payload["decision"] == "deny"
    assert payload["hookSpecificOutput"]["permissionDecision"] == "ask"


def test_allow_is_allow_on_both():
    payload = pretool_payload("allow", "")
    assert payload["decision"] == "allow"
    assert payload["hookSpecificOutput"]["permissionDecision"] == "allow"


def test_updated_input_and_additional_context_ride_along():
    payload = pretool_payload(
        "allow",
        "",
        additional_context="rules here",
        updated_input={"command": "echo hi"},
    )
    hso = payload["hookSpecificOutput"]
    assert hso["additionalContext"] == "rules here"
    assert hso["updatedInput"] == {"command": "echo hi"}


def test_dualize_adds_top_level_to_existing_claude_deny():
    payload = dualize_pretool(
        {
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "deny",
                "permissionDecisionReason": "nope",
            }
        }
    )
    assert payload["decision"] == "deny"
    assert payload["reason"] == "nope"


def test_stop_block_payload():
    payload = stop_payload("run the tests")
    assert payload == {"decision": "block", "reason": "run the tests"}


def test_stop_hook_active_matches_camel_case():
    import subprocess
    from pathlib import Path

    repo = Path(__file__).resolve().parent.parent
    script = r"""
source bin/lib/common.sh
stop_hook_active '{"stopHookActive": true}' && echo camel-yes || echo camel-no
stop_hook_active '{"stop_hook_active": true}' && echo snake-yes || echo snake-no
stop_hook_active '{"stopHookActive": false}' && echo false-yes || echo false-no
"""
    proc = subprocess.run(
        ["bash", "-c", script],
        cwd=str(repo),
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert proc.returncode == 0, proc.stderr
    assert "camel-yes" in proc.stdout
    assert "snake-yes" in proc.stdout
    assert "false-no" in proc.stdout
