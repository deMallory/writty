"""RED guard for Wave-5 Cycle 5.3b -- consolidate duplicated decision-memory
test fixtures/helpers across three test files.

Per plan.md Cycle 5.3b, this cycle:
1. creates `tests/fixtures/bitbucket.py` with a `make_bb_client(responses, *,
   email, token) -> (client, transport)` factory, replacing the dead
   `_make_bb_client` and 23 inline `_SequentialTransport`/`httpx.AsyncClient`/
   `BitbucketClient` construction triples in
   `tests/test_decision_memory_pr_comments.py`;
2. creates `tests/fixtures/server_routes.py` with shared `client` and
   `isolated_cache` pytest fixtures, imported explicitly into
   `tests/test_decision_memory_capture.py` and
   `tests/test_decision_memory_commit.py` in place of their byte-identical
   local copies;
3. collapses the nine inline `_FakeDB` classes plus `_FakeDBWithCited` in
   `tests/test_decision_memory_commit.py` into two contract-aligned
   factories (`_make_fake_route_db`, `_make_fake_capture_db`); and
4. replaces the vacuous `__aenter__`-only Neo4j guard in
   `tests/test_decision_memory_commit.py` with a real `RETURN 1 AS ok`
   liveness probe.

This guard is FULLY HERMETIC:
- The two behavioral tests exercise only the new fixture modules
  in-process (a mocked httpx transport with an EMPTY response list, and a
  plain fixture-callable check). No daemon, no Neo4j, no real HTTP.
- The five source-scan tests are pure source-text reads
  (`Path.read_text()` + substring/count checks). They do NOT import,
  execute, or collect fixtures from any target file, matching the idiom in
  tests/test_w5_hermeticity.py and tests/test_w5_free_port.py.

CRITICAL COLLECTION NOTE: `tests/fixtures/bitbucket.py` and
`tests/fixtures/server_routes.py` do not exist yet (the implementer creates
them in this cycle). Both behavioral tests therefore import them LOCALLY
(inside the test function), not at module scope -- a module-level import
would raise ImportError/ModuleNotFoundError during test COLLECTION and break
every other test in this file. Importing locally means only that one test
errors/fails RED while the five source-scan tests still collect and run
normally.

RED today (2026-07-16, pre-implementation):
- `test_bitbucket_factory_importable_and_returns_pair` fails (ImportError)
  because `tests/fixtures/bitbucket.py` does not exist.
- `test_server_routes_fixtures_importable` fails (ImportError) because
  `tests/fixtures/server_routes.py` does not exist.
- `test_pr_comments_uses_shared_bb_factory` fails: `_make_bb_client` is
  still defined, `tests.fixtures.bitbucket` is not imported,
  `_SequentialTransport` is still defined locally, and `BitbucketClient(`
  is constructed 24 times (not <= 1).
- `test_capture_imports_shared_fixtures` fails: no
  `tests.fixtures.server_routes` import; `def isolated_cache` still present
  locally.
- `test_commit_imports_shared_fixtures` fails: same as above for the commit
  file.
- `test_commit_fakedb_consolidated` fails: `class _FakeDB` occurs 11 times
  (not 0), and neither `_make_fake_route_db` nor `_make_fake_capture_db`
  exists yet.
- `test_commit_neo4j_guard_uses_liveness_probe` fails: `RETURN 1 AS ok`
  occurs only once today (the `db_clean` fixture's probe); the vacuous
  `__aenter__`-only guard has not yet been replaced with a second probe.

All seven become GREEN only once the fixture modules are created and the
three target files are migrated per plan.md Cycle 5.3b.
"""

from __future__ import annotations

from pathlib import Path

TESTS_DIR = Path(__file__).resolve().parent


def _read_target(filename: str) -> str:
    """Resolve and read a target file's source text relative to this file.

    Asserts the file exists first so a missing target fails loudly with a
    clear path rather than a confusing FileNotFoundError deep in
    `read_text()`.
    """
    path = TESTS_DIR / filename
    assert path.exists(), f"expected {path} to exist"
    return path.read_text()


# ---------------------------------------------------------------------------
# Behavioral: shared fixture modules are importable (local imports -- see
# CRITICAL COLLECTION NOTE above).
# ---------------------------------------------------------------------------


def test_bitbucket_factory_importable_and_returns_pair() -> None:
    """`tests.fixtures.bitbucket.make_bb_client` exists and constructs a
    `(client, transport)` pair with zero HTTP requests for an empty
    responses list.

    Imported LOCALLY so this is the only test that errors/fails while
    `tests/fixtures/bitbucket.py` is absent. RED now (module doesn't
    exist); GREEN once the factory is created per plan.md Decision A.
    """
    from tests.fixtures.bitbucket import make_bb_client

    result = make_bb_client([])

    assert isinstance(result, tuple) and len(result) == 2, (
        f"make_bb_client([]) must return a 2-tuple (client, transport), "
        f"got {type(result).__name__} of length "
        f"{len(result) if isinstance(result, tuple) else 'n/a'}"
    )
    client, transport = result

    assert client, (
        "make_bb_client([]) must return a truthy client as the first "
        "element of the pair"
    )
    assert hasattr(transport, "_seen"), (
        "make_bb_client([]) must return a transport with a `_seen` "
        "attribute so callers can assert on captured requests"
    )
    assert isinstance(transport._seen, list), (
        f"transport._seen must be a list, got {type(transport._seen).__name__}"
    )


def test_server_routes_fixtures_importable() -> None:
    """`tests.fixtures.server_routes` exposes `client` and `isolated_cache`
    as callable pytest fixture functions.

    Imported LOCALLY so this is the only test that errors/fails while
    `tests/fixtures/server_routes.py` is absent. RED now (module doesn't
    exist); GREEN once the shared fixtures are created per plan.md
    Decision B.
    """
    from tests.fixtures.server_routes import client, isolated_cache

    assert callable(client), (
        "tests.fixtures.server_routes.client must be a callable pytest "
        "fixture function"
    )
    assert callable(isolated_cache), (
        "tests.fixtures.server_routes.isolated_cache must be a callable "
        "pytest fixture function"
    )


# ---------------------------------------------------------------------------
# Source-scan: pr_comments migrated to the shared bitbucket factory.
# ---------------------------------------------------------------------------


def test_pr_comments_uses_shared_bb_factory() -> None:
    """tests/test_decision_memory_pr_comments.py must drop the dead
    `_make_bb_client` helper and the local `_SequentialTransport` class,
    import the shared factory, and construct `BitbucketClient(` at most
    once (i.e. only inside the shared factory module, not inline at any
    of the 23 former call sites).
    """
    src = _read_target("test_decision_memory_pr_comments.py")

    assert "def _make_bb_client" not in src, (
        "test_decision_memory_pr_comments.py must no longer define the "
        "dead local `_make_bb_client` helper -- it is replaced by the "
        "shared `tests.fixtures.bitbucket.make_bb_client` factory"
    )
    assert "tests.fixtures.bitbucket" in src, (
        "test_decision_memory_pr_comments.py must import the shared "
        "factory via `from tests.fixtures.bitbucket import make_bb_client` "
        "(and/or the transport/response helpers) -- no reference to "
        "`tests.fixtures.bitbucket` was found"
    )
    assert "class _SequentialTransport" not in src, (
        "test_decision_memory_pr_comments.py must no longer define "
        "`class _SequentialTransport` locally -- it moves into "
        "`tests/fixtures/bitbucket.py` per plan.md Decision A"
    )

    bb_construction_count = src.count("BitbucketClient(")
    assert bb_construction_count <= 1, (
        "test_decision_memory_pr_comments.py must construct "
        "`BitbucketClient(` at most once inline (essentially all 23 "
        f"former inline sites replaced by make_bb_client), found "
        f"{bb_construction_count} occurrences"
    )


# ---------------------------------------------------------------------------
# Source-scan: capture + commit import the shared server_routes fixtures.
# ---------------------------------------------------------------------------


def test_capture_imports_shared_fixtures() -> None:
    """tests/test_decision_memory_capture.py must import the shared
    `client`/`isolated_cache` fixtures and drop its local `isolated_cache`
    definition.
    """
    src = _read_target("test_decision_memory_capture.py")

    assert "tests.fixtures.server_routes" in src, (
        "test_decision_memory_capture.py must import the shared fixtures "
        "via `from tests.fixtures.server_routes import client, "
        "isolated_cache` -- no reference to `tests.fixtures.server_routes` "
        "was found"
    )
    assert "def isolated_cache" not in src, (
        "test_decision_memory_capture.py must no longer define a local "
        "`isolated_cache` fixture -- it is replaced by the shared copy in "
        "tests/fixtures/server_routes.py"
    )


def test_commit_imports_shared_fixtures() -> None:
    """tests/test_decision_memory_commit.py must import the shared
    `client`/`isolated_cache` fixtures and drop its local `isolated_cache`
    definition.
    """
    src = _read_target("test_decision_memory_commit.py")

    assert "tests.fixtures.server_routes" in src, (
        "test_decision_memory_commit.py must import the shared fixtures "
        "via `from tests.fixtures.server_routes import client, "
        "isolated_cache` -- no reference to `tests.fixtures.server_routes` "
        "was found"
    )
    assert "def isolated_cache" not in src, (
        "test_decision_memory_commit.py must no longer define a local "
        "`isolated_cache` fixture -- it is replaced by the shared copy in "
        "tests/fixtures/server_routes.py"
    )


# ---------------------------------------------------------------------------
# Source-scan: commit's _FakeDB consolidation + Neo4j guard fix.
# ---------------------------------------------------------------------------


def test_commit_fakedb_consolidated() -> None:
    """tests/test_decision_memory_commit.py's nine inline `_FakeDB` classes
    (plus `_FakeDBWithCited`) must collapse into two contract-aligned
    factories: `_make_fake_route_db` and `_make_fake_capture_db`.

    Note: `src.count("class _FakeDB")` also counts occurrences of
    `class _FakeDBWithCited` (it contains the substring `class _FakeDB`),
    so a single count check catches both families. The assertion is ==0
    after consolidation -- every inline class is gone, replaced by the two
    factory functions.
    """
    src = _read_target("test_decision_memory_commit.py")

    fakedb_count = src.count("class _FakeDB")
    assert fakedb_count == 0, (
        "test_decision_memory_commit.py must no longer define any inline "
        "`class _FakeDB` (or `class _FakeDBWithCited`, which contains that "
        f"substring) -- found {fakedb_count} occurrence(s); all must "
        "collapse into `_make_fake_route_db`/`_make_fake_capture_db` per "
        "plan.md Decision C"
    )
    assert "_make_fake_route_db" in src, (
        "test_decision_memory_commit.py must define the minimal "
        "route/spy contract factory `_make_fake_route_db` (get_projects + "
        "create_project only), preserving the AttributeError signal that "
        "the auto-install route must not call create_commit"
    )
    assert "_make_fake_capture_db" in src, (
        "test_decision_memory_commit.py must define the capture-contract "
        "factory `_make_fake_capture_db(*, open_decisions=None, "
        "resolve_count=0)`, generalizing the existing "
        "`_make_fake_db_for_merge` per plan.md Decision C"
    )


def test_commit_neo4j_guard_uses_liveness_probe() -> None:
    """tests/test_decision_memory_commit.py's vacuous `__aenter__`-only
    Neo4j guard must be replaced with a real `RETURN 1 AS ok` liveness
    probe.

    The `db_clean` fixture already contains one `RETURN 1 AS ok` literal
    (around line 170); the fix adds a second one to the previously vacuous
    guard, so the total count in the file must be >= 2.
    """
    src = _read_target("test_decision_memory_commit.py")

    probe_count = src.count("RETURN 1 AS ok")
    assert probe_count >= 2, (
        "test_decision_memory_commit.py must contain at least two "
        "`RETURN 1 AS ok` liveness-probe literals: one in the existing "
        "`db_clean` fixture and a second replacing the vacuous "
        "`__aenter__`-only guard so it actually skips when Neo4j is "
        f"unreachable (plan.md Decision D) -- found {probe_count}"
    )
