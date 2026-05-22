"""Regression test for writ-sdd-review-order.sh JSON-decode bug class.

Context: PSR-008 surfaced "PreToolUse:Agent hook error -- Failed with
non-blocking status code: Traceback ..." on every subagent dispatch.
Root cause was the same shape as the legacy-hotfix bug class
(commit db58ec1):

    parsed = json.loads('''$PARSED''')

Heredoc substitution preserves raw control characters from the
parsed envelope (newlines, tabs, etc. embedded in tool_input fields).
Python's triple-quoted string accepts them; json.loads rejects them.
The hook exits non-zero, "non-blocking status code" so the dispatch
proceeds, but the SDD review-order gate falls open silently.

This test pins the new contract: stdin envelopes containing control
characters do NOT crash the hook.
"""

from __future__ import annotations

import json
import os
import subprocess

import pytest
from pathlib import Path

SKILL_DIR = str(Path.home() / ".claude/skills/writ")
HOOK = f"{SKILL_DIR}/.claude/hooks/writ-sdd-review-order.sh"


def _envelope_with_control_chars() -> str:
    """Mirror what Claude Code passes when the user prompt contains
    multi-line code-fenced text. The literal embedded \\n is what
    breaks json.loads('''$PARSED''') -- the heredoc substitution
    inserts the raw bytes."""
    payload = {
        "session_id": "sdd-bug-repro",
        "tool_input": {
            "subagent_type": "writ-explorer",
            "description": "Explore for X",
            # The break: a multi-line description with embedded
            # newlines + tabs. Real prompts include code fences which
            # have literal newlines.
            "prompt": "line1\nline2\twith tab\nline3 with control\x01char",
        },
    }
    return json.dumps(payload)


class TestSDDReviewOrderHookHandlesControlChars:
    """The hook must not crash on envelopes with control characters
    in tool_input fields. It should either exit cleanly (no deny)
    or emit a structured deny -- but never produce a Python
    traceback."""

    def _seed_work_mode_cache(self, cache_dir: str, session_id: str) -> None:
        """The hook short-circuits at `is_work_mode` if the session
        cache says mode != work. Seed a minimal cache so the hook
        reaches the json.loads line we're testing."""
        path = os.path.join(cache_dir, f"writ-session-{session_id}.json")
        with open(path, "w") as f:
            json.dump({"mode": "work", "current_phase": "implementation"}, f)

    def test_hook_does_not_traceback_on_control_chars(self, tmp_path) -> None:
        envelope = _envelope_with_control_chars()
        sid = "sdd-bug-repro"
        self._seed_work_mode_cache(str(tmp_path), sid)

        env = os.environ.copy()
        env["WRIT_CACHE_DIR"] = str(tmp_path)

        # The hook tees stderr to /tmp/writ-hook-debug.log unconditionally
        # (line 12). Read pre/post deltas to scope to this run.
        debug_path = "/tmp/writ-hook-debug.log"
        pre_size = os.path.getsize(debug_path) if os.path.exists(debug_path) else 0

        result = subprocess.run(
            ["bash", HOOK],
            input=envelope,
            capture_output=True,
            text=True,
            env=env,
            timeout=10,
        )

        # Exit code is 0 -- the hook is "non-blocking" by design,
        # but the regression we're fixing is the traceback printed
        # to stderr, not the exit code.
        assert result.returncode == 0, (
            f"hook exited non-zero: rc={result.returncode} "
            f"stderr={result.stderr[:500]}"
        )

        # The fix contract: no Python traceback in stderr from THIS
        # invocation. We read the appended chunk of the debug log.
        post_size = os.path.getsize(debug_path) if os.path.exists(debug_path) else 0
        new_chunk = ""
        if post_size > pre_size:
            with open(debug_path) as f:
                f.seek(pre_size)
                new_chunk = f.read()

        assert "JSONDecodeError" not in new_chunk, (
            f"hook tracebacked on control-char envelope:\n{new_chunk[:1000]}"
        )
        assert "Traceback" not in new_chunk, (
            f"hook tracebacked on control-char envelope:\n{new_chunk[:1000]}"
        )

    def test_hook_handles_clean_envelope(self, tmp_path) -> None:
        """Sanity: a normal envelope (no control chars) still works."""
        sid = "sdd-clean"
        self._seed_work_mode_cache(str(tmp_path), sid)

        envelope = json.dumps({
            "session_id": sid,
            "tool_input": {
                "subagent_type": "writ-code-reviewer",
                "description": "Review code",
            },
        })

        env = os.environ.copy()
        env["WRIT_CACHE_DIR"] = str(tmp_path)
        result = subprocess.run(
            ["bash", HOOK],
            input=envelope,
            capture_output=True,
            text=True,
            env=env,
            timeout=10,
        )
        assert result.returncode == 0
        # On a clean envelope where review_ordering_state is empty,
        # the hook should emit a deny (because no spec-reviewer
        # completed) -- BUT only if the cache for the session has
        # mode=work. Without a seeded cache, is_work_mode bails out.
        # So for this test we don't assert on stdout content; we just
        # assert the hook didn't crash.
