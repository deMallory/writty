"""POL-5b-2b: migrate the 4 nuanced hooks to load_hook_env.

Adds HOOK_SESSION_ID_RAW (raw session_id, no agent fallback) for mark-pending-test's
parent-session keying; removes inject-tier's dead `tier set` branch; gate-first
reorders inject-tier. web-capture / inject-tier read non-scalar fields from
$HOOK_ENVELOPE. (track-failed-writes removed in #3 -- its PostToolUseFailure
Write|Edit surface never fires; see test_pol5b2c_removal.)

RED until the emitter field is added and the 4 hooks are migrated.
"""

from __future__ import annotations

import json
import os
import shlex
import subprocess
from pathlib import Path

import pytest

SKILL_DIR = Path(__file__).resolve().parent.parent
PARSE_PY = str(SKILL_DIR / "bin" / "lib" / "parse-hook-stdin.py")
HOOKS = SKILL_DIR / "hooks" / "scripts"

NUANCED = [
    "writ-mark-pending-test.sh",
    "writ-web-capture.sh",
    "inject-tier-workflow.sh",
]
ENVELOPE_HOOKS = ["writ-web-capture.sh", "inject-tier-workflow.sh"]


def _shell_then_print(envelope: str, var: str) -> str:
    script = (
        f'eval "$(printf %s {shlex.quote(envelope)} | python3 {shlex.quote(PARSE_PY)} --shell)"; '
        f'printf "%s" "${{{var}}}"'
    )
    return subprocess.run(["bash", "-c", script], capture_output=True, text=True, timeout=10).stdout


def _run(hook: str, envelope: str, cwd: str | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["bash", str(HOOKS / hook)],
        input=envelope, capture_output=True, text=True,
        cwd=cwd or str(SKILL_DIR),
        env={**os.environ, "WRIT_HOST": "localhost"},
        timeout=20,
    )


# --------------------------------------------------------------------------- #
# 1. emitter: HOOK_SESSION_ID_RAW
# --------------------------------------------------------------------------- #
class TestRawSessionId:
    def test_raw_is_session_id_not_agent_id(self) -> None:
        env = '{"agent_id":"agent-9","session_id":"sid-1","tool_input":{}}'
        assert _shell_then_print(env, "HOOK_SESSION_ID_RAW") == "sid-1"
        assert _shell_then_print(env, "HOOK_SESSION_ID") == "agent-9"

    def test_raw_empty_when_no_session_id(self) -> None:
        env = '{"agent_id":"agent-9","session_id":"","tool_input":{}}'
        assert _shell_then_print(env, "HOOK_SESSION_ID_RAW") == ""


# --------------------------------------------------------------------------- #
# 2. migration markers
# --------------------------------------------------------------------------- #
class TestMigration:
    @pytest.mark.parametrize("hook", NUANCED)
    def test_uses_load_hook_env(self, hook: str) -> None:
        assert "load_hook_env" in (HOOKS / hook).read_text(), f"{hook} must call load_hook_env"

    @pytest.mark.parametrize("hook", NUANCED)
    def test_dropped_old_idiom(self, hook: str) -> None:
        src = (HOOKS / hook).read_text()
        for stale in ("parsed_field", "parse_hook_stdin", "detect_session_id", "parsed_bool"):
            assert stale not in src, f"{hook} must not still use {stale}"

    def test_mark_pending_test_uses_raw_session(self) -> None:
        assert "HOOK_SESSION_ID_RAW" in (HOOKS / "writ-mark-pending-test.sh").read_text()

    @pytest.mark.parametrize("hook", ENVELOPE_HOOKS)
    def test_envelope_hooks_use_hook_envelope(self, hook: str) -> None:
        src = (HOOKS / hook).read_text()
        assert "HOOK_ENVELOPE" in src, f"{hook} must read $HOOK_ENVELOPE"
        assert "$PARSED" not in src, f"{hook} must not reference $PARSED after migration"

    def test_inject_tier_dead_branch_removed(self) -> None:
        assert "tier set" not in (HOOKS / "inject-tier-workflow.sh").read_text(), (
            "the dead `tier set` branch must be removed"
        )


# --------------------------------------------------------------------------- #
# 3. inject-tier behavior preserved (mode-set injection)
# --------------------------------------------------------------------------- #
class TestInjectTierBehavior:
    def test_injects_on_mode_set(self) -> None:
        env = json.dumps({
            "hook_event_name": "PostToolUse", "tool_name": "Bash", "session_id": "sid-it",
            "tool_input": {"command": "python3 writ-session.py mode set review sid-it"},
            "tool_output": "set: review",
        })
        r = _run("inject-tier-workflow.sh", env)
        assert r.returncode == 0
        assert "Review mode" in r.stdout, f"mode-set injection lost; stdout={r.stdout!r}"

    def test_no_injection_on_normal_command(self) -> None:
        env = json.dumps({
            "hook_event_name": "PostToolUse", "tool_name": "Bash", "session_id": "sid-it",
            "tool_input": {"command": "ls -la"}, "tool_output": "total 0",
        })
        r = _run("inject-tier-workflow.sh", env)
        assert r.returncode == 0
        assert r.stdout.strip() == "", f"normal Bash must not inject; stdout={r.stdout!r}"


# --------------------------------------------------------------------------- #
# 4. behavior smoke
# --------------------------------------------------------------------------- #
class TestBehaviorPreserved:
    @pytest.mark.parametrize("hook", NUANCED)
    def test_runs_clean(self, hook: str) -> None:
        env = json.dumps({
            "hook_event_name": "PostToolUse", "tool_name": "Write", "session_id": "sid-5b2b",
            "tool_input": {"file_path": "/tmp/pol5b2b.txt", "content": "x"},
            "tool_output": "ok",
        })
        r = _run(hook, env)
        assert r.returncode == 0, f"{hook} exited {r.returncode}; stderr={r.stderr[:200]!r}"
