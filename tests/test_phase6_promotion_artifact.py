"""Phase 6.3b: the promotion gate surfaces a REVIEW ARTIFACT, not an id + a number.

A token makes an approval AUTHENTIC; it does not make it INFORMED. An "ID X crossed
threshold, approve? [y/N]" prompt trains the human to rubber-stamp. So the promotion path
must surface the candidate's CONTENT (statement, trigger, both examples, severity/scope)
AND its canon-fit: nearest rules by embedding similarity + conflict candidates
(CONFLICTS_WITH targets + same-category + high-similarity). The RED assertion is about
CONTENT presence (non-empty statements), not artifact shape -- an artifact of id-stubs
passes a structure check but still fails the North Star.

RED until 6.3b lands (writ.promotion.build_promotion_review_artifact does not exist yet).
"""
from __future__ import annotations

from dataclasses import dataclass
from unittest.mock import MagicMock

import numpy as np
import pytest
import pytest_asyncio

from writ.config import get_neo4j_password, get_neo4j_uri, get_neo4j_user
from writ.graph.db import Neo4jConnection

CAND = "ART-CAND-001"
SIM = "ART-SIM-001"          # high embedding similarity, different category
CONF = "ART-CONF-001"        # CONFLICTS_WITH the candidate
SAMECAT = "ART-CAT-001"      # shares the candidate's category
SEEDS = [CAND, SIM, CONF, SAMECAT]
CATEGORY = "CAT-PROC-001"


@dataclass
class Scored:
    rule_id: str
    score: float


def _rule(rid: str, statement: str, category: str | None = None) -> dict:
    d = {
        "rule_id": rid, "domain": "Testing", "severity": "high", "scope": "slice",
        "trigger": f"When {rid} applies.", "statement": statement,
        "violation": f"{rid} is violated.", "pass_example": f"{rid} is satisfied.",
        "enforcement": "e", "rationale": "r", "last_validated": "2026-03-15",
    }
    if category:
        d["category"] = category
    return d


def _mock_pipeline(search_results, neighbors):
    p = MagicMock()
    p._model.encode.return_value = np.zeros(384, dtype=np.float32)
    p._vector.search.return_value = search_results
    p._cache.get_neighbors.return_value = neighbors
    p._metadata = {}
    return p


@pytest_asyncio.fixture()
async def db():
    conn = Neo4jConnection(get_neo4j_uri(), get_neo4j_user(), get_neo4j_password())
    try:
        async with conn._driver.session(database=conn._database) as s:
            await (await s.run("RETURN 1 AS ok")).consume()
    except Exception:
        await conn.close()
        pytest.skip("Neo4j unreachable")
    async with conn._driver.session(database=conn._database) as s:
        await s.run("MATCH (n) WHERE n.rule_id IN $ids DETACH DELETE n", ids=SEEDS)
    yield conn
    async with conn._driver.session(database=conn._database) as s:
        await s.run("MATCH (n) WHERE n.rule_id IN $ids DETACH DELETE n", ids=SEEDS)
    await conn.close()


async def _seed(db: Neo4jConnection) -> None:
    await db.create_rule(_rule(CAND, "The candidate's load-bearing statement.", CATEGORY),
                         source_origin="graph-authored")
    await db.create_rule(_rule(SIM, "A near-duplicate existing rule statement."))
    await db.create_rule(_rule(CONF, "A directly conflicting rule statement."))
    await db.create_rule(_rule(SAMECAT, "Another rule in the same category.", CATEGORY))
    await db.create_edge("CONFLICTS_WITH", CAND, CONF)


class TestReviewArtifact:
    @pytest.mark.asyncio
    async def test_artifact_carries_candidate_content(self, db: Neo4jConnection) -> None:
        from writ.promotion import build_promotion_review_artifact
        await _seed(db)
        pipeline = _mock_pipeline(
            search_results=[Scored(SIM, 0.88), Scored(CAND, 0.99)],
            neighbors=[{"rule_id": CONF, "edge_type": "CONFLICTS_WITH", "direction": "out"}],
        )
        art = await build_promotion_review_artifact(CAND, pipeline, db)
        # Content the human must see -- not an id and a number.
        assert art["statement"] == "The candidate's load-bearing statement."
        assert art["violation"]
        assert art["pass_example"]
        assert art["severity"] == "high"
        assert art["scope"] == "slice"

    @pytest.mark.asyncio
    async def test_artifact_surfaces_nearest_with_statements(self, db: Neo4jConnection) -> None:
        from writ.promotion import build_promotion_review_artifact
        await _seed(db)
        pipeline = _mock_pipeline(
            search_results=[Scored(SIM, 0.88), Scored(CAND, 0.99)],
            neighbors=[],
        )
        art = await build_promotion_review_artifact(CAND, pipeline, db)
        near = {n["id"]: n for n in art["nearest_similar"]}
        assert CAND not in near, "the candidate must not list itself as a neighbor"
        assert SIM in near
        assert near[SIM]["statement"], "neighbor must carry its statement, not just an id"

    @pytest.mark.asyncio
    async def test_artifact_conflict_candidates_union(self, db: Neo4jConnection) -> None:
        from writ.promotion import build_promotion_review_artifact
        await _seed(db)
        pipeline = _mock_pipeline(
            search_results=[Scored(SIM, 0.88), Scored(CAND, 0.99)],
            neighbors=[{"rule_id": CONF, "edge_type": "CONFLICTS_WITH", "direction": "out"}],
        )
        art = await build_promotion_review_artifact(CAND, pipeline, db)
        by_id = {c["id"]: set(c["reasons"]) for c in art["conflict_candidates"]}
        assert "CONFLICTS_WITH" in by_id.get(CONF, set())
        assert "same-category" in by_id.get(SAMECAT, set())
        assert "high-similarity" in by_id.get(SIM, set())  # score 0.88 >= 0.7

    @pytest.mark.asyncio
    async def test_artifact_empty_neighbors_safe(self, db: Neo4jConnection) -> None:
        # A candidate with no neighbors yields empty lists, not an error.
        from writ.promotion import build_promotion_review_artifact
        await db.create_rule(_rule(CAND, "Lonely candidate."), source_origin="graph-authored")
        pipeline = _mock_pipeline(search_results=[Scored(CAND, 0.99)], neighbors=[])
        art = await build_promotion_review_artifact(CAND, pipeline, db)
        assert art["nearest_similar"] == []
        assert art["conflict_candidates"] == []
