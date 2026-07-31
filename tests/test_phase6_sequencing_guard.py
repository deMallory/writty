"""Phase 6.5: sequencing guard -- Phase 6 precedes 5.2, and 5.2's provenance-aware parity
clause depends on the 6.1 field + the 6.3a graduation_pending state being recognized.

6.4 pins that `proposed` is parity-exempt. This guard closes the loop by pinning the OTHER
graph-first state -- graduation_pending (introduced by 6.3a) -- as parity-exempt too, and
that the canonical states (graduated / hand-authored) are NOT exempt. That is the exact
dependency 5.2's provenance-aware parity check rests on; if 6.1/6.3a regress, this is RED.
"""
from __future__ import annotations

from pathlib import Path

import pytest
import pytest_asyncio

from writ.config import get_neo4j_password, get_neo4j_uri, get_neo4j_user
from writ.graph.db import Neo4jConnection
from writ.graph.integrity import IntegrityChecker
from writ.graph.methodology_ingest import ingest_path

BIBLE = Path(__file__).resolve().parent.parent / "bible"
PENDING = "ZZZ-PENDING-GUARD-001"
GRADUATED = "ZZZ-GRADUATED-GUARD-001"
SEEDS = [PENDING, GRADUATED]


def _rule(rid: str) -> dict:
    return {
        "rule_id": rid, "domain": "Testing", "severity": "high", "scope": "slice",
        "trigger": "t", "statement": "s", "violation": "v", "pass_example": "p",
        "enforcement": "e", "rationale": "r", "last_validated": "2026-03-15",
    }


def test_graph_first_provenance_is_the_two_transient_states() -> None:
    # The axis 5.2's exemption keys on must be exactly the no-markdown-home states.
    from writ.graph.schema import GRAPH_FIRST_PROVENANCE
    assert set(GRAPH_FIRST_PROVENANCE) == {"proposed", "graduation_pending"}


def test_integrity_imports_the_provenance_axis() -> None:
    # The parity module (5.2's home) must consume the 6.1 axis, not source_origin.
    # It re-exports PARITY_EXEMPT_PROVENANCE rather than GRAPH_FIRST_PROVENANCE
    # itself: parity must also exempt runtime `record` nodes, so the exported name
    # is the wider set (PARITY_EXEMPT_PROVENANCE = GRAPH_FIRST_PROVENANCE |
    # {"record"}, writ/graph/schema.py). Asserting on the old name failed while the
    # contract it stands for -- provenance, not source_origin -- was in fact held.
    import writ.graph.integrity as integ
    from writ.graph.schema import GRAPH_FIRST_PROVENANCE

    assert hasattr(integ, "PARITY_EXEMPT_PROVENANCE")
    assert GRAPH_FIRST_PROVENANCE <= integ.PARITY_EXEMPT_PROVENANCE


@pytest_asyncio.fixture()
async def db_corpus():
    db = Neo4jConnection(get_neo4j_uri(), get_neo4j_user(), get_neo4j_password())
    try:
        async with db._driver.session(database=db._database) as s:
            await (await s.run("RETURN 1 AS ok")).consume()
    except Exception:
        await db.close()
        pytest.skip("Neo4j unreachable")
    await db.clear_all()
    await ingest_path(BIBLE, db)
    yield db
    async with db._driver.session(database=db._database) as s:
        await s.run("MATCH (n) WHERE n.rule_id IN $ids DETACH DELETE n", ids=SEEDS)
    await db.close()


class TestGraduationPendingParityExempt:
    @pytest.mark.asyncio
    async def test_graduation_pending_node_not_flagged(self, db_corpus: Neo4jConnection) -> None:
        # A candidate mid-graduation (proposed -> graduation_pending) still has no markdown
        # home by design; the 5.2 parity check must NOT flag it.
        await db_corpus.create_rule(_rule(PENDING), source_origin="graph-authored")
        await db_corpus.evaluate_and_flip_graduation(PENDING, threshold=0, ratio_min=0.0)
        # threshold=0/ratio=0 with 0 counts still won't flip (n==0); set a crossing first.
        async with db_corpus._driver.session(database=db_corpus._database) as s:
            await s.run(
                "MATCH (r:Rule {rule_id:$id}) SET r.provenance='graduation_pending'", id=PENDING
            )
        checker = IntegrityChecker(db_corpus._driver, db_corpus._database)
        violations = await checker.detect_parity_violations(BIBLE)
        assert PENDING not in {v["id"] for v in violations}

    @pytest.mark.asyncio
    async def test_graduated_without_source_still_flagged(self, db_corpus: Neo4jConnection) -> None:
        # The canonical end-state is NOT exempt: a graduated node with no .md is drift.
        await db_corpus.create_rule({**_rule(GRADUATED), "provenance": "graduated"})
        checker = IntegrityChecker(db_corpus._driver, db_corpus._database)
        violations = await checker.detect_parity_violations(BIBLE)
        assert GRADUATED in {v["id"] for v in violations}
