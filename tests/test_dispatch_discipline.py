"""Fix B (Phase 3): the dispatch-discipline Task hook steers generic dispatches.

hooks/scripts/writ-dispatch-discipline.sh is a PreToolUse(Task) hook. In governed modes
(work / investigate / unset), a generic dispatch (subagent_type general-purpose / Explore /
claude / empty) with no escape marker is REWRITTEN via updatedInput to the Writ role that
matches the prompt -- so the model proceeds with the governed role directly, no deny/retry
(SKL-PROC-DISPATCH-001). A prompt that maps to no specific role falls back to deny+ask.
Named (writ-*) roles, escape-hatched prompts, and non-governed modes pass through untouched
-- the hook never blocks a dispatch spuriously (ERR-GRACEFUL-001).

Per TEST-REGRESSION-001: these assert the new behavior; they fail against the absent hook
and pass once it is wired.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys

import pytest

HOOK = os.path.abspath(
    os.path.join(
        os.path.dirname(__file__),
        os.pardir,
        "hooks",
        "scripts",
        "writ-dispatch-discipline.sh",
    )
)
HELPER = os.path.abspath(
    os.path.join(os.path.dirname(__file__), os.pardir, "bin", "lib", "writ-session.py")
)


def _seed_mode(cache_dir, sid, mode):
    """Set the master session's mode via the file-direct CLI (how production sets it)."""
    env = os.environ.copy()
    env["WRIT_CACHE_DIR"] = str(cache_dir)
    subprocess.run(
        [sys.executable, HELPER, "mode", "set", mode, sid],
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )


def _run_hook(cache_dir, master_sid, *, subagent_type, prompt):
    env = os.environ.copy()
    env["WRIT_CACHE_DIR"] = str(cache_dir)
    env["WRIT_FRICTION_LOG"] = os.path.join(str(cache_dir), "friction.log")
    envelope = {
        "session_id": master_sid,
        "hook_event_name": "PreToolUse",
        "tool_name": "Task",
        "tool_input": {"subagent_type": subagent_type, "prompt": prompt},
    }
    res = subprocess.run(
        ["bash", HOOK],
        input=json.dumps(envelope),
        capture_output=True,
        text=True,
        env=env,
        timeout=20,
    )
    assert res.returncode == 0, res.stderr  # denial is via stdout JSON, never exit code
    return res.stdout


def _decision(stdout):
    """Parse the hook's stdout; return (permissionDecision, reason) or (None, '')."""
    out = stdout.strip()
    if not out:
        return None, ""
    payload = json.loads(out)
    hso = payload.get("hookSpecificOutput", {})
    return hso.get("permissionDecision"), hso.get("permissionDecisionReason", "")


def _rewrite_target(stdout):
    """The subagent_type the hook rewrote the dispatch to via updatedInput (or None)."""
    out = stdout.strip()
    if not out:
        return None
    hso = json.loads(out).get("hookSpecificOutput", {})
    return (hso.get("updatedInput") or {}).get("subagent_type")


class TestDispatchDiscipline:
    def test_work_generic_explore_routes_to_explorer(self, tmp_path):
        _seed_mode(tmp_path, "m1", "work")
        out = _run_hook(
            tmp_path, "m1",
            subagent_type="general-purpose",
            prompt="explore the codebase structure and find where auth is handled",
        )
        assert _decision(out)[0] == "allow"
        assert _rewrite_target(out) == "writ-explorer"

    def test_work_named_role_allowed(self, tmp_path):
        """A named writ-* role is the correct dispatch -> pass through (no deny)."""
        _seed_mode(tmp_path, "m2", "work")
        out = _run_hook(
            tmp_path, "m2",
            subagent_type="writ-explorer",
            prompt="explore the codebase structure",
        )
        decision, _ = _decision(out)
        assert decision is None

    def test_escape_hatch_allows_generic(self, tmp_path):
        """An explicit [general-purpose] marker overrides the discipline."""
        _seed_mode(tmp_path, "m3", "work")
        out = _run_hook(
            tmp_path, "m3",
            subagent_type="general-purpose",
            prompt="[general-purpose] do this odd one-off task with no matching role",
        )
        decision, _ = _decision(out)
        assert decision is None

    def test_conversation_mode_not_enforced(self, tmp_path):
        """Conversation is not governed work -> pass through (a quick lookup mid-chat is fine)."""
        _seed_mode(tmp_path, "m4", "conversation")
        out = _run_hook(
            tmp_path, "m4",
            subagent_type="general-purpose",
            prompt="explore the codebase structure",
        )
        decision, _ = _decision(out)
        assert decision is None

    def test_investigate_mode_enforced(self, tmp_path):
        """Investigate (audit/explore) IS governed dispatch -> a generic audit dispatch is
        steered to writ-explorer. This is the exact scenario that slipped through before:
        an audit request must use the named role, not the built-in Explore/general-purpose."""
        _seed_mode(tmp_path, "m4b", "investigate")
        out = _run_hook(
            tmp_path, "m4b",
            subagent_type="general-purpose",
            prompt="audit the codebase for security issues and find where input is validated",
        )
        assert _decision(out)[0] == "allow"
        assert _rewrite_target(out) == "writ-explorer"

    def test_work_generic_research_routes_to_explorer(self, tmp_path):
        """'research ...' must route to writ-explorer (investigation engine)."""
        _seed_mode(tmp_path, "m4c", "work")
        out = _run_hook(
            tmp_path, "m4c",
            subagent_type="general-purpose",
            prompt="research how the session cache is keyed and what TTL is applied",
        )
        assert _decision(out)[0] == "allow"
        assert _rewrite_target(out) == "writ-explorer"

    def test_work_generic_implement_routes_to_implementer(self, tmp_path):
        """'implement the approved plan' routes to writ-implementer, not writ-planner."""
        _seed_mode(tmp_path, "m5", "work")
        out = _run_hook(
            tmp_path, "m5",
            subagent_type="general-purpose",
            prompt="implement the approved plan in the orders module",
        )
        assert _decision(out)[0] == "allow"
        assert _rewrite_target(out) == "writ-implementer"

    def test_work_builtin_explore_type_routes_to_explorer(self, tmp_path):
        """The built-in 'Explore' subagent_type is generic and is rewritten too."""
        _seed_mode(tmp_path, "m6", "work")
        out = _run_hook(
            tmp_path, "m6",
            subagent_type="Explore",
            prompt="investigate how the session cache is keyed",
        )
        assert _decision(out)[0] == "allow"
        assert _rewrite_target(out) == "writ-explorer"

    def test_empty_subagent_type_in_work_routes_to_planner(self, tmp_path):
        """An empty subagent_type (defaults to generic) is rewritten in work mode."""
        _seed_mode(tmp_path, "m7", "work")
        out = _run_hook(
            tmp_path, "m7",
            subagent_type="",
            prompt="plan the implementation of the new export endpoint",
        )
        assert _decision(out)[0] == "allow"
        assert _rewrite_target(out) == "writ-planner"

    def test_work_generic_ambiguous_denied(self, tmp_path):
        """A generic dispatch whose prompt maps to no specific role is DENIED (we ask rather
        than force a possibly-wrong role) -- the deny fallback the rewrite path preserves."""
        _seed_mode(tmp_path, "m8", "work")
        out = _run_hook(
            tmp_path, "m8",
            subagent_type="general-purpose",
            prompt="handle this one-off miscellaneous chore",
        )
        decision, reason = _decision(out)
        assert decision == "deny"
        assert "did not map to a specific Writ role" in reason

    # --- Binding extended to UNSET mode (2026-06-18) ----------------------------
    # Real engineering work routinely runs with no mode set; that ungoverned gap let
    # general-purpose agents through (observed in a real client project: most dispatches
    # ran mode=None). Unset mode is now governed like work/investigate.

    def test_unset_mode_generic_routes_to_role(self, tmp_path):
        """No mode set (the real-client-project case): a generic dispatch is now REWRITTEN
        to the matching writ-* role (was the ungoverned leak)."""
        # NB: no _seed_mode -> the session has no mode -> `mode get` returns "".
        out = _run_hook(
            tmp_path, "u1",
            subagent_type="general-purpose",
            prompt="explore the codebase and find where auth is handled",
        )
        assert _decision(out)[0] == "allow"
        assert _rewrite_target(out) == "writ-explorer"

    def test_unset_mode_named_role_allowed(self, tmp_path):
        """A named writ-* role is correct even with no mode set -> pass through."""
        out = _run_hook(
            tmp_path, "u2",
            subagent_type="writ-explorer",
            prompt="explore the codebase",
        )
        assert _decision(out)[0] is None

    def test_unset_mode_escape_hatch_allowed(self, tmp_path):
        """The [general-purpose] hatch still overrides when no mode is set."""
        out = _run_hook(
            tmp_path, "u3",
            subagent_type="general-purpose",
            prompt="[general-purpose] a genuine one-off with no matching role",
        )
        assert _decision(out)[0] is None

    def test_debug_mode_not_enforced(self, tmp_path):
        """debug is a deliberately-chosen non-build mode (own flow, Explore agents) ->
        stays ungoverned."""
        _seed_mode(tmp_path, "d1", "debug")
        out = _run_hook(
            tmp_path, "d1",
            subagent_type="general-purpose",
            prompt="explore the failing code path",
        )
        assert _decision(out)[0] is None

    def test_review_mode_not_enforced(self, tmp_path):
        """review (read-only) stays ungoverned."""
        _seed_mode(tmp_path, "r1", "review")
        out = _run_hook(
            tmp_path, "r1",
            subagent_type="general-purpose",
            prompt="review the diff for correctness",
        )
        assert _decision(out)[0] is None
