"""Shared markdown-node parsing helpers for the methodology test suite (POL-2c).

The frontmatter-body regex and the lowercased read were copy-pasted into nine INC test files.
Centralized here so there is exactly one definition; each test keeps its own path / node-id
resolution and delegates the parse to these. `BODY_WORD_BUDGET` is the single source of the
concise body word budget (ENF-META-CONCISE-001) that the INC files assert against.
"""
from __future__ import annotations

import re
from pathlib import Path

_FRONTMATTER_RE = re.compile(r"^---\n.*?\n---\n(.*)$", re.S)

# Single source of the concise body word budget (ENF-META-CONCISE-001).
BODY_WORD_BUDGET = 320


def frontmatter_body(path: Path) -> str:
    """The markdown body after the YAML front matter ('' when there is no front matter)."""
    m = _FRONTMATTER_RE.match(path.read_text(encoding="utf-8"))
    return m.group(1) if m else ""


def text_lower(path: Path) -> str:
    """The whole file lowercased, for case-insensitive vocabulary assertions."""
    return path.read_text(encoding="utf-8").lower()


def word_count(text: str) -> int:
    """Whitespace-delimited word count (for ENF-META-CONCISE-001 body budgets)."""
    return len(text.split())
