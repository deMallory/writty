"""RED guard for Wave-5 Cycle 5.3c -- consolidate the four remaining
duplicated test-fixture families: the word-budget constant/idiom, the
session_id/project_root/_call_can_write trio, the _collect_all_commands
re-implementation, and the token-audit helper pair.

Per plan.md Cycle 5.3c, this cycle:
1. adds `BODY_WORD_BUDGET = 320` to `tests/fixtures/md_helpers.py` as the
   single source of the concise body budget, and routes all nine INC files'
   word counts through the existing shared `word_count()` helper (dropping
   the five local `BODY_WORD_BUDGET = 320` defs in inc3/inc4/inc5/inc9/inc12);
2. creates `tests/fixtures/session_state.py` with shared `session_id` /
   `project_root` fixtures and a `call_can_write` helper, imported by
   `test_mode_infrastructure.py` and `test_phase3_centralization.py` in place
   of their local `project_root`/`session_id` defs;
3. rewrites `_collect_all_commands` in `tests/plugin/test_hooks_routing.py`
   to delegate to `_collect_event_commands` per event, instead of
   re-implementing the same per-entry walk; and
4. creates `tests/fixtures/token_audit_helpers.py` with a parametrized
   `load_token_audit(force_reimport=False)` loader, a superset `usage(...)`
   builder, and `write_transcript(...)`, imported by `test_token_audit.py`
   and `test_token_audit_prevented.py` in place of their local `_ta`/`_usage`
   copies.

This guard is FULLY HERMETIC:
- The behavioral tests (items 1, 2, 4) exercise only the new fixture
  modules in-process (module import + attribute/callable checks; no
  daemon, no Neo4j, no HTTP, no subprocess).
- All source-scan tests are pure source-text reads (`Path.read_text()` +
  substring/count checks). They do NOT import, execute, or collect
  fixtures from any target file, matching the idiom in
  tests/test_w5_free_port.py and tests/test_w5_decision_memory_fixtures.py.

CRITICAL COLLECTION NOTE: `tests/fixtures/session_state.py` and
`tests/fixtures/token_audit_helpers.py` do not exist yet, and
`BODY_WORD_BUDGET` is not yet defined in `tests/fixtures/md_helpers.py`.
Every import of those symbols is done LOCALLY (inside the test function
that needs it), never at module scope -- a module-level import would raise
ImportError during test COLLECTION and break every other test in this
file. Importing locally means only that one test errors/fails RED while
every other test in this file still collects and runs normally.

RED today (2026-07-16, pre-implementation):
- `test_body_word_budget_and_word_count_shared` fails (ImportError) --
  `BODY_WORD_BUDGET` is not yet defined in `tests/fixtures/md_helpers.py`.
- All nine `test_incN_uses_shared_word_count` source-scan tests fail --
  none of the nine INC files reference `word_count` yet (they all still
  inline `len(_body(...).split())`).
- The five `test_incN_no_longer_defines_local_budget_const` source-scan
  tests fail -- inc3/inc4/inc5/inc9/inc12 still each define a local
  `BODY_WORD_BUDGET = 320`.
- `test_session_state_module_importable` fails (ImportError) --
  `tests/fixtures/session_state.py` does not exist.
- `test_mode_infrastructure_imports_shared_session_state` and
  `test_phase3_centralization_imports_shared_session_state` fail -- neither
  file imports `tests.fixtures.session_state` yet, and both still define
  `def project_root` locally.
- `test_collect_all_commands_delegates` fails -- `_collect_all_commands`'s
  own body (the source slice between its `def` and the following
  `def _collect_event_commands`) does not call `_collect_event_commands(`
  today; it re-implements the per-entry walk inline instead. (Note: the
  file already contains two OTHER, unrelated call sites of
  `_collect_event_commands` inside other test methods -- a naive whole-file
  occurrence count would false-pass, so this test slices out
  `_collect_all_commands`'s own body specifically.)
- `test_token_audit_helpers_importable` fails (ImportError) --
  `tests/fixtures/token_audit_helpers.py` does not exist.
- `test_token_audit_imports_shared_helpers` and
  `test_token_audit_prevented_imports_shared_helpers` fail -- neither file
  imports `tests.fixtures.token_audit_helpers` yet, and both still define
  `def _usage` locally.

All twenty-two become GREEN only once the fixture modules are created and
all target files are migrated per plan.md Cycle 5.3c.
"""

from __future__ import annotations

from pathlib import Path

import pytest

TESTS_DIR = Path(__file__).resolve().parent


def _read_target(*parts: str) -> str:
    """Resolve and read a target file's source text relative to `tests/`.

    `parts` are joined onto `TESTS_DIR` (e.g. `_read_target("test_foo.py")`
    or `_read_target("plugin", "test_bar.py")`). Asserts the file exists
    first so a missing target fails loudly with a clear path rather than a
    confusing FileNotFoundError deep in `read_text()`.
    """
    path = TESTS_DIR.joinpath(*parts)
    assert path.exists(), f"expected {path} to exist"
    return path.read_text()


# ---------------------------------------------------------------------------
# Item 1 -- shared BODY_WORD_BUDGET constant + word_count() idiom.
# ---------------------------------------------------------------------------


def test_body_word_budget_and_word_count_shared() -> None:
    """`tests.fixtures.md_helpers` exports `BODY_WORD_BUDGET == 320` and the
    existing `word_count()` helper does a plain whitespace word count.

    Imported LOCALLY so this is the only test that errors/fails while
    `BODY_WORD_BUDGET` is absent from `tests/fixtures/md_helpers.py`. RED
    now (the constant doesn't exist yet); GREEN once it is added per
    plan.md Item 1.
    """
    from tests.fixtures.md_helpers import BODY_WORD_BUDGET, word_count

    assert BODY_WORD_BUDGET == 320, (
        f"tests.fixtures.md_helpers.BODY_WORD_BUDGET must equal 320 (the "
        f"single source of the concise body budget), got {BODY_WORD_BUDGET!r}"
    )
    assert word_count("a b c") == 3, (
        "tests.fixtures.md_helpers.word_count must do a plain "
        f"whitespace-delimited word count; word_count('a b c') returned "
        f"{word_count('a b c')!r}, expected 3"
    )


_WORD_BUDGET_FILES = [
    "test_inc3_authoring_uplift.py",
    "test_inc4_phase_model.py",
    "test_inc5_investigate_engine.py",
    "test_inc9_receiving_review.py",
    "test_inc12_verify_parallel.py",
    "test_inc10_worktree.py",
    "test_inc7_tdd_design.py",
    "test_inc8_planning.py",
    "test_inc11_methodology_check.py",
]

# The subset of the above that also defined a local `BODY_WORD_BUDGET = 320`
# constant (inc10/inc7/inc8/inc11 keep per-type BUDGET maps instead and never
# defined this local constant, so they are excluded from this sub-check).
_LOCAL_BUDGET_CONST_FILES = [
    "test_inc3_authoring_uplift.py",
    "test_inc4_phase_model.py",
    "test_inc5_investigate_engine.py",
    "test_inc9_receiving_review.py",
    "test_inc12_verify_parallel.py",
]


@pytest.mark.parametrize("filename", _WORD_BUDGET_FILES)
def test_incN_uses_shared_word_count(filename: str) -> None:
    """Every word-budget INC file imports the shared `md_helpers` module and
    routes its body word count through the shared `word_count()` helper
    (no remaining inline `len(_body(...).split())` idiom).
    """
    src = _read_target(filename)

    assert "tests.fixtures.md_helpers" in src, (
        f"{filename} must import from `tests.fixtures.md_helpers` -- no "
        "reference to `tests.fixtures.md_helpers` was found"
    )
    assert "word_count" in src, (
        f"{filename} must route its body word count through the shared "
        "`tests.fixtures.md_helpers.word_count()` helper -- no reference "
        "to `word_count` was found (Wave-5 Cycle 5.3c Item 1)"
    )


@pytest.mark.parametrize("filename", _LOCAL_BUDGET_CONST_FILES)
def test_incN_no_longer_defines_local_budget_const(filename: str) -> None:
    """The five INC files that previously defined a local
    `BODY_WORD_BUDGET = 320` constant no longer do so -- they reference the
    shared constant from `tests.fixtures.md_helpers` instead.
    """
    src = _read_target(filename)

    assert "BODY_WORD_BUDGET = 320" not in src, (
        f"{filename} must no longer define a local `BODY_WORD_BUDGET = 320` "
        "-- it must import the shared constant from "
        "`tests.fixtures.md_helpers` instead (Wave-5 Cycle 5.3c Item 1)"
    )


# ---------------------------------------------------------------------------
# Item 2 -- shared session_id / project_root / call_can_write.
# ---------------------------------------------------------------------------


def test_session_state_module_importable() -> None:
    """`tests.fixtures.session_state` exposes `session_id`, `project_root`,
    and `call_can_write` as usable objects (the first two as pytest
    fixture functions, the last as a plain callable helper).

    Imported LOCALLY so this is the only test that errors/fails while
    `tests/fixtures/session_state.py` is absent. RED now (module doesn't
    exist); GREEN once it is created per plan.md Item 2.
    """
    from tests.fixtures.session_state import call_can_write, project_root, session_id

    assert callable(session_id), (
        "tests.fixtures.session_state.session_id must be a callable pytest "
        "fixture function"
    )
    assert callable(project_root), (
        "tests.fixtures.session_state.project_root must be a callable "
        "pytest fixture function"
    )
    assert callable(call_can_write), (
        "tests.fixtures.session_state.call_can_write must be a callable "
        "helper function"
    )


def test_mode_infrastructure_imports_shared_session_state() -> None:
    """tests/test_mode_infrastructure.py must import `session_id` /
    `project_root` from the shared `tests.fixtures.session_state` module
    and no longer define its own `project_root` fixture.
    """
    src = _read_target("test_mode_infrastructure.py")

    assert "tests.fixtures.session_state" in src, (
        "test_mode_infrastructure.py must import the shared fixtures via "
        "`from tests.fixtures.session_state import session_id, "
        "project_root` -- no reference to `tests.fixtures.session_state` "
        "was found"
    )
    assert "def project_root" not in src, (
        "test_mode_infrastructure.py must no longer define a local "
        "`project_root` fixture -- it is replaced by the shared copy in "
        "tests/fixtures/session_state.py (Wave-5 Cycle 5.3c Item 2)"
    )


def test_phase3_centralization_imports_shared_session_state() -> None:
    """tests/test_phase3_centralization.py must import `session_id` /
    `project_root` from the shared `tests.fixtures.session_state` module
    and no longer define its own `project_root` fixture.
    """
    src = _read_target("test_phase3_centralization.py")

    assert "tests.fixtures.session_state" in src, (
        "test_phase3_centralization.py must import the shared fixtures via "
        "`from tests.fixtures.session_state import session_id, "
        "project_root` -- no reference to `tests.fixtures.session_state` "
        "was found"
    )
    assert "def project_root" not in src, (
        "test_phase3_centralization.py must no longer define a local "
        "`project_root` fixture -- it is replaced by the shared copy in "
        "tests/fixtures/session_state.py (Wave-5 Cycle 5.3c Item 2)"
    )


# ---------------------------------------------------------------------------
# Item 3 -- _collect_all_commands delegates to _collect_event_commands.
# ---------------------------------------------------------------------------


def test_collect_all_commands_delegates() -> None:
    """tests/plugin/test_hooks_routing.py's `_collect_all_commands` must
    delegate to `_collect_event_commands` per event instead of
    re-implementing the same per-entry walk inline.

    A naive whole-file `src.count("_collect_event_commands") >= 2` check is
    NOT sufficient: the file already has two OTHER, unrelated call sites of
    `_collect_event_commands` inside separate test methods (used to check a
    single event's commands directly), so that count is already >= 2 today
    even though `_collect_all_commands` itself does not delegate. This test
    instead slices out `_collect_all_commands`'s own body -- the source
    between its `def` line and the following `def _collect_event_commands`
    line -- and asserts the delegation call appears specifically within
    that slice.
    """
    src = _read_target("plugin", "test_hooks_routing.py")

    start = src.index("def _collect_all_commands")
    end = src.index("def _collect_event_commands")
    assert end > start, (
        "expected `def _collect_event_commands` to appear after "
        "`def _collect_all_commands` in tests/plugin/test_hooks_routing.py "
        "so the body slice between them is well-defined"
    )
    body = src[start:end]

    assert "_collect_event_commands(" in body, (
        "tests/plugin/test_hooks_routing.py's `_collect_all_commands` body "
        "must call `_collect_event_commands(...)` per event instead of "
        "re-implementing the same per-entry walk inline -- no call to "
        "`_collect_event_commands(` was found within `_collect_all_commands`'s "
        "own body (Wave-5 Cycle 5.3c Item 3)"
    )


# ---------------------------------------------------------------------------
# Item 4 -- shared token-audit helpers.
# ---------------------------------------------------------------------------


def test_token_audit_helpers_importable() -> None:
    """`tests.fixtures.token_audit_helpers` exposes `load_token_audit`,
    `usage`, and `write_transcript` as callables.

    Imported LOCALLY so this is the only test that errors/fails while
    `tests/fixtures/token_audit_helpers.py` is absent. RED now (module
    doesn't exist); GREEN once it is created per plan.md Item 4.
    """
    from tests.fixtures.token_audit_helpers import load_token_audit, usage, write_transcript

    assert callable(load_token_audit), (
        "tests.fixtures.token_audit_helpers.load_token_audit must be a "
        "callable loader function"
    )
    assert callable(usage), (
        "tests.fixtures.token_audit_helpers.usage must be a callable "
        "superset usage-dict builder"
    )
    assert callable(write_transcript), (
        "tests.fixtures.token_audit_helpers.write_transcript must be a "
        "callable helper function"
    )


def test_token_audit_imports_shared_helpers() -> None:
    """tests/test_token_audit.py must import the shared token-audit
    helpers and no longer define its own local `_usage` helper.
    """
    src = _read_target("test_token_audit.py")

    assert "tests.fixtures.token_audit_helpers" in src, (
        "test_token_audit.py must import the shared helpers via "
        "`from tests.fixtures.token_audit_helpers import load_token_audit, "
        "usage, write_transcript` -- no reference to "
        "`tests.fixtures.token_audit_helpers` was found"
    )
    assert "def _usage" not in src, (
        "test_token_audit.py must no longer define a local `_usage` "
        "helper -- it is replaced by the shared superset "
        "`tests.fixtures.token_audit_helpers.usage` (Wave-5 Cycle 5.3c "
        "Item 4)"
    )


def test_token_audit_prevented_imports_shared_helpers() -> None:
    """tests/test_token_audit_prevented.py must import the shared
    token-audit helpers and no longer define its own local `_usage`
    helper.
    """
    src = _read_target("test_token_audit_prevented.py")

    assert "tests.fixtures.token_audit_helpers" in src, (
        "test_token_audit_prevented.py must import the shared helpers via "
        "`from tests.fixtures.token_audit_helpers import load_token_audit, "
        "usage, write_transcript` -- no reference to "
        "`tests.fixtures.token_audit_helpers` was found"
    )
    assert "def _usage" not in src, (
        "test_token_audit_prevented.py must no longer define a local "
        "`_usage` helper -- it is replaced by the shared superset "
        "`tests.fixtures.token_audit_helpers.usage` (Wave-5 Cycle 5.3c "
        "Item 4)"
    )
