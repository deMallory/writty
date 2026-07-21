"""POL-5b-fix: hooks must not crash on a no-match grep under set -euo pipefail.

`VAR=$(echo "$X" | grep "^WRIT_META:" ...)` propagates grep's exit 1 when nothing
matches; under set -euo pipefail that aborts the hook with no stderr (the live
"UserPromptSubmit hook error -- non-blocking status code: No stderr output").
The fix: such grep substitutions must end in `|| true` (the empty result the
downstream code already expects).

Static guard (deterministic RED->GREEN) + behavioral empty-rules survival.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
from pathlib import Path

import pytest

SKILL_DIR = Path.home() / ".claude/skills/writ"
HOOKS_DIR = SKILL_DIR / "hooks" / "scripts"
RAG_INJECT = HOOKS_DIR / "writ-rag-inject.sh"

# An assignment whose command substitution greps for the WRIT_META / parse_error
# markers -- these select-or-nothing greps exit 1 on no-match and crash the hook.
_RISKY = re.compile(r'=\$\(.*\bgrep\b.*(\^WRIT_META:|\^parse_error:)')
_GUARDED = ("|| true", "|| echo")


def _set_e_hooks() -> list[Path]:
    out = []
    for sh in sorted(HOOKS_DIR.glob("*.sh")):
        text = sh.read_text()
        if "set -euo pipefail" in text or re.search(r"^\s*set -e", text, re.M):
            out.append(sh)
    return out


def _risky_unguarded_lines(path: Path) -> list[tuple[int, str]]:
    bad = []
    for i, line in enumerate(path.read_text().splitlines(), 1):
        if _RISKY.search(line) and not any(g in line for g in _GUARDED):
            bad.append((i, line.strip()))
    return bad


# --------------------------------------------------------------------------- #
# 1. Static guard -- the RED->GREEN driver + permanent lock-in
# --------------------------------------------------------------------------- #
class TestNoUnguardedMarkerGrep:
    def test_no_unguarded_grep_in_any_set_e_hook(self) -> None:
        offenders: dict[str, list[tuple[int, str]]] = {}
        for sh in _set_e_hooks():
            bad = _risky_unguarded_lines(sh)
            if bad:
                offenders[sh.name] = bad
        assert not offenders, (
            "WRIT_META/parse_error grep substitutions without `|| true` crash the hook "
            f"on no-match under set -euo pipefail:\n{json.dumps(offenders, indent=2)}"
        )

    @pytest.mark.parametrize(
        "hook",
        [
            "writ-rag-inject.sh",
            "writ-posttool-rag.sh",
            "writ-read-rag.sh",
            "writ-subagent-start.sh",
        ],
    )
    def test_named_hook_has_no_unguarded_grep(self, hook: str) -> None:
        bad = _risky_unguarded_lines(HOOKS_DIR / hook)
        assert not bad, f"{hook} still has unguarded marker grep(s): {bad}"


# --------------------------------------------------------------------------- #
# 2. Behavioral -- empty-rules path must exit 0, not crash
# --------------------------------------------------------------------------- #
class TestEmptyRulesSurvival:
    def test_rag_inject_exits_zero_on_no_match_prompt(self) -> None:
        """A nonsense prompt returns zero rules; the hook must exit 0, not 1."""
        envelope = json.dumps({
            "session_id": "test-pol5b-fix-empty",
            "hook_event_name": "UserPromptSubmit",
            "prompt": "zzqqx_nomatch_token_9173_qpzlk",
            "cwd": str(SKILL_DIR),
            "transcript_path": "/tmp/pol5b-fix-x.jsonl",
        })
        result = subprocess.run(
            ["bash", str(RAG_INJECT)],
            input=envelope,
            capture_output=True, text=True,
            cwd=str(SKILL_DIR),
            env={**os.environ, "WRIT_HOST": "localhost"},
            timeout=15,
        )
        assert result.returncode == 0, (
            f"writ-rag-inject.sh crashed on the empty-rules path (rc={result.returncode}); "
            f"stderr={result.stderr[:300]!r}"
        )
