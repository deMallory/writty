"""Phase 6 promotion: authority stamping (ITEM 2) and observation-count reset (ITEM 3).

ITEM 2 (RED today):
    promote_candidate must stamp authority="ai-promoted" on the promoted node.
    Currently it never sets authority, so the node keeps "ai-provisional" from
    propose-time (writ/promotion.py does not write authority= in the edited dict).

ITEM 3 (mixed RED/GREEN today):
    promote_candidate must RESET times_seen_positive and times_seen_negative to 0
    when graduated_via=="human-edit" AND the normalized statement changed
    (lowercase + collapsed-whitespace comparison of edited vs pre-edit statement).
    Approve-as-is and human-edit that leaves the statement normalized-equal must
    PRESERVE existing counters.

Fixture style matches tests/test_phase6_promote.py (same _rule(), _accepting_pipeline(),
_seed_pending() pattern, same db fixture with Neo4j skip-if-unreachable).

times_seen seeding strategy
---------------------------
`db.create_rule` calls `_node_write_spec` which passes ALL data-dict keys as props
via `SET r += $props`, so times_seen_positive/negative CAN be written through
create_rule if they are in the data dict. However, the parity/export machinery
treats them as RUNTIME_EXEMPT_PROPS (schema.py:708), which means a round-trip
through import-markdown resets them to absent. The safest seed pattern (copied
from the existing test_phase6_promote.py::_seed_pending) is:
  1. db.create_rule(...) to create the node
  2. Direct Cypher SET to write times_seen_positive + times_seen_negative + provenance
This avoids any question about whether create_rule propagates RUNTIME_EXEMPT fields.

db.get_rule returns dict(record["r"]) which is the raw Neo4j node -- all properties
including times_seen_positive/negative are present once written by the Cypher SET.
promote_candidate calls db.get_rule to build `edited`, so the counters travel into
the create_rule call via `SET r += $props` unless explicitly overwritten.
"""

from __future__ import annotations

from dataclasses import dataclass
from unittest.mock import MagicMock

import numpy as np
import pytest
import pytest_asyncio

from writ.config import get_neo4j_password, get_neo4j_uri, get_neo4j_user
from writ.graph.db import Neo4jConnection

CAND = "PROMO-AUTH-001"


@dataclass
class Scored:
    rule_id: str
    score: float


def _rule(rid: str) -> dict:
    return {
        "rule_id": rid, "domain": "Testing", "severity": "high", "scope": "slice",
        "trigger": "When a function exceeds the agreed line budget.",
        "statement": "A function must not exceed thirty lines of logic.",
        "violation": "A function body is forty-five lines.",
        "pass_example": "The function is decomposed into helpers.",
        "enforcement": "Reviewed in the per-slice findings table.",
        "rationale": "Long functions resist testing and reuse.",
        "last_validated": "2026-03-15", "authority": "ai-provisional",
    }


def _accepting_pipeline(candidate_id: str):
    """structural_gate accepts: the only similar hit is the candidate itself."""
    p = MagicMock()
    p._model.encode.return_value = np.zeros(384, dtype=np.float32)
    p._vector.search.return_value = [Scored(candidate_id, 0.99)]
    p._metadata = {}
    p._cache.get_neighbors.return_value = []
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
        await s.run("MATCH (n:Rule {rule_id: $id}) DETACH DELETE n", id=CAND)
    yield conn
    async with conn._driver.session(database=conn._database) as s:
        await s.run("MATCH (n:Rule {rule_id: $id}) DETACH DELETE n", id=CAND)
    await conn.close()


async def _field(db: Neo4jConnection, rule_id: str, prop: str):
    """Read a single property from the graph node."""
    async with db._driver.session(database=db._database) as s:
        r = await s.run(
            f"MATCH (r:Rule {{rule_id: $id}}) RETURN r.{prop} AS v", id=rule_id
        )
        rec = await r.single()
        return rec["v"] if rec else None


async def _seed_pending(
    db: Neo4jConnection,
    times_positive: int = 50,
    times_negative: int = 3,
) -> None:
    """Create a graduation_pending Rule with configurable observation counters.

    Two-step: create_rule (establishes the node), then direct Cypher SET (writes
    provenance + RUNTIME_EXEMPT observation counts that create_rule would not
    preserve through a re-import).
    """
    await db.create_rule(_rule(CAND), source_origin="graph-authored")  # -> proposed
    async with db._driver.session(database=db._database) as s:
        await s.run(
            "MATCH (r:Rule {rule_id: $id}) "
            "SET r.provenance = 'graduation_pending', "
            "r.times_seen_positive = $pos, "
            "r.times_seen_negative = $neg",
            id=CAND,
            pos=times_positive,
            neg=times_negative,
        )


# ---------------------------------------------------------------------------
# ITEM 2: authority="ai-promoted" stamped on promotion
# RED today: promote_candidate never writes authority, so the node stays
# "ai-provisional" after promotion.
# ---------------------------------------------------------------------------

class TestPromoteSetsAuthorityAiPromoted:

    @pytest.mark.asyncio
    async def test_promote_sets_authority_ai_promoted(
        self, db: Neo4jConnection, tmp_path
    ) -> None:
        """approve-as-is promotion stamps authority='ai-promoted' on the node.

        RED today: promote_candidate does not set authority; the node retains
        'ai-provisional' from seed-time (writ/promotion.py:206 sets provenance +
        graduated_via but no authority= line).
        """
        from writ.promotion import promote_candidate
        await _seed_pending(db)
        result = await promote_candidate(
            CAND, _accepting_pipeline(CAND), db, tmp_path
        )
        assert result["promoted"] is True, f"Unexpected rejection: {result}"
        authority = await _field(db, CAND, "authority")
        assert authority == "ai-promoted", (
            f"Expected authority='ai-promoted' after approve-as-is promotion, "
            f"got {authority!r}. Add `edited['authority'] = 'ai-promoted'` in "
            f"promote_candidate (writ/promotion.py) before the create_rule call."
        )

    @pytest.mark.asyncio
    async def test_promote_edit_also_sets_ai_promoted(
        self, db: Neo4jConnection, tmp_path
    ) -> None:
        """human-edit promotion also stamps authority='ai-promoted'.

        Even when the human edits the text, the authority comes from the promotion
        event, not the original proposal. RED today for same reason.
        """
        from writ.promotion import promote_candidate
        await _seed_pending(db)
        new_stmt = "A function must not exceed twenty-five lines of logic."
        result = await promote_candidate(
            CAND, _accepting_pipeline(CAND), db, tmp_path,
            edited_fields={"statement": new_stmt},
        )
        assert result["promoted"] is True, f"Unexpected rejection: {result}"
        authority = await _field(db, CAND, "authority")
        assert authority == "ai-promoted", (
            f"Expected authority='ai-promoted' after human-edit promotion, "
            f"got {authority!r}."
        )


# ---------------------------------------------------------------------------
# ITEM 3: observation-count reset on statement-changing human-edit
# ---------------------------------------------------------------------------

def _normalize_statement(s: str) -> str:
    """Lowercase + collapse whitespace. Must match the implementation's normalization."""
    import re
    return re.sub(r"\s+", " ", s.strip().lower())


ORIGINAL_STATEMENT = "A function must not exceed thirty lines of logic."
CHANGED_STATEMENT = "Every function body must remain under twenty lines."
# Same statement, only case and extra whitespace differ -- normalized-equal.
WHITESPACE_ONLY_STATEMENT = "  A Function  Must Not Exceed  Thirty  Lines  Of  Logic.  "


class TestObservationCountReset:

    @pytest.mark.asyncio
    async def test_promote_edit_changing_statement_resets_observations(
        self, db: Neo4jConnection, tmp_path
    ) -> None:
        """human-edit that changes the statement resets times_seen_* to 0.

        RED today: promote_candidate does not inspect the statement diff; it
        passes the full `edited` dict into create_rule unchanged, so the
        counters travel through unmodified (open question noted in the docstring
        at promotion.py:177-180).

        Precondition: verify the two statements are NOT normalized-equal.
        """
        assert _normalize_statement(ORIGINAL_STATEMENT) != _normalize_statement(CHANGED_STATEMENT), (
            "Test setup error: ORIGINAL_STATEMENT and CHANGED_STATEMENT normalize to the same string"
        )

        from writ.promotion import promote_candidate
        await _seed_pending(db, times_positive=50, times_negative=3)

        result = await promote_candidate(
            CAND, _accepting_pipeline(CAND), db, tmp_path,
            edited_fields={"statement": CHANGED_STATEMENT},
        )
        assert result["promoted"] is True, f"Unexpected rejection: {result}"

        pos = await _field(db, CAND, "times_seen_positive")
        neg = await _field(db, CAND, "times_seen_negative")
        assert pos == 0, (
            f"Expected times_seen_positive=0 after statement-changing edit, got {pos}. "
            f"promote_candidate must detect the normalized statement change and zero "
            f"the counters before calling create_rule."
        )
        assert neg == 0, (
            f"Expected times_seen_negative=0 after statement-changing edit, got {neg}."
        )

    @pytest.mark.asyncio
    async def test_promote_edit_not_touching_statement_preserves_observations(
        self, db: Neo4jConnection, tmp_path
    ) -> None:
        """human-edit that changes only a non-statement field preserves counters.

        GREEN today (nothing resets, so 50 survives) and must stay GREEN after
        the statement-reset feature lands. This locks the no-reset case.
        """
        from writ.promotion import promote_candidate
        await _seed_pending(db, times_positive=50, times_negative=3)

        result = await promote_candidate(
            CAND, _accepting_pipeline(CAND), db, tmp_path,
            edited_fields={"pass_example": "Decomposed into three focused helpers."},
        )
        assert result["promoted"] is True, f"Unexpected rejection: {result}"

        pos = await _field(db, CAND, "times_seen_positive")
        assert pos == 50, (
            f"Expected times_seen_positive=50 (unchanged) when only pass_example was "
            f"edited, got {pos}."
        )

    @pytest.mark.asyncio
    async def test_promote_approve_asis_preserves_observations(
        self, db: Neo4jConnection, tmp_path
    ) -> None:
        """approve-as-is preserves existing observation counters.

        GREEN today (no reset logic exists) and must stay GREEN. Locks the
        approve-as-is counter-preservation invariant.
        """
        from writ.promotion import promote_candidate
        await _seed_pending(db, times_positive=50, times_negative=3)

        result = await promote_candidate(
            CAND, _accepting_pipeline(CAND), db, tmp_path,
            edited_fields=None,
        )
        assert result["promoted"] is True, f"Unexpected rejection: {result}"

        pos = await _field(db, CAND, "times_seen_positive")
        assert pos == 50, (
            f"Expected times_seen_positive=50 (unchanged) after approve-as-is, "
            f"got {pos}."
        )

    @pytest.mark.asyncio
    async def test_promote_edit_whitespace_only_statement_preserves(
        self, db: Neo4jConnection, tmp_path
    ) -> None:
        """human-edit with only whitespace/case changes to statement preserves counters.

        The implementation must use normalized comparison (lowercase + collapsed
        whitespace), NOT raw string equality. A statement that differs only in
        whitespace/case from the original is NOT a substantive change -- counters
        must be preserved.

        Precondition: verify the whitespace-only variant is normalized-equal to the
        original.
        """
        assert (
            _normalize_statement(ORIGINAL_STATEMENT)
            == _normalize_statement(WHITESPACE_ONLY_STATEMENT)
        ), (
            "Test setup error: WHITESPACE_ONLY_STATEMENT does not normalize to the "
            "same value as ORIGINAL_STATEMENT"
        )

        from writ.promotion import promote_candidate
        await _seed_pending(db, times_positive=50, times_negative=3)

        result = await promote_candidate(
            CAND, _accepting_pipeline(CAND), db, tmp_path,
            edited_fields={"statement": WHITESPACE_ONLY_STATEMENT},
        )
        assert result["promoted"] is True, f"Unexpected rejection: {result}"

        pos = await _field(db, CAND, "times_seen_positive")
        assert pos == 50, (
            f"Expected times_seen_positive=50 when statement change is whitespace-only "
            f"(normalized-equal), got {pos}. Implementation must normalize before "
            f"comparing: re.sub(r'\\\\s+', ' ', s.strip().lower())."
        )
