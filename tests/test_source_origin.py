"""0.10 foundation: the `source_origin` bit (ingest | graph-authored).

The reconcile-on-ingest deletion exemption keys on SOURCE EXISTENCE, not trust. A node
carries `source_origin: ingest` when it came from a markdown source file, and
`graph-authored` when it was written graph-first (`/propose`, `cli add/edit`) and has no
markdown home yet. Reconcile (later in 0.10) deletes a not-in-source node only when
`source_origin != graph-authored`. This bit is the binary floor of 6.1's provenance enum.

These tests pin the WRITE-PATH behavior: which creation path stamps which origin.
"""
from __future__ import annotations

import pytest
import pytest_asyncio

from writ.config import get_neo4j_password, get_neo4j_uri, get_neo4j_user
from writ.graph.db import Neo4jConnection


def _make_rule(rule_id: str) -> dict:
    return {
        "rule_id": rule_id, "domain": "Test", "severity": "medium", "scope": "file",
        "trigger": "t", "statement": "s", "violation": "v", "pass_example": "p",
        "enforcement": "e", "rationale": "r", "mandatory": False,
        "confidence": "production-validated", "evidence": "doc:original-bible",
    }


@pytest_asyncio.fixture()
async def db():
    conn = Neo4jConnection(get_neo4j_uri(), get_neo4j_user(), get_neo4j_password())
    await conn.clear_all()
    yield conn
    await conn.clear_all()
    await conn.close()


async def _node_origin(db: Neo4jConnection, label: str, id_field: str, node_id: str) -> str | None:
    async with db._driver.session(database=db._database) as s:
        r = await s.run(
            f"MATCH (n:{label} {{{id_field}: $id}}) RETURN n.source_origin AS so", id=node_id
        )
        rec = await r.single()
        return rec["so"] if rec else None


class TestSourceOriginWritePath:
    @pytest.mark.asyncio
    async def test_create_rule_defaults_to_ingest(self, db: Neo4jConnection) -> None:
        await db.create_rule(_make_rule("SO-RULE-ING-001"))
        assert await _node_origin(db, "Rule", "rule_id", "SO-RULE-ING-001") == "ingest"

    @pytest.mark.asyncio
    async def test_create_rule_graph_authored_when_flagged(self, db: Neo4jConnection) -> None:
        await db.create_rule(_make_rule("SO-RULE-GA-001"), source_origin="graph-authored")
        assert await _node_origin(db, "Rule", "rule_id", "SO-RULE-GA-001") == "graph-authored"

    @pytest.mark.asyncio
    async def test_create_methodology_node_defaults_to_ingest(self, db: Neo4jConnection) -> None:
        await db.create_methodology_node(
            "Skill",
            {"skill_id": "SO-SKILL-001", "domain": "process", "severity": "high",
             "scope": "task", "trigger": "t", "statement": "s", "rationale": "r"},
        )
        assert await _node_origin(db, "Skill", "skill_id", "SO-SKILL-001") == "ingest"


class TestSourceOriginIsGraphOnly:
    """source_origin is set at write time, never authored in markdown -- it must be
    excluded from export and from 5.2's field-level methodology parity diff."""

    def test_source_origin_in_graph_only_fields(self) -> None:
        from writ.export import GRAPH_ONLY_FIELDS
        assert "source_origin" in GRAPH_ONLY_FIELDS, (
            "source_origin must be graph-only or it leaks into exported markdown and "
            "flags as field-drift in the 5.2 methodology parity check"
        )
