"""Phase 4c D3: writ-postcompact.sh emits verify-discipline directive.

PSR-004 finding: after /compact, the model treats recalled verification
output (e.g. "last run was 6 tests, 13 assertions, all passing") as
fresh evidence. The architectural defense is to make the existing
PostCompact hook emit a directive into the next-turn context that
forces a re-verify mindset.

Tests verify the directive contains key phrases and is emitted to
stdout (which Claude Code injects into next-turn context per its
PostCompact contract).
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

WRIT_ROOT = Path(__file__).resolve().parent.parent
HOOK = WRIT_ROOT / ".claude" / "hooks" / "writ-postcompact.sh"


def _run_hook(stdin_json: dict) -> tuple[str, str, int]:
    proc = subprocess.run(
        [str(HOOK)],
        input=json.dumps(stdin_json),
        capture_output=True, text=True,
        cwd=str(WRIT_ROOT),
    )
    return proc.stdout, proc.stderr, proc.returncode


class TestPostCompactDirective:
    """The hook emits a verify-discipline directive on stdout after compact."""

    def test_directive_emitted_on_stdout(self) -> None:
        stdout, _, code = _run_hook({"session_id": "diag", "event": "compact"})
        assert code == 0, "PostCompact hook must exit 0"
        # Directive should be visible on stdout (next-turn context).
        assert stdout.strip(), "Hook must emit a non-empty directive on stdout"

    def test_directive_mentions_compaction(self) -> None:
        stdout, _, _ = _run_hook({"session_id": "diag", "event": "compact"})
        assert "compact" in stdout.lower(), (
            "Directive must reference the compaction event so the model "
            "knows why this directive is firing"
        )

    def test_directive_mentions_recalled_or_second_hand_evidence(self) -> None:
        stdout, _, _ = _run_hook({"session_id": "diag", "event": "compact"})
        signals = ["recalled", "second-hand", "second hand", "remembered", "pre-compact"]
        assert any(s in stdout.lower() for s in signals), (
            "Directive must signal that pre-compact memory is now "
            f"second-hand evidence (one of {signals!r})"
        )

    def test_directive_instructs_reverify(self) -> None:
        stdout, _, _ = _run_hook({"session_id": "diag", "event": "compact"})
        signals = ["re-run", "rerun", "re-verify", "reverify", "verify"]
        assert any(s in stdout.lower() for s in signals), (
            f"Directive must instruct re-verification (one of {signals!r})"
        )

    def test_directive_handles_blocked_reverification(self) -> None:
        """PSR-004b finding: when re-run is rejected by tool permissions,
        the model must surface the gap, not collapse to 'yes'. The
        directive needs an explicit blocked-case clause."""
        stdout, _, _ = _run_hook({"session_id": "diag", "event": "compact"})
        lower = stdout.lower()
        assert "blocked" in lower, (
            "Directive must address the blocked/rejected re-verification "
            "case explicitly (PSR-004b regression)"
        )

    def test_directive_uses_stop_language(self) -> None:
        """The blocked case needs imperative STOP language so the model
        does not slide from 'blocked' into a confident affirmative."""
        stdout, _, _ = _run_hook({"session_id": "diag", "event": "compact"})
        assert "STOP" in stdout, (
            "Directive must include STOP language for the blocked case "
            "to interrupt the rejection-as-confirmation reflex"
        )

    def test_directive_forbids_yes_without_evidence(self) -> None:
        """Explicitly forbidden response language (PSR-004b option-a fix)."""
        stdout, _, _ = _run_hook({"session_id": "diag", "event": "compact"})
        lower = stdout.lower()
        assert "forbidden" in lower, (
            "Directive must use 'forbidden' framing so the model recognizes "
            "answering 'yes' without re-verify as a hard rule, not advice"
        )

    def test_directive_mentions_fresh_evidence(self) -> None:
        """The directive must distinguish recalled output from fresh evidence."""
        stdout, _, _ = _run_hook({"session_id": "diag", "event": "compact"})
        assert "fresh evidence" in stdout.lower(), (
            "Directive must contrast recalled output with 'fresh evidence' "
            "so the model knows what counts as a valid affirmative"
        )


class TestHookExecutability:
    """The hook is executable and bash-syntax-valid."""

    def test_hook_exists(self) -> None:
        assert HOOK.exists(), f"{HOOK} does not exist"

    def test_hook_executable(self) -> None:
        import os
        assert os.access(HOOK, os.X_OK), f"{HOOK} is not executable"

    def test_hook_syntax(self) -> None:
        proc = subprocess.run(
            ["bash", "-n", str(HOOK)],
            capture_output=True, text=True,
        )
        assert proc.returncode == 0, f"Syntax error: {proc.stderr}"


class TestExistingBehaviorPreserved:
    """Adding the directive must not break existing PostCompact logic."""

    def test_hook_does_not_throw_on_minimal_input(self) -> None:
        """A minimal/empty stdin should not crash the hook."""
        stdout, stderr, code = _run_hook({})
        assert code == 0, (
            f"Hook must handle minimal input gracefully. stderr={stderr!r}"
        )

    def test_hook_does_not_emit_deny_decision(self) -> None:
        """Hook is informational, not blocking."""
        stdout, _, _ = _run_hook({"session_id": "diag", "event": "compact"})
        compact_stdout = stdout.replace(" ", "")
        assert '"permissionDecision":"deny"' not in compact_stdout
        assert '"permissionDecision": "deny"' not in stdout
