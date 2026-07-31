"""The test suite must not hardcode where Writ is installed.

48 test files located the repo as `Path.home() / ".claude/skills/writ"`, so the suite only
ran from that one location: a checkout at /opt/writ or in a second worktree found no
scripts, no hooks and no bin/lib, and the failures pointed at missing files rather than at
the assumption. Runtime code was already path-agnostic (hooks use ${CLAUDE_PLUGIN_ROOT},
common.sh resolves from ${BASH_SOURCE}, the log and session roots derive from the package
root), so the suite was the last thing pinning the install location.

Tests now derive the repo from their own file: `Path(__file__).resolve().parent.parent`.
This guard fails if the home-relative form returns, and it fails wherever the suite is run
from, because it reasons about source text rather than about this machine (where the two
happen to resolve to the same path, which is exactly why a broken assumption here is
invisible until someone relocates).
"""
from __future__ import annotations

import re
from pathlib import Path

TESTS_DIR = Path(__file__).resolve().parent
SELF = Path(__file__).name

# `Path.home() / ".claude/skills/writ..."` in any spacing, and the os.path equivalent.
_HARDCODED = re.compile(
    r'Path\.home\(\)\s*/\s*"\.claude/skills/writ'
    r'|expanduser\(\s*["\']~/\.claude/skills/writ'
    r'|Path\.home\(\)\s*/\s*"\.claude"\s*/\s*"skills"'
)


def _offenders() -> list[str]:
    out = []
    for path in sorted(TESTS_DIR.glob("*.py")):
        if path.name == SELF:
            continue
        for lineno, line in enumerate(path.read_text().splitlines(), 1):
            if _HARDCODED.search(line):
                out.append(f"{path.name}:{lineno}: {line.strip()}")
    return out


def test_no_test_locates_the_repo_via_home() -> None:
    offenders = _offenders()
    assert offenders == [], (
        "these tests pin the install location; derive the repo from the test file instead "
        "(Path(__file__).resolve().parent.parent):\n  " + "\n  ".join(offenders)
    )


def test_the_guard_actually_matches_the_old_form() -> None:
    """Prove the detector has teeth, so a green result means clean and not broken regex."""
    for sample in (
        'SKILL_DIR = Path.home() / ".claude/skills/writ"',
        'SKILL_DIR = str(Path.home() / ".claude/skills/writ/bin/lib/common.sh")',
        'SKILL_DIR = Path.home()/".claude/skills/writ"',
        'D = os.path.expanduser("~/.claude/skills/writ")',
    ):
        assert _HARDCODED.search(sample), f"guard failed to flag: {sample}"


def test_genuine_home_references_are_not_flagged() -> None:
    """`~/.claude` itself is a real location (global settings, installed commands).

    Only locating the REPO via home is wrong; asserting on the user's actual Claude Code
    config directory is correct and must keep working.
    """
    for sample in (
        'GLOBAL_SETTINGS = Path.home() / ".claude" / "settings.json"',
        'INSTALLED = Path.home() / ".claude" / "commands" / "writ-approve.md"',
        'assert result != Path.home() / ".claude" / "writ" / "logs"',
    ):
        assert not _HARDCODED.search(sample), f"guard wrongly flagged: {sample}"
