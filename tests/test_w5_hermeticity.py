"""RED guard for Wave-5 Cycle 5.1 -- wipe-and-restore hermeticity contract.

Writ uses ONE shared Neo4j graph for the whole test suite. Three test files
wipe that graph (`clear_all()` / `_clear_graph()` / the raw
`MATCH (n) DETACH DELETE n` statement) but do not restore the corpus
afterward, leaking an empty (or fake-node-polluted) graph to whatever test
runs next in the same pytest process. The already-fixed model is
`_roundtrip_db` in tests/test_edge_export_roundtrip.py, whose teardown
shells `subprocess.run([*WRIT_CMD_PREFIX, "import-markdown", "bible/"], ...)`
after its own cleanup. This guard asserts the three stragglers below adopt
that same contract: each must pair its graph-wipe with a corpus-restore that
runs in teardown (after a fixture `yield`).

This guard is FULLY HERMETIC: it is a pure source-text scan. It does NOT
import, execute, or collect fixtures from any of the three target files, and
it does NOT touch Neo4j. It reads each file's text with `Path.read_text()`
and regex-searches it only.

RED today (2026-07-16, pre-implementation):
- test_export.py has `clear_all()` (wipe present) but no
  `"import-markdown", "bible/"` literal anywhere -> restore check fails.
- test_graph_proximity.py has `clear_all()` (wipe present) but no
  `"import-markdown", "bible/"` literal anywhere -> restore check fails.
- test_compress_on_ingest.py has `_clear_graph()` (wipe present) and does
  contain other `import-markdown` substrings (e.g. inside `_run_import`),
  but none form the `"import-markdown", "bible/"` adjacency this guard
  requires, AND the file has no `yield` at all today -> both the restore
  check and the teardown-ordering check fail.

All three become GREEN only once the corresponding fixture in each file
adds a `[*WRIT_CMD_PREFIX, "import-markdown", "bible/"]` subprocess restore
after a `yield`, per plan.md Cycle 5.1.
"""

from __future__ import annotations

import re
from pathlib import Path

TESTS_DIR = Path(__file__).resolve().parent

# Condition 1: a graph-wipe token is present somewhere in the file.
WIPE_RE = re.compile(r"clear_all\(\)|_clear_graph\(\)|MATCH \(n\) DETACH DELETE n")

# Condition 2: the subprocess corpus-restore literal is present -- the
# argument-list adjacency `"import-markdown", "bible/"` (or "bible", no
# trailing slash), mirroring _roundtrip_db's restore call exactly.
RESTORE_RE = re.compile(r'import-markdown"\s*,\s*"bible/?"')

# Condition 3 uses a REAL fixture `yield` (word-boundary), not the prose word
# "yields" that appears in docstrings -- `\byield\b` does not match "yields".
YIELD_RE = re.compile(r"\byield\b")


def _assert_wipe_paired_with_restore(filename: str) -> None:
    """Shared source-scan used by each per-file test below.

    Reads `filename`'s source text (never imports or executes it) and
    asserts all three hermeticity conditions:
    1. a wipe call is present,
    2. a corpus-restore literal is present, and
    3. that restore literal appears after a fixture `yield` (i.e. in
       teardown, not setup).
    """
    path = TESTS_DIR / filename
    assert path.exists(), f"expected {path} to exist"
    src = path.read_text()

    assert WIPE_RE.search(src) is not None, (
        f"{filename} must contain a graph-wipe call (clear_all() / "
        "_clear_graph() / raw 'MATCH (n) DETACH DELETE n') -- condition 1 "
        "(wipe present) failed"
    )

    restore_matches = list(RESTORE_RE.finditer(src))
    assert restore_matches, (
        f'{filename} must contain the subprocess corpus-restore literal '
        '`"import-markdown", "bible/"` (mirroring the _roundtrip_db '
        "teardown in tests/test_edge_export_roundtrip.py) somewhere after "
        "its graph-wipe -- condition 2 (restore present) failed"
    )

    # Condition 3: at least one restore literal is preceded by a REAL fixture
    # `yield`, i.e. it runs in teardown. Requiring a real yield BEFORE the
    # restore (not merely "a yield exists somewhere") rejects an unrelated
    # `import-markdown", "bible/"` that sits in a test body / CliRunner call
    # with no teardown yield ahead of it -- the exact false positive that a
    # bare `"yield" in src` substring check let through.
    restore_in_teardown = any(
        YIELD_RE.search(src[: m.start()]) for m in restore_matches
    )
    assert restore_in_teardown, (
        f"{filename}'s corpus-restore literal must appear AFTER a fixture "
        "`yield` (i.e. in teardown, not setup / test body) -- condition 3 "
        "(restore is in teardown) failed: no real `yield` precedes any "
        "`import-markdown\", \"bible/\"` literal in this file"
    )


def test_export_wipe_paired_with_restore() -> None:
    """tests/test_export.py must restore the corpus after its Neo4j wipes.

    Its two Neo4j fixtures (`TestExportWithNeo4j.db`,
    `TestExportGraphToMarkdown.live_db`) call `clear_all()` today with no
    subsequent `import-markdown bible/` restore, so this is RED until a
    module-scoped autouse teardown fixture adds the restore once per plan.md.
    """
    _assert_wipe_paired_with_restore("test_export.py")


def test_graph_proximity_wipe_paired_with_restore() -> None:
    """tests/test_graph_proximity.py's `db` fixture teardown must restore
    the corpus after its `clear_all()`.

    The module-scoped `db` fixture currently does `clear_all()` then
    `close()` with no restore, so this is RED until the subprocess
    `import-markdown bible/` restore is added to its teardown per plan.md.
    """
    _assert_wipe_paired_with_restore("test_graph_proximity.py")


def test_compress_on_ingest_wipe_paired_with_restore() -> None:
    """tests/test_compress_on_ingest.py must restore the corpus after the
    `TestImportMarkdownCompressFlag` class wipes it (and seeds fake
    Abstraction nodes).

    The file calls `_clear_graph()` at the top of each of that class's three
    tests, contains no `"import-markdown", "bible/"` adjacency, and has no
    `yield` at all today, so this is RED until a class-scoped autouse
    teardown fixture wipes-and-reimports per plan.md.
    """
    _assert_wipe_paired_with_restore("test_compress_on_ingest.py")
