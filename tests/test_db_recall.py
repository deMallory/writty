"""Decision Memory Phase 2 RECALL: tests for db.get_recent_decisions.

Every test here is RED until the implementer adds get_recent_decisions to
writ/graph/db.py. Tests fail on AttributeError (method missing) or
AssertionError, never on a collection/import error.

CRITICAL isolation guarantee: NO test in this file touches the live Neo4j
graph. All tests use a fake async driver/session that records the Cypher
query text and parameters, then returns canned rows. No Neo4jConnection or
migrate.py is instantiated.

Run: .venv/bin/python -m pytest tests/test_db_recall.py

Capability map:
  [db-recall-1]  get_recent_decisions returns only the queried project's Decisions
  [db-recall-2]  get_recent_decisions returns decisions newest-first (ORDER BY ts DESC)
  [db-recall-3]  get_recent_decisions respects the limit argument
  [db-recall-4]  get_recent_decisions parses planned_files from JSON-string to list[dict]
"""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Fake async driver / session infrastructure
# ---------------------------------------------------------------------------

class _FakeAsyncResult:
    """Async iterable over a fixed list of row-like dicts."""

    def __init__(self, rows: list[dict]) -> None:
        self._rows = rows

    def __aiter__(self):
        return self._iter()

    async def _iter(self):
        for row in self._rows:
            yield _FakeRecord(row)


class _FakeRecord:
    """Minimal dict-like Neo4j record stub."""

    def __init__(self, data: dict) -> None:
        self._data = data

    def __iter__(self):
        return iter(self._data)

    def keys(self):
        return self._data.keys()

    def values(self):
        return self._data.values()

    def items(self):
        return self._data.items()

    def __getitem__(self, key):
        return self._data[key]

    def __repr__(self):
        return f"_FakeRecord({self._data!r})"


class _FakeSession:
    """Records run() calls and returns canned rows."""

    def __init__(self, rows: list[dict]) -> None:
        self._rows = rows
        self.cypher_calls: list[tuple[str, dict]] = []

    async def run(self, query: str, **params) -> _FakeAsyncResult:
        self.cypher_calls.append((query, params))
        return _FakeAsyncResult(self._rows)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        pass


def _make_db_with_fake_session(rows: list[dict]) -> tuple[Any, _FakeSession]:
    """Build a partial Neo4jConnection whose _driver.session() returns a
    _FakeSession. Returns (db_instance, fake_session) so tests can inspect
    cypher_calls without touching Neo4j."""
    from writ.graph.db import Neo4jConnection

    fake_session = _FakeSession(rows)

    fake_driver = MagicMock()
    fake_driver.session.return_value = fake_session

    db = Neo4jConnection.__new__(Neo4jConnection)
    db._driver = fake_driver
    db._database = "neo4j"
    return db, fake_session


# ---------------------------------------------------------------------------
# Factories (TEST-FIXTURE-001)
# ---------------------------------------------------------------------------

def _decision_row(
    decision_id: str = "DEC-2026-001",
    project: str = "writ",
    title: str = "Add recall module",
    rationale: str = "Users need to read back decisions.",
    planned_files_json: str | None = None,
    governing_rule_ids: list[str] | None = None,
    phase: str = "planning",
    ts: str = "2026-06-27T10:00:00+00:00",
) -> dict:
    """Minimal canned row returned by the fake session for get_recent_decisions."""
    if planned_files_json is None:
        planned_files_json = json.dumps([{"path": "writ/session/recall.py", "reason": "new module"}])
    return {
        "decision_id": decision_id,
        "title": title,
        "rationale": rationale,
        "planned_files": planned_files_json,
        "governing_rule_ids": governing_rule_ids if governing_rule_ids is not None else ["PERF-BATCH-001"],
        "phase": phase,
        "ts": ts,
    }


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestGetRecentDecisionsProjectScope:
    """[db-recall-1]: only the queried project's Decisions appear."""

    @pytest.mark.asyncio
    async def test_query_includes_project_predicate(self) -> None:
        # [db-recall-1]: the generated Cypher must filter on d.project = $project.
        # The fake session returns one row. We assert the query contains the
        # project predicate -- this is the only way a DB-level scope is enforced
        # without a live graph.
        # RED: get_recent_decisions does not exist yet (AttributeError).
        db, session = _make_db_with_fake_session([_decision_row(project="writ")])

        await db.get_recent_decisions("writ", limit=5)

        assert session.cypher_calls, "get_recent_decisions must issue at least one Cypher query"
        cypher, params = session.cypher_calls[0]
        assert "$project" in cypher, (
            "Cypher must filter on $project so a Decision in another project is never returned; "
            f"query: {cypher!r}"
        )
        assert params.get("project") == "writ", (
            f"$project param must be 'writ'; got {params!r}"
        )

    @pytest.mark.asyncio
    async def test_decision_in_other_project_not_returned_by_query_predicate(self) -> None:
        # [db-recall-1]: querying project='projectA' must pass project='projectA'
        # as the parameter (not 'projectB'). We verify the param value directly.
        # RED: AttributeError.
        db, session = _make_db_with_fake_session([])

        await db.get_recent_decisions("projectA", limit=10)

        _, params = session.cypher_calls[0]
        assert params.get("project") == "projectA", (
            "project param must match the queried project, not another project; "
            f"got {params!r}"
        )

    @pytest.mark.asyncio
    async def test_decision_node_label_in_query(self) -> None:
        # [db-recall-1]: the query must MATCH on :Decision (the label that excludes
        # records from RETRIEVABLE_NODE_TYPES). A mismatch (e.g. MATCH (d:Rule))
        # would cross into the wrong node type.
        # RED: AttributeError.
        db, session = _make_db_with_fake_session([])

        await db.get_recent_decisions("writ")

        cypher, _ = session.cypher_calls[0]
        assert "Decision" in cypher, (
            f"MATCH must target the :Decision label; query: {cypher!r}"
        )


class TestGetRecentDecisionsOrdering:
    """[db-recall-2]: decisions returned newest-first (ORDER BY ts DESC)."""

    @pytest.mark.asyncio
    async def test_query_orders_by_ts_desc(self) -> None:
        # [db-recall-2]: ORDER BY d.ts DESC must appear in the Cypher so the
        # compile_recall eviction policy (newest-first) can rely on ordering.
        # RED: AttributeError.
        db, session = _make_db_with_fake_session([])

        await db.get_recent_decisions("writ")

        cypher, _ = session.cypher_calls[0]
        cypher_upper = cypher.upper()
        assert "ORDER BY" in cypher_upper and "DESC" in cypher_upper, (
            "Cypher must include ORDER BY ... DESC so decisions arrive newest-first; "
            f"query: {cypher!r}"
        )

    @pytest.mark.asyncio
    async def test_result_rows_preserved_in_order(self) -> None:
        # [db-recall-2]: the Python post-processing must not reorder rows returned
        # by the query. The fake session returns rows in the order given; we assert
        # the returned list preserves that order.
        # RED: AttributeError.
        newer = _decision_row(decision_id="NEWER-DEC", ts="2026-06-27T12:00:00+00:00")
        older = _decision_row(decision_id="OLDER-DEC", ts="2026-06-26T10:00:00+00:00")
        db, _ = _make_db_with_fake_session([newer, older])

        result = await db.get_recent_decisions("writ")

        assert len(result) == 2, f"expected 2 rows, got {len(result)}"
        assert result[0]["decision_id"] == "NEWER-DEC", (
            "first row must be the newer decision; "
            f"got {result[0].get('decision_id')!r}"
        )
        assert result[1]["decision_id"] == "OLDER-DEC", (
            f"second row must be the older decision; got {result[1].get('decision_id')!r}"
        )


class TestGetRecentDecisionsLimit:
    """[db-recall-3]: the limit argument is passed to the query."""

    @pytest.mark.asyncio
    async def test_limit_param_passed_to_query(self) -> None:
        # [db-recall-3]: $limit must appear in the Cypher and the limit argument
        # value must be passed as that parameter (LIMIT $limit, not LIMIT 20).
        # RED: AttributeError.
        db, session = _make_db_with_fake_session([])

        await db.get_recent_decisions("writ", limit=7)

        cypher, params = session.cypher_calls[0]
        assert "$limit" in cypher or "LIMIT" in cypher.upper(), (
            f"Cypher must use a LIMIT clause; query: {cypher!r}"
        )
        assert params.get("limit") == 7, (
            f"limit param must be 7; got {params!r}"
        )

    @pytest.mark.asyncio
    async def test_default_limit_is_twenty(self) -> None:
        # [db-recall-3]: when limit is omitted, the default must be 20 (as
        # documented in the plan).
        # RED: AttributeError.
        db, session = _make_db_with_fake_session([])

        await db.get_recent_decisions("writ")

        _, params = session.cypher_calls[0]
        assert params.get("limit") == 20, (
            f"default limit must be 20; got {params.get('limit')!r}"
        )


class TestGetRecentDecisionsPlannedFilesParsing:
    """[db-recall-4]: planned_files parsed from JSON-string to list[dict]."""

    @pytest.mark.asyncio
    async def test_json_string_parsed_to_list_of_dicts(self) -> None:
        # [db-recall-4]: Community Edition stores planned_files as a JSON string.
        # _parse_planned_files must deserialize it. The returned row must have a
        # list[dict], not the raw JSON string.
        # RED: AttributeError.
        files = [{"path": "writ/session/recall.py", "reason": "add recall", "resolved": False}]
        row = _decision_row(planned_files_json=json.dumps(files))
        db, _ = _make_db_with_fake_session([row])

        result = await db.get_recent_decisions("writ")

        assert len(result) == 1
        pf = result[0]["planned_files"]
        assert isinstance(pf, list), (
            f"planned_files must be a list[dict] after parsing; got {type(pf)}"
        )
        assert len(pf) == 1
        assert pf[0]["path"] == "writ/session/recall.py", (
            f"parsed planned_files[0].path must be 'writ/session/recall.py'; got {pf[0]!r}"
        )
        assert pf[0]["reason"] == "add recall", (
            f"parsed planned_files[0].reason must be 'add recall'; got {pf[0]!r}"
        )

    @pytest.mark.asyncio
    async def test_empty_planned_files_json_returns_empty_list(self) -> None:
        # [db-recall-4]: planned_files stored as '[]' must parse to [] not '[]'.
        # RED: AttributeError.
        row = _decision_row(planned_files_json="[]")
        db, _ = _make_db_with_fake_session([row])

        result = await db.get_recent_decisions("writ")

        pf = result[0]["planned_files"]
        assert pf == [], f"planned_files '[]' must parse to []; got {pf!r}"

    @pytest.mark.asyncio
    async def test_none_planned_files_returns_empty_list(self) -> None:
        # [db-recall-4]: planned_files=None (null in Community Edition) must be
        # handled gracefully -- returns [] not None (mirrors _parse_planned_files
        # fallback in db.py:1352).
        # RED: AttributeError.
        row = _decision_row(planned_files_json=None)
        row["planned_files"] = None  # simulate NULL from Neo4j
        db, _ = _make_db_with_fake_session([row])

        result = await db.get_recent_decisions("writ")

        pf = result[0]["planned_files"]
        assert pf == [], (
            f"planned_files=None must be normalized to []; got {pf!r}"
        )

    @pytest.mark.asyncio
    async def test_governing_rule_ids_defaults_to_empty_list(self) -> None:
        # [db-recall-4] adjacency: governing_rule_ids=None (null from Neo4j)
        # must be normalized to [] so callers never iterate None.
        # RED: AttributeError.
        row = _decision_row()
        row["governing_rule_ids"] = None  # simulate NULL
        db, _ = _make_db_with_fake_session([row])

        result = await db.get_recent_decisions("writ")

        assert result[0]["governing_rule_ids"] == [], (
            f"governing_rule_ids=None must default to []; got {result[0]['governing_rule_ids']!r}"
        )

    @pytest.mark.asyncio
    async def test_multiple_planned_files_all_parsed(self) -> None:
        # [db-recall-4]: multiple entries in the JSON array must all be parsed.
        # RED: AttributeError.
        files = [
            {"path": "writ/session/recall.py", "reason": "new", "resolved": False},
            {"path": "writ/server.py", "reason": "add route", "resolved": False},
        ]
        row = _decision_row(planned_files_json=json.dumps(files))
        db, _ = _make_db_with_fake_session([row])

        result = await db.get_recent_decisions("writ")

        pf = result[0]["planned_files"]
        assert len(pf) == 2, f"expected 2 parsed files; got {len(pf)}"
        paths = [f["path"] for f in pf]
        assert "writ/session/recall.py" in paths
        assert "writ/server.py" in paths
