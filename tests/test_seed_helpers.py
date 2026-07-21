"""Wave-3 dedup Cycle F: scripts/_seed_helpers.py (connect() + upsert_rule()).

The 10 scripts/seed_phase_*.py rulebook-expansion scripts each hand-roll the
same two shapes in their main():

  1. `db = Neo4jConnection(get_neo4j_uri(), get_neo4j_user(), get_neo4j_password())`
  2. per-rule loop:
       result = await session.run(
           "MATCH (r:Rule {rule_id: $rid}) RETURN r.rule_id AS x", rid=rule["rule_id"]
       )
       exists = await result.single() is not None
       props = {k: v for k, v in rule.items() if k != "rule_id"}
       await session.run(
           "MERGE (r:Rule {rule_id: $rid}) SET r += $props",
           rid=rule["rule_id"], props=props,
       )

The planned refactor extracts both into scripts/_seed_helpers.py:

    def connect() -> Neo4jConnection
    async def upsert_rule(session, rule) -> bool

and migrates each seed_phase_*.py to import and call them instead of
inlining the connect line + exists-probe/MERGE block.

scripts/ is not a package (no __init__.py, never installed), so this file
adds scripts/ to sys.path directly rather than importing it as
`writ.scripts._seed_helpers` or similar.

RED-now / GREEN-after-implementation split in THIS file:

  - TestUpsertRule is RED now: scripts/_seed_helpers.py does not exist yet.
    Guarded like tests/test_db_run_helper.py's TestQueryRunnerHelper --
    setup_method fails each test in the class individually with a clear
    reason instead of one opaque collection error for the whole file.
  - TestConnect is RED now for the same reason (module absent).
  - TestSeedScriptsAdoptHelpers is RED now: all 10 seed_phase_*.py scripts
    still inline their own `Neo4jConnection(...)` construction and their own
    exists-probe/MERGE block; none of them import scripts/_seed_helpers yet.
    Flips GREEN once each script is migrated in the same change that lands
    scripts/_seed_helpers.py.

The TestUpsertRule differential tests define a frozen `_head_upsert`
reproducing the HEAD (pre-refactor) inline block verbatim (captured from
scripts/seed_phase_1a_injection.py:284-296, identical in shape across all 10
scripts and cross-checked against scripts/seed_phase_2a_clean_dry.py:373-384).
Running both the frozen copy and the real imported `upsert_rule` against
fresh hermetic fake sessions for the same rule input must produce identical
call sequences and identical return values -- this is the regression net that
must stay green once the 10 scripts are migrated to call the real helper: if
the extraction silently reordered the probe/MERGE calls, dropped the
`rule_id` key from `props`, or changed what "existed" means, this
differential would catch it.

ENF-SYS-005 disclosure: every test below drives connect()/upsert_rule()
against a hermetic fake async session (_FakeSession/_FakeResult) or a fake
Neo4jConnection stand-in -- no real Neo4j, no socket, the shared graph is
never touched. This proves the exact Cypher text, parameter shapes, and
existed/not-existed return-value contract that upsert_rule must preserve,
and that connect() wires config getters into Neo4jConnection positionally in
the right order. It does NOT and CANNOT prove that the MERGE actually
upserts correctly against a real Neo4j engine, that Neo4jConnection.__init__
does anything sane with real driver construction, or anything about
concurrent-seed-run safety (two seed scripts racing to MERGE the same
rule_id). That coverage, if ever needed, belongs to a separate live-Neo4j
test; the 10 seed scripts are one-shot maintainer-run idempotent upserts, not
a concurrent-actor path, so no such test currently exists or is added here.

Run: .venv/bin/python -m pytest tests/test_seed_helpers.py -q
"""
from __future__ import annotations

import asyncio
import inspect
import sys
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

try:
    import _seed_helpers  # noqa: E402  # RED until scripts/_seed_helpers.py exists
    _IMPORT_ERROR = None
except ImportError as exc:  # RED until scripts/_seed_helpers.py exists
    _seed_helpers = None
    _IMPORT_ERROR = exc


def _require_seed_helpers() -> None:
    """Fail the calling test with a clear reason if scripts/_seed_helpers.py
    isn't importable yet (mirrors tests/test_db_run_helper.py's
    _require_query_runner_module pattern)."""
    if _IMPORT_ERROR is not None:
        pytest.fail(
            f"scripts/_seed_helpers.py is not importable yet: {_IMPORT_ERROR!r}"
        )


EXISTS_PROBE_QUERY = "MATCH (r:Rule {rule_id: $rid}) RETURN r.rule_id AS x"
MERGE_SET_MARKERS = ("MERGE (r:Rule {rule_id: $rid})", "SET r += $props")


def _rule_fixture(**overrides) -> dict:
    defaults = {
        "rule_id": "SEC-INJ-001",
        "domain": "security",
        "severity": "high",
        "statement": "s",
    }
    return {**defaults, **overrides}


# ---------------------------------------------------------------------------
# Hermetic fake async session -- records every call, in order. Never opens a
# socket, never touches the shared Neo4j graph.
# ---------------------------------------------------------------------------


class _FakeResult:
    def __init__(self, single_row):
        self._row = single_row

    async def single(self):
        return self._row


class _FakeSession:
    def __init__(self, single_row):
        self.calls: list[dict] = []
        self._single_row = single_row

    async def run(self, query, **params):
        self.calls.append({"query": query, "params": params})
        return _FakeResult(self._single_row)


# ---------------------------------------------------------------------------
# Section 1: upsert_rule. RED until scripts/_seed_helpers.py exists.
# ---------------------------------------------------------------------------


class TestUpsertRule:
    def setup_method(self) -> None:
        _require_seed_helpers()

    def test_upsert_rule_is_a_coroutine_function(self) -> None:
        assert inspect.iscoroutinefunction(_seed_helpers.upsert_rule)

    def test_existing_rule_issues_probe_then_merge_and_returns_true(self) -> None:
        rule = _rule_fixture()
        session = _FakeSession(single_row={"x": "SEC-INJ-001"})

        result = asyncio.run(_seed_helpers.upsert_rule(session, rule))

        assert len(session.calls) == 2
        assert session.calls[0]["query"] == EXISTS_PROBE_QUERY
        assert session.calls[0]["params"] == {"rid": "SEC-INJ-001"}
        for marker in MERGE_SET_MARKERS:
            assert marker in session.calls[1]["query"], (
                f"MERGE-SET query missing expected fragment: {marker!r}"
            )
        assert session.calls[1]["params"] == {
            "rid": "SEC-INJ-001",
            "props": {"domain": "security", "severity": "high", "statement": "s"},
        }
        assert result is True

    def test_new_rule_still_issues_both_calls_and_returns_false(self) -> None:
        rule = _rule_fixture()
        session = _FakeSession(single_row=None)

        result = asyncio.run(_seed_helpers.upsert_rule(session, rule))

        assert len(session.calls) == 2
        assert result is False

    @staticmethod
    async def _head_upsert(session, rule: dict) -> bool:
        """Frozen reproduction of the HEAD inline exists-probe/MERGE block
        shared by all 10 scripts/seed_phase_*.py main() loops (verbatim from
        scripts/seed_phase_1a_injection.py:284-296 at HEAD, before the
        Cycle F extraction into scripts/_seed_helpers.upsert_rule)."""
        result = await session.run(
            "MATCH (r:Rule {rule_id: $rid}) RETURN r.rule_id AS x", rid=rule["rule_id"]
        )
        existed = await result.single() is not None
        props = {k: v for k, v in rule.items() if k != "rule_id"}
        await session.run(
            """
            MERGE (r:Rule {rule_id: $rid})
            SET r += $props
            """,
            rid=rule["rule_id"], props=props,
        )
        return existed

    def test_differential_against_head_inline_block_existing_rule(self) -> None:
        rule = _rule_fixture()
        head_session = _FakeSession(single_row={"x": "SEC-INJ-001"})
        real_session = _FakeSession(single_row={"x": "SEC-INJ-001"})

        head_result = asyncio.run(self._head_upsert(head_session, rule))
        real_result = asyncio.run(_seed_helpers.upsert_rule(real_session, rule))

        # Compare Cypher-token + params equivalence, not the heredoc's incidental
        # leading whitespace: the MERGE query's indentation legitimately changed when
        # the block moved from a deep-nested main() loop to a module-level helper, and
        # Neo4j ignores leading whitespace. Params and return are still asserted exactly.
        def _norm(calls: list[dict]) -> list[dict]:
            return [{"query": " ".join(c["query"].split()), "params": c["params"]} for c in calls]

        assert _norm(head_session.calls) == _norm(real_session.calls)
        assert head_result is True
        assert real_result is True

    def test_differential_against_head_inline_block_new_rule(self) -> None:
        rule = _rule_fixture()
        head_session = _FakeSession(single_row=None)
        real_session = _FakeSession(single_row=None)

        head_result = asyncio.run(self._head_upsert(head_session, rule))
        real_result = asyncio.run(_seed_helpers.upsert_rule(real_session, rule))

        # Compare Cypher-token + params equivalence, not the heredoc's incidental
        # leading whitespace: the MERGE query's indentation legitimately changed when
        # the block moved from a deep-nested main() loop to a module-level helper, and
        # Neo4j ignores leading whitespace. Params and return are still asserted exactly.
        def _norm(calls: list[dict]) -> list[dict]:
            return [{"query": " ".join(c["query"].split()), "params": c["params"]} for c in calls]

        assert _norm(head_session.calls) == _norm(real_session.calls)
        assert head_result is False
        assert real_result is False


# ---------------------------------------------------------------------------
# Section 2: connect(). RED until scripts/_seed_helpers.py exists.
# ---------------------------------------------------------------------------


class _FakeNeo4jConnection:
    def __init__(self, uri, user, password):
        self.args = (uri, user, password)


class TestConnect:
    def setup_method(self) -> None:
        _require_seed_helpers()

    def test_connect_builds_neo4j_connection_from_config_values(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Patch the names as bound ON _seed_helpers (it does `from writ.config
        # import get_neo4j_uri, get_neo4j_user, get_neo4j_password` and `from
        # writ.graph.db import Neo4jConnection`, so these are module-level
        # attributes of _seed_helpers, not of writ.config/writ.graph.db).
        monkeypatch.setattr(_seed_helpers, "get_neo4j_uri", lambda: "URI")
        monkeypatch.setattr(_seed_helpers, "get_neo4j_user", lambda: "USER")
        monkeypatch.setattr(_seed_helpers, "get_neo4j_password", lambda: "PW")
        monkeypatch.setattr(_seed_helpers, "Neo4jConnection", _FakeNeo4jConnection)

        conn = _seed_helpers.connect()

        assert isinstance(conn, _FakeNeo4jConnection)
        assert conn.args == ("URI", "USER", "PW")


# ---------------------------------------------------------------------------
# Section 3: source guards over the 10 seed_phase_*.py scripts. RED now (all
# 10 still inline their own connect line + exists-probe/MERGE block); flips
# GREEN once each script is migrated to `from _seed_helpers import connect,
# upsert_rule` and call sites use connect()/upsert_rule(...) instead.
# ---------------------------------------------------------------------------

SEED_SCRIPT_NAMES = [
    "seed_phase_1a_injection",
    "seed_phase_1b_auth",
    "seed_phase_1c_crypto_headers_rate",
    "seed_phase_1d_data_deps",
    "seed_phase_2a_clean_dry",
    "seed_phase_2b_solid_arch",
    "seed_phase_3a_testing_error",
    "seed_phase_3b_performance",
    "seed_phase_4_scale_api_docs",
    "seed_phase_5_process",
]


class TestSeedScriptsAdoptHelpers:
    @pytest.mark.parametrize("script_name", SEED_SCRIPT_NAMES)
    def test_script_adopts_seed_helpers(self, script_name: str) -> None:
        source = (SCRIPTS_DIR / f"{script_name}.py").read_text(encoding="utf-8")

        assert "from _seed_helpers import" in source, (
            f"{script_name}.py does not import from _seed_helpers yet"
        )
        assert "connect()" in source, (
            f"{script_name}.py does not call connect() yet"
        )
        assert "upsert_rule(" in source, (
            f"{script_name}.py does not call upsert_rule(...) yet"
        )
        assert (
            "db = Neo4jConnection(get_neo4j_uri(), get_neo4j_user(), get_neo4j_password())"
            not in source
        ), (
            f"{script_name}.py still inlines the raw Neo4jConnection(...) "
            "construction; it should call connect() instead"
        )
        assert "exists = await result.single() is not None" not in source, (
            f"{script_name}.py still inlines the exists-probe/MERGE block; "
            "it should call upsert_rule(session, rule) instead"
        )
