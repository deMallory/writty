"""Phase M.2: composite (project, *_id) identity.

RED-FIRST. With M.1, nodes carry a `project` but MERGE keys + uniqueness are
still per-id only. So ingesting rule X into project 'writ' then into 'proj2'
MERGEs onto the SAME node (project clobbered to 'proj2') -- a silent
cross-project identity collision. The single-property `rule_id IS UNIQUE`
constraint also forbids two projects from ever holding the same id.

Fix: MERGE on (id, project); replace single-property uniqueness with composite
(id, project) (Community-available on 5.26, verified); scope create_edge endpoint
matches by project so an edge never resolves to another project's same-id node.
Collision policy: same-id/diff-project COEXIST (namespace), never reject.

Each test isolated (TEST-ISO-001).
"""

from __future__ import annotations

from datetime import date

import pytest
import pytest_asyncio

from writ.config import get_neo4j_password, get_neo4j_uri, get_neo4j_user
from writ.graph.db import Neo4jConnection

NEO4J_URI = get_neo4j_uri()
NEO4J_USER = get_neo4j_user()
NEO4J_PASSWORD = get_neo4j_password()


def _rule(rule_id: str, project: str, statement: str = "s.") -> dict:
    return {
        "rule_id": rule_id, "domain": "security", "severity": "medium",
        "scope": "file", "trigger": "t.", "statement": statement, "violation": "v.",
        "pass_example": "p.", "enforcement": "e.", "rationale": "r.",
        "mandatory": False, "confidence": "production-validated",
        "evidence": "doc:original-bible", "staleness_window": 365,
        "last_validated": date.today().isoformat(), "project": project,
    }


@pytest_asyncio.fixture()
async def db():
    conn = Neo4jConnection(NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD)
    await conn.clear_all()
    await conn.apply_constraints()
    yield conn
    await conn.clear_all()
    await conn.close()


async def _rules_with_id(db: Neo4jConnection, rule_id: str) -> list[dict]:
    async with db._driver.session(database=db._database) as s:
        res = await s.run(
            "MATCH (r:Rule {rule_id: $id}) RETURN r.project AS project, r.statement AS stmt "
            "ORDER BY project", id=rule_id)
        return [dict(r) async for r in res]


class TestSameIdDifferentProjectCoexist:
    @pytest.mark.asyncio
    async def test_same_id_two_projects_are_two_nodes(self, db) -> None:
        await db.create_rule(_rule("SHARED-A-001", "writ", "writ statement"))
        await db.create_rule(_rule("SHARED-A-001", "proj2", "proj2 statement"))
        rows = await _rules_with_id(db, "SHARED-A-001")
        assert len(rows) == 2, f"expected 2 coexisting nodes, got {len(rows)}: {rows}"
        assert {r["project"] for r in rows} == {"writ", "proj2"}
        # Each keeps its OWN statement (no clobber).
        by_proj = {r["project"]: r["stmt"] for r in rows}
        assert by_proj["writ"] == "writ statement"
        assert by_proj["proj2"] == "proj2 statement"

    @pytest.mark.asyncio
    async def test_same_id_same_project_still_upserts(self, db) -> None:
        # Within ONE project, MERGE is still idempotent (one node).
        await db.create_rule(_rule("UP-A-001", "writ", "first"))
        await db.create_rule(_rule("UP-A-001", "writ", "second"))
        rows = await _rules_with_id(db, "UP-A-001")
        assert len(rows) == 1
        assert rows[0]["stmt"] == "second"


class TestCompositeConstraint:
    @pytest.mark.asyncio
    async def test_composite_uniqueness_present_and_single_absent(self, db) -> None:
        constraints = await db.list_constraints()
        # A composite (rule_id, project) uniqueness constraint exists...
        def props(c):
            return tuple(c.get("properties") or [])
        rule_constraints = [
            c for c in constraints
            if (c.get("labelsOrTypes") or []) == ["Rule"] and c.get("type") == "UNIQUENESS"
        ]
        composite = [c for c in rule_constraints if set(props(c)) == {"rule_id", "project"}]
        single = [c for c in rule_constraints if props(c) == ("rule_id",)]
        assert composite, f"no composite (rule_id, project) uniqueness; have {rule_constraints}"
        assert not single, f"single-property rule_id uniqueness must be gone; have {single}"


class TestEdgeProjectScoping:
    @pytest.mark.asyncio
    async def test_edge_resolves_within_project(self, db) -> None:
        # writ and proj2 both have X-A-001; proj2 also has Y-A-001. An edge
        # X-A-001 -> Y-A-001 created for proj2 must connect proj2's X, not writ's.
        await db.create_rule(_rule("X-A-001", "writ"))
        await db.create_rule(_rule("X-A-001", "proj2"))
        await db.create_rule(_rule("Y-A-001", "proj2"))
        await db.create_edge("RELATED_TO", "X-A-001", "Y-A-001", project="proj2")
        async with db._driver.session(database=db._database) as s:
            res = await s.run(
                "MATCH (a:Rule {rule_id:'X-A-001'})-[:RELATED_TO]->(b:Rule {rule_id:'Y-A-001'}) "
                "RETURN a.project AS ap, b.project AS bp")
            rows = [dict(r) async for r in res]
        assert len(rows) == 1, f"expected exactly one within-project edge, got {rows}"
        assert rows[0]["ap"] == "proj2" and rows[0]["bp"] == "proj2"
