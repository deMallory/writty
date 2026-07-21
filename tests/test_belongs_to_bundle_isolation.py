"""Behavioral regression guard: BELONGS_TO edges must NOT enter AdjacencyCache.

Risk: if BELONGS_TO edges entered the cache, the pattern

    rule -> Category <- sibling

would link every rule to its entire category membership through the category
hub. Neighbor/enrichment expansion is INJECTED into the prompt (not scored), so
a 75-member security category would produce a 75-node dump on every query.

The guard is the `type(r) <> 'BELONGS_TO'` WHERE clause inside
build_from_db's Cypher query. This test MUST FAIL if that clause is removed.

Fixture: a tiny isolated graph -- two Rule nodes (TST-A-001, TST-B-001) and
one Category node (CAT-TST-001), each rule connected to the category via
BELONGS_TO. No RELATED_TO edge between the rules. After build_from_db the
cache must show zero BELONGS_TO entries and get_neighbors('TST-A-001') must not
contain TST-B-001 or CAT-TST-001.
"""

from __future__ import annotations

from datetime import date

import pytest
import pytest_asyncio

from writ.config import get_neo4j_password, get_neo4j_uri, get_neo4j_user
from writ.graph.db import Neo4jConnection
from writ.retrieval.traversal import AdjacencyCache

NEO4J_URI = get_neo4j_uri()
NEO4J_USER = get_neo4j_user()
NEO4J_PASSWORD = get_neo4j_password()


# ---------------------------------------------------------------------------
# Module-level reachability guard
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module", autouse=True)
def _require_neo4j():
    """Skip the entire module when Neo4j is unreachable.

    Uses the same neo4j_reachable() helper + autouse pattern as
    test_db_category.py so the skip is structural, not accidental.
    """
    from tests._corpus import neo4j_reachable

    if not neo4j_reachable():
        pytest.skip("Neo4j unreachable")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _rule_data(rule_id: str) -> dict:
    return {
        "rule_id": rule_id,
        "domain": "Test",
        "severity": "medium",
        "scope": "file",
        "trigger": "Test trigger",
        "statement": "Test statement",
        "violation": "Test violation",
        "pass_example": "Test pass example",
        "enforcement": "Test enforcement",
        "rationale": "Test rationale",
        "mandatory": False,
        "confidence": "production-validated",
        "evidence": "doc:test",
        "staleness_window": 365,
        "last_validated": date.today().isoformat(),
    }


def _category_data() -> dict:
    return {
        "category_id": "CAT-TST-001",
        "name": "test-category",
        "routes": ["semantic"],
        "parent": None,
        "description": "Fixture category for bundle-isolation tests.",
    }


# ---------------------------------------------------------------------------
# Fixture: isolated graph with two rules + one category, BELONGS_TO only
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture()
async def db_with_belongs_to():
    """Set up a tiny isolated Neo4j graph and tear it down after the test.

    Graph topology:
        TST-A-001 -[BELONGS_TO]-> CAT-TST-001
        TST-B-001 -[BELONGS_TO]-> CAT-TST-001

    There is NO RELATED_TO edge between TST-A-001 and TST-B-001.
    If BELONGS_TO leaked into AdjacencyCache, TST-B-001 would appear
    as a depth-2 neighbor of TST-A-001 via the category hub.
    """
    conn = Neo4jConnection(NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD)
    await conn.clear_all()

    await conn.create_rule(_rule_data("TST-A-001"))
    await conn.create_rule(_rule_data("TST-B-001"))
    await conn.create_methodology_node("Category", _category_data())

    await conn.create_edge("BELONGS_TO", "TST-A-001", "CAT-TST-001")
    await conn.create_edge("BELONGS_TO", "TST-B-001", "CAT-TST-001")

    yield conn

    await conn.clear_all()
    await conn.close()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestBelongsToDoesNotEnterCache:
    """BELONGS_TO edges must be absent from AdjacencyCache after build_from_db."""

    @pytest.mark.asyncio
    async def test_no_belongs_to_edge_type_in_cache(
        self, db_with_belongs_to: Neo4jConnection
    ) -> None:
        """After build_from_db, no neighbor entry carries edge_type 'BELONGS_TO'.

        If the guard (`type(r) <> 'BELONGS_TO'`) were removed from the Cypher
        query in AdjacencyCache.build_from_db, BELONGS_TO edges would populate
        the _neighbors dict and this assertion would fail.
        """
        cache = AdjacencyCache()
        await cache.build_from_db(db_with_belongs_to)

        for node_id, neighbors in cache._neighbors.items():
            for neighbor in neighbors:
                assert neighbor["edge_type"] != "BELONGS_TO", (
                    f"BELONGS_TO edge found in AdjacencyCache for node '{node_id}': "
                    f"{neighbor}. The build_from_db guard must exclude BELONGS_TO."
                )

    @pytest.mark.asyncio
    async def test_no_category_node_id_in_cache_neighbors(
        self, db_with_belongs_to: Neo4jConnection
    ) -> None:
        """After build_from_db, no neighbor entry has a rule_id starting with 'CAT-'.

        Category nodes use the category_id field (e.g. 'CAT-TST-001'), not rule_id.
        The coalesce() in build_from_db's query resolves category_id only when no
        rule_id is present; if BELONGS_TO were allowed through, CAT-TST-001 would
        appear as a neighbor entry with rule_id='CAT-TST-001'.
        """
        cache = AdjacencyCache()
        await cache.build_from_db(db_with_belongs_to)

        for node_id, neighbors in cache._neighbors.items():
            for neighbor in neighbors:
                assert not neighbor["rule_id"].startswith("CAT-"), (
                    f"Category node ID '{neighbor['rule_id']}' found as a neighbor "
                    f"of '{node_id}' in AdjacencyCache. Category membership edges "
                    f"(BELONGS_TO) must be excluded from the traversal cache."
                )


class TestBelongsToNeighborIsolation:
    """get_neighbors (the production traversal accessor) must not surface a
    BELONGS_TO co-member or the Category hub.

    With TST-A-001 -[BELONGS_TO]-> CAT-TST-001 <-[BELONGS_TO]- TST-B-001 and NO
    RELATED_TO edge, build_from_db's `type(r) <> 'BELONGS_TO'` guard means
    get_neighbors('TST-A-001') is empty -- neither the category hub nor the
    co-member is reachable. (Was a get_bundle depth-2 BFS; get_bundle was removed
    in 1.6b, so this re-points the behavioral guard onto the live accessor.)
    """

    @pytest.mark.asyncio
    async def test_neighbors_exclude_co_member(
        self, db_with_belongs_to: Neo4jConnection
    ) -> None:
        """TST-B-001 (a category co-member) must not be a neighbor of TST-A-001.

        Both BELONGS_TO CAT-TST-001. If BELONGS_TO leaked into the cache the hub
        would link them; the guard keeps get_neighbors('TST-A-001') free of it.
        """
        cache = AdjacencyCache()
        await cache.build_from_db(db_with_belongs_to)

        neighbor_ids = [n["rule_id"] for n in cache.get_neighbors("TST-A-001")]

        assert "TST-B-001" not in neighbor_ids, (
            "TST-B-001 surfaced as a neighbor of TST-A-001 via the category hub. "
            "BELONGS_TO edges must be excluded from AdjacencyCache so category "
            "co-membership does not contaminate the traversal accessor."
        )

    @pytest.mark.asyncio
    async def test_neighbors_exclude_category_node(
        self, db_with_belongs_to: Neo4jConnection
    ) -> None:
        """CAT-TST-001 must not appear as a neighbor of TST-A-001.

        Category nodes are organizational containers, not semantic neighbors.
        If BELONGS_TO were included, CAT-TST-001 would appear as a direct neighbor.
        """
        cache = AdjacencyCache()
        await cache.build_from_db(db_with_belongs_to)

        neighbor_ids = [n["rule_id"] for n in cache.get_neighbors("TST-A-001")]

        assert "CAT-TST-001" not in neighbor_ids, (
            "CAT-TST-001 (category node) appeared as a neighbor of TST-A-001. "
            "Category membership edges (BELONGS_TO) must be excluded from "
            "AdjacencyCache so Category nodes never enter the traversal accessor."
        )

    @pytest.mark.asyncio
    async def test_neighbors_empty_when_only_belongs_to(
        self, db_with_belongs_to: Neo4jConnection
    ) -> None:
        """With no RELATED_TO edges, both rules have NO neighbors.

        Positive confirmation: the fixture has ONLY BELONGS_TO edges, so after the
        guard excludes them the adjacency cache is empty for both test rules.
        """
        cache = AdjacencyCache()
        await cache.build_from_db(db_with_belongs_to)

        assert cache.get_neighbors("TST-A-001") == [], (
            f"Expected no neighbors for TST-A-001, got {cache.get_neighbors('TST-A-001')}. "
            "With only BELONGS_TO edges (all excluded), the rule must have no neighbors."
        )
        assert cache.get_neighbors("TST-B-001") == [], (
            f"Expected no neighbors for TST-B-001, got {cache.get_neighbors('TST-B-001')}."
        )
