"""Phase M.2b: multi-project data-integrity RED tests.

Three contracts currently broken in the graph layer:

A) Abstraction composite (id, project) identity
   create_abstraction MERGEs on {abstraction_id} alone (no project scope), so
   seeding the same abstraction_id under two projects clobbers the first node.
   create_abstracts_edge has no project scope and can resolve to the wrong
   project's node.

B) ingest_edges cross-project edge resolution
   known_ids is built from get_all_rules() which spans ALL projects. A parsed
   edge referencing an id that exists in project A (but is not in project B's
   parsed set) silently resolves instead of being reported dangling.

C) create_edge OR-match is a hardcoded 13-field list, not derived from
   NODE_ID_FIELDS. A structural drift test: the set of id fields in the
   create_edge query must equal the set of values in NODE_ID_FIELDS.

Each test asserts the CORRECT behaviour. All three currently FAIL (RED) because
the implementation has the bugs described above.

Teardown discipline: each fixture deletes ONLY the nodes it seeded (by their
test-unique ids) so the shared corpus is not wiped between runs.
"""

from __future__ import annotations

import inspect

import pytest
import pytest_asyncio

from writ.config import get_neo4j_password, get_neo4j_uri, get_neo4j_user
from writ.graph.db import Neo4jConnection, _id_or_match
from writ.graph.methodology_ingest import ingest_edges
from writ.graph.schema import NODE_ID_FIELDS

NEO4J_URI = get_neo4j_uri()
NEO4J_USER = get_neo4j_user()
NEO4J_PASSWORD = get_neo4j_password()

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_TEST_RULE_PREFIX = "MTEST-IR"  # "multi-test integrity RED"


def _rule_data(rule_id: str, project: str) -> dict:
    return {
        "rule_id": rule_id,
        "domain": "testing",
        "severity": "medium",
        "scope": "file",
        "trigger": "Trigger for test rule.",
        "statement": f"Statement for {rule_id}.",
        "violation": "v.",
        "pass_example": "p.",
        "enforcement": "e.",
        "rationale": "r.",
        "mandatory": False,
        "confidence": "production-validated",
        "evidence": "doc:original-bible",
        "staleness_window": 365,
        "last_validated": "2026-06-16",
        "project": project,
    }


def _abstraction_data(abstraction_id: str, project: str) -> dict:
    return {
        "abstraction_id": abstraction_id,
        "summary": f"Summary for {abstraction_id} in {project}.",
        "rule_ids": [],
        "domain": "testing",
        "compression_ratio": 1.0,
        "project": project,
    }


async def _delete_nodes_by_ids(db: Neo4jConnection, node_ids: list[str]) -> None:
    """Delete only the test-seeded nodes identified by their id values across all types.

    Checks every id field from NODE_ID_FIELDS so the cleanup covers Rules,
    Abstractions, and any other type seeded by a test.
    """
    for id_field in NODE_ID_FIELDS.values():
        async with db._driver.session(database=db._database) as s:
            await s.run(
                f"MATCH (n) WHERE n.{id_field} IN $ids DETACH DELETE n",
                ids=node_ids,
            )


# ---------------------------------------------------------------------------
# db fixture -- connects, skips if unreachable, corpus-safe teardown
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture()
async def db():
    """Open a real Neo4j connection. Skips if unreachable. Teardown is caller-managed."""
    conn = Neo4jConnection(NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD)
    try:
        async with conn._driver.session(database=conn._database) as s:
            await (await s.run("RETURN 1 AS ok")).consume()
    except Exception:
        await conn.close()
        pytest.skip("Neo4j unreachable")
    yield conn
    await conn.close()


# ---------------------------------------------------------------------------
# Contract A: Abstraction composite identity
# ---------------------------------------------------------------------------


class TestAbstractionCompositeIdentity:
    """Contract A -- create_abstraction must MERGE on (abstraction_id, project),
    not on abstraction_id alone.

    RED: currently MERGEs on {abstraction_id} only -> second write clobbers first.
    """

    @pytest.mark.asyncio
    async def test_same_abstraction_id_two_projects_coexist(self, db) -> None:
        """Two Abstraction nodes with the same abstraction_id but different projects
        must coexist as distinct nodes.  Today create_abstraction clobbers the first."""
        abs_id = "ABS-MTEST-ID-001"
        seeded = [abs_id]
        try:
            await db.create_abstraction(_abstraction_data(abs_id, "projA"))
            await db.create_abstraction(_abstraction_data(abs_id, "projB"))

            async with db._driver.session(database=db._database) as s:
                res = await s.run(
                    "MATCH (a:Abstraction {abstraction_id: $id}) "
                    "RETURN a.project AS project, a.summary AS summary "
                    "ORDER BY project",
                    id=abs_id,
                )
                rows = [dict(r) async for r in res]

            assert len(rows) == 2, (
                f"Expected 2 coexisting Abstraction nodes for {abs_id}, "
                f"got {len(rows)}: {rows}. "
                "Bug: create_abstraction MERGEs on abstraction_id alone -> clobber."
            )
            projects = {r["project"] for r in rows}
            assert projects == {"projA", "projB"}, (
                f"Expected projects {{'projA','projB'}}, got {projects}"
            )
        finally:
            await _delete_nodes_by_ids(db, seeded)

    @pytest.mark.asyncio
    async def test_create_abstraction_no_project_defaults_to_writ(self, db) -> None:
        """create_abstraction with no project in the data dict must store project='writ'.

        Today the MERGE has no project scope and the node carries whatever project
        value was in the props dict (or none at all). When no project key is passed,
        the node should default to 'writ'.
        """
        abs_id = "ABS-MTEST-DEF-001"
        seeded = [abs_id]
        data_without_project = {
            "abstraction_id": abs_id,
            "summary": "Default project test.",
            "rule_ids": [],
            "domain": "testing",
            "compression_ratio": 1.0,
            # intentionally no "project" key
        }
        try:
            await db.create_abstraction(data_without_project)

            async with db._driver.session(database=db._database) as s:
                res = await s.run(
                    "MATCH (a:Abstraction {abstraction_id: $id}) RETURN a.project AS project",
                    id=abs_id,
                )
                rec = await res.single()

            assert rec is not None, f"Abstraction {abs_id} not found after create."
            assert rec["project"] == "writ", (
                f"Expected project='writ' (default), got {rec['project']!r}. "
                "Bug: create_abstraction does not apply a project default."
            )
        finally:
            await _delete_nodes_by_ids(db, seeded)

    @pytest.mark.asyncio
    async def test_abstracts_edge_is_project_scoped(self, db) -> None:
        """create_abstracts_edge(project='projA') must link projA's Abstraction to
        projA's Rule. Today there is no project parameter -- the call must accept one
        and the test is RED because the current signature lacks it.
        """
        abs_id = "ABS-MTEST-EDGE-001"
        rule_id = f"{_TEST_RULE_PREFIX}-E-001"
        seeded = [abs_id, rule_id]
        try:
            await db.create_rule(_rule_data(rule_id, "projA"))
            await db.create_abstraction(_abstraction_data(abs_id, "projA"))

            # create_abstracts_edge will gain a project parameter; pass project="projA".
            # RED today: the current signature is create_abstracts_edge(abstraction_id, rule_id)
            # with no project kwarg -- this call will raise TypeError.
            await db.create_abstracts_edge(abs_id, rule_id, project="projA")

            async with db._driver.session(database=db._database) as s:
                res = await s.run(
                    "MATCH (a:Abstraction {abstraction_id: $aid})"
                    "-[:ABSTRACTS]->"
                    "(r:Rule {rule_id: $rid}) "
                    "RETURN a.project AS ap, r.project AS rp",
                    aid=abs_id,
                    rid=rule_id,
                )
                rows = [dict(r) async for r in res]

            assert len(rows) == 1, (
                f"Expected 1 ABSTRACTS edge scoped to projA, got {len(rows)}. "
                "Bug: create_abstracts_edge has no project scope."
            )
            assert rows[0]["ap"] == "projA" and rows[0]["rp"] == "projA", (
                f"Edge resolved to wrong project(s): {rows[0]}. "
                "Bug: create_abstracts_edge must match within project."
            )
        finally:
            await _delete_nodes_by_ids(db, seeded)

    @pytest.mark.asyncio
    async def test_write_abstractions_to_graph_propagates_project(self, db) -> None:
        """The production write-path must propagate `project` so compress-generated
        Abstraction nodes + ABSTRACTS edges land in the caller's project, not 'writ'
        (closes the caller-side half of the seam, not just the db API)."""
        from writ.compression.abstractions import write_abstractions_to_graph

        rid = _TEST_RULE_PREFIX + "-WA-RULE-001"
        aid = "ABS-MTEST-WA-001"
        seeded = [rid, aid]
        try:
            await db.create_rule(_rule_data(rid, "projWA"))
            absts = [{
                "abstraction_id": aid, "summary": "s", "domain": "testing",
                "compression_ratio": 1.0, "rule_ids": [rid],
            }]
            await write_abstractions_to_graph(db, absts, project="projWA")
            async with db._driver.session(database=db._database) as s:
                node = await (await s.run(
                    "MATCH (a:Abstraction {abstraction_id:$id}) RETURN a.project AS p", id=aid
                )).single()
                edge = await (await s.run(
                    "MATCH (:Abstraction {abstraction_id:$aid})-[e:ABSTRACTS]->(:Rule {rule_id:$rid}) "
                    "RETURN e.project AS p", aid=aid, rid=rid
                )).single()
            assert node is not None and node["p"] == "projWA", "Abstraction node must carry the project"
            assert edge is not None and edge["p"] == "projWA", (
                "ABSTRACTS edge must resolve in-project and carry e.project"
            )
        finally:
            await _delete_nodes_by_ids(db, seeded)


# ---------------------------------------------------------------------------
# Contract B: ingest_edges cross-project isolation
# ---------------------------------------------------------------------------


class TestIngestEdgesCrossProjectIsolation:
    """Contract B -- ingest_edges for project B must not resolve edge endpoints
    against nodes that belong only to project A.

    RED: get_all_rules() is unscoped -> known_ids spans all projects -> an edge
    referencing a projA id is silently created instead of marked dangling.
    """

    @pytest.mark.asyncio
    async def test_cross_project_rule_ref_is_dangling(self, db) -> None:
        """Seed rule X in projA. Run ingest_edges for projB with a parsed edge that
        references X. The edge must be reported dangling (created=0, dangling=1).

        Today known_ids includes X (from get_all_rules) so the edge is created
        cross-project: created=1, dangling=0 -- the wrong result.
        """
        rule_x = f"{_TEST_RULE_PREFIX}-B-001"   # exists only in projA
        rule_y = f"{_TEST_RULE_PREFIX}-B-002"   # will be in projB's parsed_nodes
        seeded = [rule_x, rule_y]
        try:
            # Seed rule X in projA (in the graph, not in projB's parsed_nodes).
            await db.create_rule(_rule_data(rule_x, "projA"))

            # projB's parsed_nodes contains rule Y only.
            parsed_nodes_b = [
                {
                    **_rule_data(rule_y, "projB"),
                    "node_type": "Rule",
                }
            ]
            # Declare an edge from Y -> X; X is NOT in projB's parsed set.
            parsed_edges_b = [
                {"type": "RELATED_TO", "source": rule_y, "target": rule_x}
            ]

            # Seed rule Y into the graph so the edge write has a source node.
            await db.create_rule(_rule_data(rule_y, "projB"))

            created, dangling = await ingest_edges(
                parsed_nodes_b, parsed_edges_b, db, project="projB"
            )

            assert dangling >= 1, (
                f"Expected dangling>=1 (cross-project X not in projB), "
                f"got created={created} dangling={dangling}. "
                "Bug: get_all_rules() is unscoped -> X resolves cross-project."
            )
            assert created == 0, (
                f"Expected created=0 (edge should be dangling), "
                f"got created={created}. "
                "Bug: ingest_edges silently creates a cross-project edge."
            )
        finally:
            await _delete_nodes_by_ids(db, seeded)

    @pytest.mark.asyncio
    async def test_within_project_rule_ref_is_not_dangling(self, db) -> None:
        """Sanity check: an edge whose both endpoints belong to projB's parsed_nodes
        must NOT be reported dangling.

        This test is currently GREEN (in-project resolution works) and pins that the
        fix to Contract B does not regress the happy path.
        """
        rule_a = f"{_TEST_RULE_PREFIX}-C-001"
        rule_b = f"{_TEST_RULE_PREFIX}-C-002"
        seeded = [rule_a, rule_b]
        try:
            await db.create_rule(_rule_data(rule_a, "projB"))
            await db.create_rule(_rule_data(rule_b, "projB"))

            parsed_nodes_b = [
                {**_rule_data(rule_a, "projB"), "node_type": "Rule"},
                {**_rule_data(rule_b, "projB"), "node_type": "Rule"},
            ]
            parsed_edges_b = [
                {"type": "RELATED_TO", "source": rule_a, "target": rule_b}
            ]

            created, dangling = await ingest_edges(
                parsed_nodes_b, parsed_edges_b, db, project="projB"
            )

            assert dangling == 0, (
                f"In-project edge must not be dangling; got dangling={dangling}."
            )
            assert created >= 1, (
                f"In-project edge must be created; got created={created}."
            )
        finally:
            await _delete_nodes_by_ids(db, seeded)


# ---------------------------------------------------------------------------
# Contract C: create_edge OR-match derived from NODE_ID_FIELDS
# ---------------------------------------------------------------------------


class TestCreateEdgeOrMatchDerivedFromSchema:
    """Contract C -- the OR-match lists in create_edge and batch_create_edges
    (fallback path) must be derived from NODE_ID_FIELDS, not hardcoded.

    RED: the lists are hardcoded at 13 fields. The derivation tests fail because
    NODE_ID_FIELDS is not referenced inside the methods.
    """

    def test_create_edge_delegates_to_id_or_match(self) -> None:
        """create_edge must DERIVE its OR-match by delegating to _id_or_match (which
        builds from NODE_ID_FIELDS), not hardcode a field list. Asserting the
        delegation call -- not a literal source string -- means re-hardcoding (which
        would drop the _id_or_match call) turns this RED, and there is no manual
        comment/list to keep in sync.
        """
        source = inspect.getsource(Neo4jConnection.create_edge)
        assert "_id_or_match(" in source, (
            "create_edge must call _id_or_match to derive its OR-match from "
            "NODE_ID_FIELDS; a hardcoded field list is the Contract C bug."
        )

    def test_batch_create_edges_fallback_delegates_to_id_or_match(self) -> None:
        """Same derivation guard for the batch_create_edges label-less fallback."""
        source = inspect.getsource(Neo4jConnection.batch_create_edges)
        assert "_id_or_match(" in source, (
            "batch_create_edges fallback must call _id_or_match (the same derivation "
            "as create_edge), not a duplicated hardcoded OR-clause."
        )

    def test_id_or_match_covers_every_node_id_field(self) -> None:
        """The deriving helper must cover EVERY NODE_ID_FIELDS value -- so adding a
        14th node type to the registry is matched automatically with no source edit.
        Behavioral (calls the helper), not a source-text audit, so it cannot be
        satisfied by a comment.
        """
        clause = _id_or_match("a", "src")
        missing = sorted(f for f in set(NODE_ID_FIELDS.values()) if f"a.{f}" not in clause)
        assert not missing, (
            f"_id_or_match omits these NODE_ID_FIELDS values: {missing} -- edge "
            "resolution would silently fail for those node types."
        )
