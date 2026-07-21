"""RED guard for Wave-5 Cycle 5.3a -- consolidate duplicated `_free_port`
test helper into a single shared `tests/fixtures/net.py`.

Five test modules each carry a byte-identical (modulo bind host) ~5-line
helper that binds a socket to port 0 and returns the OS-assigned free TCP
port for a stub `HTTPServer`. Per plan.md Cycle 5.3a, this collapses into one
canonical `tests.fixtures.net.free_port()`, imported by all five call sites
via `from tests.fixtures.net import free_port as _free_port`.

This guard is FULLY HERMETIC:
- The behavioral test binds at most one local ephemeral socket (port 0,
  OS-assigned, immediately closed by the helper itself). No daemon, no
  Neo4j.
- The five source-scan tests are pure source-text reads (`Path.read_text()`
  + substring checks). They do NOT import, execute, or collect fixtures from
  any target file, matching the idiom in tests/test_w5_hermeticity.py and
  tests/test_w5_live_env.py.

CRITICAL COLLECTION NOTE: `tests/fixtures/net.py` does not exist yet (the
implementer creates it in this cycle). The `from tests.fixtures.net import
free_port` import is therefore done INSIDE the behavioral test function, not
at module scope -- a module-level import would raise ImportError during test
COLLECTION and break every other test in this file. Importing locally means
only that one test errors/fails RED while the five source-scan tests still
collect and run normally.

RED today (2026-07-16, pre-implementation):
- `test_free_port_helper_exists_and_returns_valid_port` fails (ImportError /
  ModuleNotFoundError) because `tests/fixtures/net.py` does not exist yet.
- All five source-scan tests fail: each target file still contains
  `def _free_port` and none contains the literal `tests.fixtures.net`.

GREEN only once `tests/fixtures/net.py` exists with a `free_port() -> int`
and all five target files drop their local `def _free_port` in favor of
`from tests.fixtures.net import free_port as _free_port`.
"""

from __future__ import annotations

from pathlib import Path

TESTS_DIR = Path(__file__).resolve().parent


def test_free_port_helper_exists_and_returns_valid_port() -> None:
    """The shared helper module exists and returns a usable TCP port.

    Imported LOCALLY (not at module scope) so this is the only test that
    errors/fails while `tests/fixtures/net.py` is absent; the module-level
    import list below stays limited to stdlib so the rest of this file
    still collects. RED now (module doesn't exist); GREEN once
    `tests/fixtures/net.py` is created with `free_port() -> int`.
    """
    from tests.fixtures.net import free_port

    port = free_port()
    assert isinstance(port, int), (
        f"free_port() must return an int, got {type(port).__name__}: {port!r}"
    )
    assert 1 <= port <= 65535, (
        f"free_port() must return a port in the valid TCP range 1..65535, "
        f"got {port}"
    )


def _assert_migrated_to_shared_helper(filename: str) -> None:
    """Shared source-scan used by each per-file test below.

    Reads `filename`'s source text (never imports or executes it) and
    asserts BOTH:
    1. the local `def _free_port` has been removed, and
    2. the shared `tests.fixtures.net` import has been added.
    """
    path = TESTS_DIR / filename
    assert path.exists(), f"expected {path} to exist"
    src = path.read_text()

    assert "def _free_port" not in src, (
        f"{filename} must no longer define a local `def _free_port` -- it "
        "must be removed in favor of the shared "
        "`tests.fixtures.net.free_port` helper (Wave-5 Cycle 5.3a dedup)"
    )
    assert "tests.fixtures.net" in src, (
        f"{filename} must import the shared helper via "
        "`from tests.fixtures.net import free_port as _free_port` -- no "
        "reference to `tests.fixtures.net` was found"
    )


def test_read_rag_investigate_gate_uses_shared_free_port() -> None:
    """tests/test_read_rag_investigate_gate.py must drop its local
    `_free_port` and import the shared `tests.fixtures.net.free_port`.
    """
    _assert_migrated_to_shared_helper("test_read_rag_investigate_gate.py")


def test_subagent_rule_injection_uses_shared_free_port() -> None:
    """tests/test_subagent_rule_injection.py must drop its local
    `_free_port` and import the shared `tests.fixtures.net.free_port`.
    """
    _assert_migrated_to_shared_helper("test_subagent_rule_injection.py")


def test_rag_query_helper_uses_shared_free_port() -> None:
    """tests/test_rag_query_helper.py must drop its local `_free_port` and
    import the shared `tests.fixtures.net.free_port` (its `_closed_port()`
    keeps calling `_free_port()` unchanged, now resolving to the alias).
    """
    _assert_migrated_to_shared_helper("test_rag_query_helper.py")


def test_pre_write_dispatch_uses_shared_free_port() -> None:
    """tests/test_pre_write_dispatch.py must drop its local `_free_port`
    and import the shared `tests.fixtures.net.free_port`.
    """
    _assert_migrated_to_shared_helper("test_pre_write_dispatch.py")


def test_subagent_mode_inheritance_uses_shared_free_port() -> None:
    """tests/test_subagent_mode_inheritance.py must drop its local
    `_free_port` and import the shared `tests.fixtures.net.free_port`.
    """
    _assert_migrated_to_shared_helper("test_subagent_mode_inheritance.py")
