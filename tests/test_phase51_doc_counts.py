"""Phase 5.1: doc-count regression gate.

A pure (no-Neo4j) test that derives each STABLE count from SOURCE and asserts the
docs contain that number on the specific claim line via narrowly anchored regexes.

Six source-derived counts:
  node types  -- len(NODE_ID_FIELDS)  == 13
  edge types  -- len(ALLOWED_EDGE_TYPES) == 17
  modes       -- len(MODE_CONFIG)     == 5
  roles       -- glob '.claude/agents/writ-*.md' == 5
  hooks       -- json.load hooks/hooks.json, count "command" leaves == 41
  endpoints   -- regex @app/@router route decorators across writ/server/**.py == 45

RED-on-current-code: ARCHITECTURE.md says "38 endpoints" (source=41) and
HANDBOOK.md says "34 hook scripts" (source=35). After the 1a doc edits those two
go GREEN and future drift re-reds them. The import-derived counts (node types, edge
types, modes) never skip.

Change C retired APPLIES_TO and JUSTIFIED_BY (19 -> 17); later features added
edge types, so ALLOWED_EDGE_TYPES now holds 24. test_edge_types_source_count
and test_edge_types_in_readme pin that count against README.md.

W2 (server package split, branch refactor/w2-server-split): writ/server.py
becomes a writ/server/ package (routes/*.py + models.py + __init__.py facade).
`_count_server_endpoints` reads via `writ_server_source()` (tests/conftest.py),
which is layout-agnostic: it concatenates every *.py under writ/server/ if that
directory exists (post-split), else falls back to the single writ/server.py file
(pre-split). It also now matches BOTH `@app.<verb>` and `@router.<verb>` decorators,
since post-split every route decorator is `@router.<verb>` inside routes/*.py and
none remain in the __init__.py facade. The true count (45) does not change across
the split -- only its file location and decorator prefix do. This also fixes the
pre-existing drift where the hardcoded expected count (42) had fallen behind the
actual decorator count in the single file (45), which was failing independently of
this refactor.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from writ.graph.db import ALLOWED_EDGE_TYPES
from writ.graph.schema import NODE_ID_FIELDS
from writ.session.mode_engine import MODE_CONFIG

from tests.conftest import writ_server_source

# ---------------------------------------------------------------------------
# Repo paths
# ---------------------------------------------------------------------------
REPO_ROOT = Path(__file__).resolve().parent.parent
ARCHITECTURE_MD = REPO_ROOT / "docs" / "ARCHITECTURE.md"
HANDBOOK_MD = REPO_ROOT / "HANDBOOK.md"
README_MD = REPO_ROOT / "README.md"
HOOKS_JSON = REPO_ROOT / "hooks" / "hooks.json"
AGENTS_DIR = Path.home() / ".claude" / "agents"

# ---------------------------------------------------------------------------
# Anchored regex patterns (test owns these as constants per plan §1c)
# ---------------------------------------------------------------------------
RE_ARCH_ENDPOINTS_PROSE = re.compile(r"\*\*(\d+) endpoints\*\*")
# Matches the grep-command verification comment on line 349: "# 38" -> "# 41"
RE_ARCH_ENDPOINTS_COMMENT = re.compile(r"server\.py\s+#\s*(\d+)")
RE_HANDBOOK_HOOKS = re.compile(r"registers \*\*(\d+) hook scripts\*\*")
RE_HANDBOOK_NODE_TYPES = re.compile(r"\*\*(\d+) node types\*\*")
RE_README_NODE_TYPES = re.compile(r"\*\*(\d+) node types\*\*")
RE_README_EDGE_TYPES = re.compile(r"\*\*(\d+) edge types\*\*")


# ---------------------------------------------------------------------------
# Source-derived counts (computed once at import time -- always run, never skip)
# ---------------------------------------------------------------------------
SOURCE_NODE_TYPE_COUNT: int = len(NODE_ID_FIELDS)
SOURCE_EDGE_TYPE_COUNT: int = len(ALLOWED_EDGE_TYPES)
SOURCE_MODE_COUNT: int = len(MODE_CONFIG)


def _count_hooks_json_entries() -> int:
    """Count JSON objects that carry a 'command' key in hooks/hooks.json."""
    data = json.loads(HOOKS_JSON.read_text(encoding="utf-8"))
    # The file is a list of objects, each representing one hook registration.
    # Count entries with a "command" key (leaf hook objects).
    if isinstance(data, list):
        return sum(1 for entry in data if "command" in entry)
    # Nested format: {event: [{command: ...}, ...], ...}
    count = 0
    def _walk(obj):
        nonlocal count
        if isinstance(obj, dict):
            if "command" in obj:
                count += 1
            else:
                for v in obj.values():
                    _walk(v)
        elif isinstance(obj, list):
            for item in obj:
                _walk(item)
    _walk(data)
    return count


def _count_server_endpoints() -> int:
    """Count `@app.<verb>` and `@router.<verb>` route decorators across the
    writ.server module/package (layout-agnostic; see writ_server_source())."""
    text = writ_server_source()
    return len(re.findall(r"^@(?:app|router)\.(get|post|put|delete|patch)", text, re.MULTILINE))


def _count_role_files() -> int | None:
    """Count writ-*.md files in ~/.claude/agents. Returns None if dir absent."""
    if not AGENTS_DIR.exists():
        return None
    return len(list(AGENTS_DIR.glob("writ-*.md")))


def _first_match_int(pattern: re.Pattern, text: str) -> int | None:
    m = pattern.search(text)
    return int(m.group(1)) if m else None


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestDocCounts:
    """Regression gate: each stable count derived from source must match the doc claim."""

    # --- node types ---------------------------------------------------------

    def test_node_types_source_count(self) -> None:
        assert SOURCE_NODE_TYPE_COUNT == 13, (
            f"NODE_ID_FIELDS has {SOURCE_NODE_TYPE_COUNT} entries; "
            "update this test and the docs if the schema changed"
        )

    def test_node_types_in_handbook(self) -> None:
        text = HANDBOOK_MD.read_text(encoding="utf-8")
        doc_count = _first_match_int(RE_HANDBOOK_NODE_TYPES, text)
        assert doc_count is not None, (
            f"HANDBOOK.md: regex {RE_HANDBOOK_NODE_TYPES.pattern!r} found no match; "
            "claim line may have changed wording"
        )
        assert doc_count == SOURCE_NODE_TYPE_COUNT, (
            f"HANDBOOK.md claims {doc_count} node types but NODE_ID_FIELDS has "
            f"{SOURCE_NODE_TYPE_COUNT}"
        )

    def test_node_types_in_readme(self) -> None:
        text = README_MD.read_text(encoding="utf-8")
        doc_count = _first_match_int(RE_README_NODE_TYPES, text)
        assert doc_count is not None, (
            f"README.md: regex {RE_README_NODE_TYPES.pattern!r} found no match"
        )
        assert doc_count == SOURCE_NODE_TYPE_COUNT, (
            f"README.md claims {doc_count} node types but NODE_ID_FIELDS has "
            f"{SOURCE_NODE_TYPE_COUNT}"
        )

    # --- edge types ---------------------------------------------------------

    def test_edge_types_source_count(self) -> None:
        # APPLIES_TO and JUSTIFIED_BY were retired (19 -> 17); later features
        # added edge types, so the current source-of-truth count is 24.
        assert SOURCE_EDGE_TYPE_COUNT == 24, (
            f"ALLOWED_EDGE_TYPES has {SOURCE_EDGE_TYPE_COUNT} entries; expected 24. "
            "If this changed, update writ/graph/db/_common.py ALLOWED_EDGE_TYPES "
            "and the README edge-type count."
        )

    def test_edge_types_in_readme(self) -> None:
        text = README_MD.read_text(encoding="utf-8")
        doc_count = _first_match_int(RE_README_EDGE_TYPES, text)
        assert doc_count is not None, (
            f"README.md: regex {RE_README_EDGE_TYPES.pattern!r} found no match"
        )
        assert doc_count == SOURCE_EDGE_TYPE_COUNT, (
            f"README.md claims {doc_count} edge types but ALLOWED_EDGE_TYPES has "
            f"{SOURCE_EDGE_TYPE_COUNT}"
        )

    # --- modes --------------------------------------------------------------

    def test_modes_source_count(self) -> None:
        assert SOURCE_MODE_COUNT == 5, (
            f"MODE_CONFIG has {SOURCE_MODE_COUNT} entries; "
            "update this test if a mode was added or removed"
        )

    def test_all_mode_names_importable(self) -> None:
        expected_names = {"work", "debug", "review", "conversation", "investigate"}
        assert set(MODE_CONFIG.keys()) == expected_names, (
            f"MODE_CONFIG keys differ: got {set(MODE_CONFIG.keys())}"
        )

    # --- hooks --------------------------------------------------------------

    def test_hooks_json_entry_count(self) -> None:
        source_count = _count_hooks_json_entries()
        assert source_count == 41, (
            f"hooks/hooks.json has {source_count} 'command' entries; expected 41. "
            "Bump this (and HANDBOOK 'registers **N hook scripts**') when adding or "
            "removing a registration."
        )

    def test_hooks_count_in_handbook(self) -> None:
        # HANDBOOK's 'registers **N hook scripts**' must match the hooks.json count.
        source_count = _count_hooks_json_entries()
        text = HANDBOOK_MD.read_text(encoding="utf-8")
        doc_count = _first_match_int(RE_HANDBOOK_HOOKS, text)
        assert doc_count is not None, (
            f"HANDBOOK.md: regex {RE_HANDBOOK_HOOKS.pattern!r} found no match; "
            "claim line may have changed wording"
        )
        assert doc_count == source_count, (
            f"HANDBOOK.md:277 claims {doc_count} hook scripts but "
            f"hooks/hooks.json has {source_count} command entries"
        )

    # --- endpoints ----------------------------------------------------------

    def test_server_endpoint_count(self) -> None:
        # W2 split: source_count is derived from writ_server_source(), which scans
        # writ/server/**/*.py post-split or the single writ/server.py pre-split, and
        # matches both @app.<verb> and @router.<verb> decorators. The true count (45)
        # is unchanged by the split -- only file location/decorator prefix change.
        # Bump this (and ARCHITECTURE.md's prose + grep-comment count) together when
        # adding/removing a route.
        source_count = _count_server_endpoints()
        assert source_count == 45, (
            f"writ.server has {source_count} @app/@router route decorators; expected 45"
        )

    def test_endpoint_count_prose_in_architecture(self) -> None:
        source_count = _count_server_endpoints()
        text = ARCHITECTURE_MD.read_text(encoding="utf-8")
        doc_count = _first_match_int(RE_ARCH_ENDPOINTS_PROSE, text)
        assert doc_count is not None, (
            f"ARCHITECTURE.md: regex {RE_ARCH_ENDPOINTS_PROSE.pattern!r} found no match; "
            "claim line may have changed wording"
        )
        assert doc_count == source_count, (
            f"ARCHITECTURE.md claims {doc_count} endpoints (prose) but "
            f"writ.server has {source_count} @app/@router route decorators"
        )

    def test_endpoint_count_comment_in_architecture(self) -> None:
        source_count = _count_server_endpoints()
        text = ARCHITECTURE_MD.read_text(encoding="utf-8")
        doc_count = _first_match_int(RE_ARCH_ENDPOINTS_COMMENT, text)
        assert doc_count is not None, (
            f"ARCHITECTURE.md: regex {RE_ARCH_ENDPOINTS_COMMENT.pattern!r} found no match; "
            "grep-command comment may have changed"
        )
        assert doc_count == source_count, (
            f"ARCHITECTURE.md grep comment claims {doc_count} endpoints but "
            f"writ.server has {source_count} @app/@router route decorators"
        )
