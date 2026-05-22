"""Hook stderr surfacing -- replace 2>/dev/null with $WRIT_HOOK_LOG.

Context: the legacy-cache KeyError went undetected for an entire session
because writ-rag-inject.sh and writ-posttool-rag.sh swallowed stderr from
the mutating `_writ_session update` calls. These tests pin the new
contract: stderr from those calls must reach a hook log file, not /dev/null.

We can't easily test the bash redirection itself, so we test the
underlying capability: WRIT_HOOK_LOG exists as a documented contract via a
helper, and the hook scripts reference it instead of /dev/null on the
mutating call sites.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys

import pytest
from pathlib import Path

SKILL_DIR = str(Path.home() / ".claude/skills/writ")
INJECT_HOOK = f"{SKILL_DIR}/.claude/hooks/writ-rag-inject.sh"
POSTTOOL_HOOK = f"{SKILL_DIR}/.claude/hooks/writ-posttool-rag.sh"


class TestHookStderrLogging:
    """The mutating writ-session.py calls AND friction-log emit blocks
    inside the hooks must redirect stderr to $WRIT_HOOK_LOG (default
    /tmp/writ-hooks.log), not /dev/null.

    We grep the hook scripts for the call sites and assert they reference
    the env var rather than /dev/null. This is a structural test -- it
    catches regressions where someone reverts the redirection.
    """

    def _friction_emit_blocks(self, body: str) -> list[str]:
        """Find inline `python3 -c "..."` blocks that conclude with the
        argv list + redirect; pick out the redirect tail (last 80 chars
        of the line that closes with `|| true`)."""
        import re
        # Match terminal lines that look like `" args 2>... || true`
        return re.findall(
            r'^"\s+"[^"\n]*"\s*(?:"[^"\n]*"\s*)*2>[^\n]+\|\|\s*true',
            body,
            re.MULTILINE,
        )

    def _read(self, path: str) -> str:
        with open(path) as f:
            return f.read()

    def _mutating_update_blocks(self, body: str) -> list[str]:
        """Extract each `_writ_session update ... || true` block, joining
        bash line-continuations so the regex over multi-line commands."""
        # Collapse `\` + newline into a single space so we can match
        # multi-line update calls as single logical lines.
        joined = re.sub(r"\\\n\s*", " ", body)
        return re.findall(
            r"_writ_session update[^\n]*?--add-(?:rules|rule-objects|always-on-tokens)[^\n]*",
            joined,
        )

    def test_inject_hook_mutating_update_uses_writ_hook_log(self) -> None:
        body = self._read(INJECT_HOOK)
        blocks = self._mutating_update_blocks(body)
        assert blocks, "expected at least one mutating update call in inject hook"
        bad = [b for b in blocks if "WRIT_HOOK_LOG" not in b and "writ-hooks.log" not in b]
        assert not bad, (
            f"mutating update(s) missing WRIT_HOOK_LOG redirect:\n"
            + "\n".join(b[:240] for b in bad)
        )
        # Defense-in-depth: assert NO mutating update still ends in 2>/dev/null
        legacy = [b for b in blocks if "2>/dev/null" in b]
        assert not legacy, (
            f"mutating update still uses 2>/dev/null:\n"
            + "\n".join(b[:240] for b in legacy)
        )

    def test_posttool_hook_mutating_update_uses_writ_hook_log(self) -> None:
        body = self._read(POSTTOOL_HOOK)
        blocks = self._mutating_update_blocks(body)
        assert blocks, "expected at least one mutating update call in posttool hook"
        bad = [b for b in blocks if "WRIT_HOOK_LOG" not in b and "writ-hooks.log" not in b]
        assert not bad, (
            f"mutating update(s) missing WRIT_HOOK_LOG redirect:\n"
            + "\n".join(b[:240] for b in bad)
        )
        legacy = [b for b in blocks if "2>/dev/null" in b]
        assert not legacy, (
            f"mutating update still uses 2>/dev/null:\n"
            + "\n".join(b[:240] for b in legacy)
        )

    def test_friction_emit_blocks_use_writ_hook_log(self) -> None:
        """The python3 -c blocks that emit friction events / write
        cache files must redirect stderr to WRIT_HOOK_LOG too. Catch
        regressions where a new emit slips in with 2>/dev/null."""
        for path in (INJECT_HOOK, POSTTOOL_HOOK):
            body = self._read(path)
            blocks = self._friction_emit_blocks(body)
            for b in blocks:
                # Each tail line must redirect to WRIT_HOOK_LOG, not /dev/null.
                assert "WRIT_HOOK_LOG" in b or "writ-hooks.log" in b, (
                    f"friction-emit/cache-write block in {path} still uses /dev/null:\n{b}"
                )

    def test_writ_session_update_failure_writes_to_hook_log(
        self, tmp_path
    ) -> None:
        """End-to-end: when writ-session.py update raises, the redirect
        target receives the stderr content."""
        log_path = tmp_path / "writ-hooks.log"
        env = os.environ.copy()
        env["WRIT_CACHE_DIR"] = str(tmp_path)

        # Trigger an error: invalid JSON to --add-rules forces a failure path.
        proc = subprocess.run(
            [
                "bash",
                "-c",
                f'python3 {SKILL_DIR}/bin/lib/writ-session.py update bogus-sid '
                f'--add-rules "not-a-json-array" 2>>"{log_path}" || true',
            ],
            capture_output=True,
            text=True,
            env=env,
        )
        assert log_path.exists(), "log path was not created by the redirect"
        content = log_path.read_text()
        assert content.strip(), (
            f"hook log is empty -- redirect did not capture stderr "
            f"(stdout={proc.stdout!r}, stderr={proc.stderr!r})"
        )
