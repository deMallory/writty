"""Dual-format hook decisions for Claude Code and Grok Build.

Claude honors hookSpecificOutput.permissionDecision.
Grok honors top-level {"decision": "deny"|"allow"|"block", "reason": "..."}.
One payload must satisfy both or Grok fail-opens.
"""

from __future__ import annotations

import json
import sys
from typing import Any


def pretool_payload(
    decision: str,
    reason: str = "",
    additional_context: str = "",
    updated_input: dict | None = None,
) -> dict[str, Any]:
    """Build a PreToolUse decision that both hosts honor.

    Grok has no `ask`; that maps to a deny so escalation cannot fail open.
    """
    grok_decision = "deny" if decision in ("deny", "ask") else "allow"
    hso: dict[str, Any] = {
        "hookEventName": "PreToolUse",
        "permissionDecision": decision,
        "permissionDecisionReason": reason,
    }
    if additional_context:
        hso["additionalContext"] = additional_context
    if updated_input is not None:
        hso["updatedInput"] = updated_input
    payload: dict[str, Any] = {
        "decision": grok_decision,
        "reason": reason,
        "hookSpecificOutput": hso,
    }
    return payload


def dualize_pretool(payload: dict) -> dict:
    """Add Grok top-level decision/reason to an existing Claude PreToolUse object."""
    hso = payload.get("hookSpecificOutput") or {}
    perm = hso.get("permissionDecision")
    if perm in ("deny", "ask"):
        payload["decision"] = "deny"
        payload["reason"] = hso.get("permissionDecisionReason") or payload.get("reason") or ""
    elif perm == "allow":
        payload.setdefault("decision", "allow")
        payload.setdefault("reason", hso.get("permissionDecisionReason") or "")
    return payload


def stop_payload(reason: str) -> dict[str, Any]:
    """Build a Stop/SubagentStop block both hosts honor."""
    return {"decision": "block", "reason": reason}


def emit_pretool(
    decision: str,
    reason: str = "",
    additional_context: str = "",
    updated_input: dict | None = None,
) -> None:
    json.dump(
        pretool_payload(decision, reason, additional_context, updated_input),
        sys.stdout,
    )
    sys.stdout.write("\n")


def emit_stop(reason: str) -> None:
    json.dump(stop_payload(reason), sys.stdout)
    sys.stdout.write("\n")
