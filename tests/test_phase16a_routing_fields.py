"""1.6a: methodology nodes carry node-declared routing fields.

floor_modes / action_triggers / trigger_keywords are the routing-as-data
substrate the 1.6 trigger index reads (mirroring Category.routes). Additive:
the fields default empty and carry no enforcement yet -- Invariant B (a pull node
with empty trigger_keywords fails ingest) fires only once keywords are authored,
else every pull node would fail ingest immediately.
"""

from __future__ import annotations

from datetime import date

import pytest
import pytest_asyncio

from writ.config import get_neo4j_password, get_neo4j_uri, get_neo4j_user
from writ.graph.db import Neo4jConnection
from writ.graph.schema import Skill

TEST_ID = "SKL-TEST-ROUTING-RT-001"


def _skill(**over) -> dict:
    base = dict(
        skill_id="SKL-TEST-ROUTING-001",
        domain="process",
        scope="task",
        trigger="When testing the node-declared routing fields.",
        statement="Routing fields are present on methodology nodes.",
        rationale="The trigger index reads node-declared routing data.",
        last_validated=date(2026, 1, 1),
        severity="high",
    )
    base.update(over)
    return base


class TestSchemaRoutingFields:
    def test_fields_default_empty(self) -> None:
        s = Skill(**_skill())
        assert s.floor_modes == []
        assert s.action_triggers == []
        assert s.trigger_keywords == []

    def test_fields_accept_values(self) -> None:
        s = Skill(**_skill(
            floor_modes=["work", "debug"],
            action_triggers=["plan", "gate-denial"],
            trigger_keywords=["worktree", "branch"],
        ))
        assert s.floor_modes == ["work", "debug"]
        assert s.action_triggers == ["plan", "gate-denial"]
        assert s.trigger_keywords == ["worktree", "branch"]


class TestIngestRoundtrip:
    @pytest_asyncio.fixture()
    async def db(self):
        conn = Neo4jConnection(get_neo4j_uri(), get_neo4j_user(), get_neo4j_password())
        try:
            async with conn._driver.session(database=conn._database) as s:
                await (await s.run("RETURN 1 AS ok")).consume()
        except Exception:
            await conn.close()
            pytest.skip("Neo4j unreachable")
        yield conn
        async with conn._driver.session(database=conn._database) as s:
            await s.run("MATCH (n:Skill {skill_id: $id}) DETACH DELETE n", id=TEST_ID)
        await conn.close()

    @pytest.mark.asyncio
    async def test_routing_fields_roundtrip_through_neo4j(self, db: Neo4jConnection) -> None:
        await db.create_methodology_node(
            "Skill",
            _skill(
                skill_id=TEST_ID,
                floor_modes=["work"],
                action_triggers=["plan"],
                trigger_keywords=["alpha", "beta"],
            ),
        )
        async with db._driver.session(database=db._database) as s:
            res = await s.run(
                "MATCH (n:Skill {skill_id: $id}) "
                "RETURN n.floor_modes AS fm, n.action_triggers AS at, n.trigger_keywords AS tk",
                id=TEST_ID,
            )
            rec = await res.single()
        assert rec["fm"] == ["work"]
        assert rec["at"] == ["plan"]
        assert rec["tk"] == ["alpha", "beta"]
