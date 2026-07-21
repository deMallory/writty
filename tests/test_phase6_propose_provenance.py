"""Phase 6.2: /propose + cli add/edit stamp/preserve provenance=proposed.

6.2 is DELIVERED BY 6.1's derivation: /propose and cli add already pass
source_origin='graph-authored', which _node_write_spec maps to provenance='proposed'
with no extra stamping; cli edit carries the existing provenance through
`updated = dict(existing)`. These tests LOCK that contract so a later change to the
derivation default cannot silently re-home a self-authored node as hand-authored.

No new production code is expected for 6.2 -- the behavior emerges from the 6.1
single-source-of-truth derivation. The tests are regression locks at the propose and
edit boundaries.
"""
from __future__ import annotations

from datetime import date
from unittest.mock import AsyncMock, MagicMock

import numpy as np
import pytest
import pytest_asyncio

from writ.config import get_neo4j_password, get_neo4j_uri, get_neo4j_user
from writ.gate import propose_rule
from writ.graph.db import Neo4jConnection


def _make_candidate(**overrides: str) -> dict:
    base = {
        "rule_id": "PROV-PROPOSE-001",
        "domain": "Testing",
        "severity": "high",
        "scope": "file",
        "trigger": "When writing a function that exceeds 30 lines.",
        "statement": "Functions must not exceed 30 lines of logic.",
        "violation": "Function body is 45 lines.",
        "pass_example": "Function decomposed into sub-functions.",
        "enforcement": "Code review.",
        "rationale": "Long functions resist testing and reuse.",
        "last_validated": date.today().isoformat(),
    }
    base.update(overrides)
    return base


def _mock_pipeline():
    """A pipeline whose retrieval finds only a low-similarity neighbor, so the
    structural gate accepts (not redundant, novel enough)."""
    from dataclasses import make_dataclass
    Scored = make_dataclass("Scored", [("rule_id", str), ("score", float)])
    pipeline = MagicMock()
    pipeline._model.encode.return_value = np.zeros(384, dtype=np.float32)
    pipeline._vector.search.return_value = [Scored("EXISTING-001", 0.30)]
    pipeline._metadata = {}
    pipeline._cache.get_neighbors.return_value = []
    return pipeline


async def _node_prov(db: Neo4jConnection, rule_id: str) -> str | None:
    async with db._driver.session(database=db._database) as s:
        r = await s.run("MATCH (r:Rule {rule_id: $id}) RETURN r.provenance AS p", id=rule_id)
        rec = await r.single()
        return rec["p"] if rec else None


@pytest_asyncio.fixture()
async def db():
    conn = Neo4jConnection(get_neo4j_uri(), get_neo4j_user(), get_neo4j_password())
    try:
        async with conn._driver.session(database=conn._database) as s:
            await (await s.run("RETURN 1 AS ok")).consume()
    except Exception:
        await conn.close()
        pytest.skip("Neo4j unreachable")
    await conn.clear_all()
    yield conn
    await conn.clear_all()
    await conn.close()


class TestProposeStampsProposed:
    @pytest.mark.asyncio
    async def test_propose_lands_proposed_in_graph(self, db: Neo4jConnection) -> None:
        # Real db, mock pipeline: the end-to-end propose path must leave the node
        # provenance=proposed (NOT hand-authored), authority ai-provisional.
        result = await propose_rule(_make_candidate(), _mock_pipeline(), db)
        assert result["accepted"] is True
        assert await _node_prov(db, "PROV-PROPOSE-001") == "proposed"

    @pytest.mark.asyncio
    async def test_propose_passes_graph_authored_to_create_rule(self) -> None:
        # The mechanism: propose enters the graph-authored write path that 6.1
        # derives to 'proposed'. Pin the call so the derivation contract holds.
        mock_db = AsyncMock()
        await propose_rule(_make_candidate(), _mock_pipeline(), mock_db)
        _, kwargs = mock_db.create_rule.call_args
        assert kwargs.get("source_origin") == "graph-authored"


class TestCliAddEditProvenance:
    """cli add uses the same graph-authored path (-> proposed); cli edit rebuilds the
    node from `dict(existing)` and preserves source_origin, so provenance carries
    through unchanged."""

    @pytest.mark.asyncio
    async def test_add_mechanism_lands_proposed(self, db: Neo4jConnection) -> None:
        await db.create_rule(_make_candidate(rule_id="PROV-ADD-001"),
                             source_origin="graph-authored")
        assert await _node_prov(db, "PROV-ADD-001") == "proposed"

    @pytest.mark.asyncio
    async def test_edit_preserves_proposed(self, db: Neo4jConnection) -> None:
        # Seed a proposed node, then re-write it the way `writ edit` does: rebuild
        # from the graph node and preserve its source_origin. provenance must stay
        # proposed (NOT flip to hand-authored).
        await db.create_rule(_make_candidate(rule_id="PROV-EDIT-001"),
                             source_origin="graph-authored")
        existing = await db.get_rule("PROV-EDIT-001")
        updated = dict(existing)
        updated["statement"] = "Functions must not exceed 25 lines of logic."
        await db.create_rule(updated, source_origin=updated.get("source_origin", "ingest"))
        assert await _node_prov(db, "PROV-EDIT-001") == "proposed"

    @pytest.mark.asyncio
    async def test_edit_preserves_hand_authored(self, db: Neo4jConnection) -> None:
        await db.create_rule(_make_candidate(rule_id="PROV-EDIT-HA-001"))  # ingest
        existing = await db.get_rule("PROV-EDIT-HA-001")
        updated = dict(existing)
        updated["statement"] = "Functions must not exceed 20 lines of logic."
        await db.create_rule(updated, source_origin=updated.get("source_origin", "ingest"))
        assert await _node_prov(db, "PROV-EDIT-HA-001") == "hand-authored"
