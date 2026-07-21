"""Phase 6.3a: the frequency crossing produces a CANDIDATE, never canon.

When a PROPOSED rule crosses the graduation threshold (n>=50, positive-ratio>=0.75),
its provenance flips proposed -> graduation_pending: a candidate surfaced for the human
promotion gate (6.3b/6.3c). It MUST NOT:
  - promote authority (stays ai-provisional until a human gates it),
  - write to bible/ source (canon is human-authored at promotion).

The flip is idempotent and one-directional: ONLY a `proposed` node flips; a
graduation_pending / hand-authored / graduated node is never (re)flipped by the crossing.
Frequency is evidence that EARNS human attention, not approval (North Star).

RED until 6.3a lands (db.evaluate_and_flip_graduation does not exist yet).
"""
from __future__ import annotations

import pytest
import pytest_asyncio

from writ.config import get_neo4j_password, get_neo4j_uri, get_neo4j_user
from writ.graph.db import Neo4jConnection

LOW_T = 4  # a low threshold keeps the unit tests fast (real default is 50)


def _rule(rid: str) -> dict:
    return {
        "rule_id": rid, "domain": "Testing", "severity": "high", "scope": "slice",
        "trigger": "t", "statement": "s", "violation": "v", "pass_example": "p",
        "enforcement": "e", "rationale": "r", "last_validated": "2026-03-15",
        "authority": "ai-provisional",
    }


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


async def _set_counts(db: Neo4jConnection, rule_id: str, pos: int, neg: int) -> None:
    async with db._driver.session(database=db._database) as s:
        await s.run(
            "MATCH (r:Rule {rule_id: $id}) SET r.times_seen_positive=$p, r.times_seen_negative=$n",
            id=rule_id, p=pos, n=neg,
        )


async def _field(db: Neo4jConnection, rule_id: str, field: str):
    async with db._driver.session(database=db._database) as s:
        r = await s.run(f"MATCH (r:Rule {{rule_id: $id}}) RETURN r.{field} AS v", id=rule_id)
        rec = await r.single()
        return rec["v"] if rec else None


async def _seed_proposed(db: Neo4jConnection, rid: str, pos: int, neg: int) -> None:
    await db.create_rule(_rule(rid), source_origin="graph-authored")  # -> proposed
    await _set_counts(db, rid, pos, neg)


class TestGraduationCandidateFlip:
    @pytest.mark.asyncio
    async def test_proposed_crossing_flips_to_graduation_pending(self, db: Neo4jConnection) -> None:
        await _seed_proposed(db, "GRAD-FLIP-001", pos=4, neg=0)  # n=4>=4, ratio=1.0
        new = await db.evaluate_and_flip_graduation("GRAD-FLIP-001", threshold=LOW_T)
        assert new == "graduation_pending"
        assert await _field(db, "GRAD-FLIP-001", "provenance") == "graduation_pending"

    @pytest.mark.asyncio
    async def test_below_threshold_stays_proposed(self, db: Neo4jConnection) -> None:
        await _seed_proposed(db, "GRAD-LOW-001", pos=2, neg=0)  # n=2<4
        new = await db.evaluate_and_flip_graduation("GRAD-LOW-001", threshold=LOW_T)
        assert new is None
        assert await _field(db, "GRAD-LOW-001", "provenance") == "proposed"

    @pytest.mark.asyncio
    async def test_flagged_low_ratio_stays_proposed(self, db: Neo4jConnection) -> None:
        # n>=threshold but ratio<0.75 -> flagged, NOT graduated -> no flip.
        await _seed_proposed(db, "GRAD-FLAG-001", pos=2, neg=3)  # n=5>=4, ratio=0.4
        new = await db.evaluate_and_flip_graduation("GRAD-FLAG-001", threshold=LOW_T)
        assert new is None
        assert await _field(db, "GRAD-FLAG-001", "provenance") == "proposed"

    @pytest.mark.asyncio
    async def test_hand_authored_never_flips(self, db: Neo4jConnection) -> None:
        # Only a proposed node is a graduation candidate; a hand-authored rule with
        # high counts must NOT be dragged into the graduation pipeline.
        await db.create_rule(_rule("GRAD-HA-001"))  # ingest -> hand-authored
        await _set_counts(db, "GRAD-HA-001", 100, 0)
        new = await db.evaluate_and_flip_graduation("GRAD-HA-001", threshold=LOW_T)
        assert new is None
        assert await _field(db, "GRAD-HA-001", "provenance") == "hand-authored"

    @pytest.mark.asyncio
    async def test_idempotent_no_double_flip(self, db: Neo4jConnection) -> None:
        await _seed_proposed(db, "GRAD-IDEM-001", pos=10, neg=0)
        first = await db.evaluate_and_flip_graduation("GRAD-IDEM-001", threshold=LOW_T)
        assert first == "graduation_pending"
        second = await db.evaluate_and_flip_graduation("GRAD-IDEM-001", threshold=LOW_T)
        assert second is None  # already pending: the crossing is not re-entrant
        assert await _field(db, "GRAD-IDEM-001", "provenance") == "graduation_pending"

    @pytest.mark.asyncio
    async def test_authority_not_promoted_on_flip(self, db: Neo4jConnection) -> None:
        await _seed_proposed(db, "GRAD-AUTH-001", pos=4, neg=0)
        await db.evaluate_and_flip_graduation("GRAD-AUTH-001", threshold=LOW_T)
        # The human gate (6.3b/c) promotes authority, not the statistical crossing.
        assert await _field(db, "GRAD-AUTH-001", "authority") == "ai-provisional"


class TestGraduationViaFeedback:
    """The crossing is checked after a /feedback increment (the daemon path)."""

    @pytest.mark.asyncio
    async def test_feedback_increment_triggers_flip_at_real_threshold(self, db: Neo4jConnection) -> None:
        # Seed a proposed rule one short of the real threshold (50), then a single
        # positive feedback crosses it -> graduation_pending. Exercises the db hook
        # /feedback uses (increment then evaluate_and_flip at the default threshold).
        await _seed_proposed(db, "GRAD-FB-001", pos=49, neg=0)  # n=49, one short of 50
        await db.increment_positive("GRAD-FB-001")  # -> n=50, ratio=1.0
        new = await db.evaluate_and_flip_graduation("GRAD-FB-001")  # default threshold
        assert new == "graduation_pending"
        assert await _field(db, "GRAD-FB-001", "provenance") == "graduation_pending"
