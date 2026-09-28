"""Pins the workflows pages to the code they describe.

The structure checks see shape only. These read the code each page summarizes, so a
renamed mode, a new agent file or a matcher change fails here instead of leaving a page
that reads right and is wrong. The step 1 draft said "approuvé" was refused; the matcher
accepts it. The approval table below is executed so that cannot happen again.

Files only, like test_structure.py:

    python -m pytest --noconftest tests/openwiki -q
"""

from __future__ import annotations

import ast
import os
import re
import sys

from tests.openwiki.test_structure import REPO_ROOT, WIKI_ROOT

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "bin", "lib"))

from approval_match import classify  # noqa: E402

WORKFLOWS = WIKI_ROOT / "workflows"
# The Result column of the approval table names the matcher's tier in plain words.
RESULT_TO_TIER = {"advances": "exact", "asks": "embedded", "nothing": "none"}
_BACKTICK = re.compile(r"`([^`\n]+)`")


def _page(name: str) -> str:
    return (WORKFLOWS / name).read_text(encoding="utf-8")


def _backticked(name: str) -> set[str]:
    return set(_BACKTICK.findall(_page(name)))


def _mode_config() -> dict:
    """MODE_CONFIG as a literal, read without importing the writ package (no Neo4j deps)."""
    source = (REPO_ROOT / "writ/session/mode_engine.py").read_text(encoding="utf-8")
    for node in ast.parse(source).body:
        if isinstance(node, ast.AnnAssign) and getattr(node.target, "id", None) == "MODE_CONFIG":
            return ast.literal_eval(node.value)
    raise AssertionError("MODE_CONFIG not found in writ/session/mode_engine.py")


def _agent_names() -> list[str]:
    names = []
    for path in sorted((REPO_ROOT / "agents").glob("*.md")):
        match = re.search(r"^name:\s*(\S+)", path.read_text(encoding="utf-8"), re.MULTILINE)
        names.append(match.group(1) if match else path.stem)
    return names


def _approval_rows() -> list[tuple[str, str]]:
    """(typed text, result word) for each body row of the `| You type | Result |` table."""
    rows: list[tuple[str, str]] = []
    in_table = False
    for line in _page("work-gates.md").split("\n"):
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if cells[:2] == ["You type", "Result"]:
            in_table = True
        elif in_table and not line.startswith("|"):
            break
        elif in_table and not set(cells[0]) <= set("-: "):
            rows.append((cells[0].strip("`"), cells[1].lower()))
    return rows


def test_the_modes_page_names_every_mode():
    missing = sorted(set(_mode_config()) - _backticked("modes.md"))
    assert missing == []


def test_the_work_gates_page_names_every_phase_and_gate():
    work = _mode_config()["work"]
    names = {work["initial_phase"], *work["gate_sequence"], *work["phase_after_gate"].values()}
    text = _page("work-gates.md")
    assert sorted(n for n in names if n not in text) == []


def test_the_sub_agents_page_names_every_agent_file():
    listed = _backticked("sub-agents.md")
    assert [n for n in _agent_names() if n not in listed] == []


def test_the_approval_examples_match_the_matcher():
    rows = _approval_rows()
    assert "approuvé" in [typed for typed, _ in rows]
    # The hook lowercases the prompt before matching; do the same.
    wrong = [
        f"{typed!r}: page says {result}, matcher gives {classify(typed.lower())}"
        for typed, result in rows
        if RESULT_TO_TIER.get(result) != classify(typed.lower())
    ]
    assert wrong == []
