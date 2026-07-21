"""Phase 6.3c: the human GATES and AUTHORS the canon write (edit-at-gate, not approve-only).

promote_candidate is the business logic AFTER the token gate (the token lives on the
server route, tested separately). With the 6.3b artifact in front of them, the human
approves the graduation_pending candidate as-is, or edits its wording/examples; the
(edited) text re-runs the structural gate, then the node is stamped provenance=graduated
+ graduated_via and EXPORTED to its bible/ source so markdown is source-of-truth at rest.

RED until 6.3c lands (writ.promotion.promote_candidate + graduated_via field).
"""
from __future__ import annotations

from dataclasses import dataclass
from unittest.mock import MagicMock

import numpy as np
import pytest
import pytest_asyncio

from writ.config import get_neo4j_password, get_neo4j_uri, get_neo4j_user
from writ.graph.db import Neo4jConnection
from writ.graph.ingest import parse_nodes_from_file

CAND = "PROMO-CAND-001"


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
    """structural_gate accepts: the only similar hit is the candidate itself (excluded),
    no metadata entry (conflict check no-ops), no vague language."""
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


async def _field(db: Neo4jConnection, rule_id: str, field: str):
    async with db._driver.session(database=db._database) as s:
        r = await s.run(f"MATCH (r:Rule {{rule_id: $id}}) RETURN r.{field} AS v", id=rule_id)
        rec = await r.single()
        return rec["v"] if rec else None


async def _seed_pending(db: Neo4jConnection) -> None:
    await db.create_rule(_rule(CAND), source_origin="graph-authored")  # -> proposed
    async with db._driver.session(database=db._database) as s:
        await s.run(
            "MATCH (r:Rule {rule_id: $id}) SET r.provenance='graduation_pending', "
            "r.times_seen_positive=60, r.times_seen_negative=2", id=CAND,
        )


# --- schema: graduated_via ---------------------------------------------------

class TestGraduatedViaField:
    def test_field_on_rule_default_none(self) -> None:
        from writ.graph.schema import Rule
        assert "graduated_via" in Rule.model_fields
        assert Rule(**_rule("X-RULE-001")).graduated_via is None

    def test_invalid_value_rejected(self) -> None:
        from pydantic import ValidationError
        from writ.graph.schema import Rule
        with pytest.raises(ValidationError):
            Rule(**{**_rule("X-RULE-002"), "graduated_via": "auto-approved"})

    def test_valid_values_accepted(self) -> None:
        from writ.graph.schema import Rule
        for v in ("human-approve-asis", "human-edit"):
            assert Rule(**{**_rule("X-RULE-003"), "graduated_via": v}).graduated_via == v

    def test_graduated_via_round_trips_export(self) -> None:
        from writ.export import node_to_yaml_frontmatter
        node = {"skill_id": "X-SKILL-001", "domain": "process", "severity": "high",
                "scope": "task", "trigger": "t", "statement": "s", "rationale": "r",
                "provenance": "graduated", "graduated_via": "human-edit"}
        out = node_to_yaml_frontmatter(node, node_type="Skill")
        assert "graduated_via: human-edit" in out


# --- business logic: promote_candidate ---------------------------------------

class TestPromoteCandidate:
    @pytest.mark.asyncio
    async def test_approve_as_is_graduates_and_exports(self, db: Neo4jConnection, tmp_path) -> None:
        from writ.promotion import promote_candidate
        await _seed_pending(db)
        result = await promote_candidate(CAND, _accepting_pipeline(CAND), db, tmp_path)
        assert result["promoted"] is True
        assert result["graduated_via"] == "human-approve-asis"
        assert await _field(db, CAND, "provenance") == "graduated"
        assert await _field(db, CAND, "graduated_via") == "human-approve-asis"
        assert (tmp_path / "methodology" / f"{CAND}.md").exists()

    @pytest.mark.asyncio
    async def test_edit_writes_edited_text(self, db: Neo4jConnection, tmp_path) -> None:
        from writ.promotion import promote_candidate
        await _seed_pending(db)
        new_stmt = "A function must not exceed twenty-five lines of logic."
        result = await promote_candidate(
            CAND, _accepting_pipeline(CAND), db, tmp_path,
            edited_fields={"statement": new_stmt},
        )
        assert result["promoted"] is True
        assert result["graduated_via"] == "human-edit"
        assert await _field(db, CAND, "statement") == new_stmt
        assert await _field(db, CAND, "provenance") == "graduated"
        md = (tmp_path / "methodology" / f"{CAND}.md").read_text(encoding="utf-8")
        assert new_stmt in md

    @pytest.mark.asyncio
    async def test_only_graduation_pending_promotes(self, db: Neo4jConnection, tmp_path) -> None:
        from writ.promotion import promote_candidate
        await db.create_rule(_rule(CAND), source_origin="graph-authored")  # proposed, NOT pending
        result = await promote_candidate(CAND, _accepting_pipeline(CAND), db, tmp_path)
        assert result["promoted"] is False
        assert await _field(db, CAND, "provenance") == "proposed"
        assert not (tmp_path / "methodology" / f"{CAND}.md").exists()

    @pytest.mark.asyncio
    async def test_broken_edit_rejected_no_canon(self, db: Neo4jConnection, tmp_path) -> None:
        from writ.promotion import promote_candidate
        await _seed_pending(db)
        # "Consider" is a vague disqualifier -> structural gate rejects the edited text.
        result = await promote_candidate(
            CAND, _accepting_pipeline(CAND), db, tmp_path,
            edited_fields={"statement": "Consider keeping functions short."},
        )
        assert result["promoted"] is False
        assert result.get("reasons")
        assert await _field(db, CAND, "provenance") == "graduation_pending"  # unchanged
        assert not (tmp_path / "methodology" / f"{CAND}.md").exists()

    @pytest.mark.asyncio
    async def test_exported_node_reimports_noop(self, db: Neo4jConnection, tmp_path) -> None:
        from writ.promotion import promote_candidate
        await _seed_pending(db)
        await promote_candidate(
            CAND, _accepting_pipeline(CAND), db, tmp_path,
            edited_fields={"statement": "A function must not exceed twenty lines."},
        )
        exported = tmp_path / "methodology" / f"{CAND}.md"
        # (a) the .md is lossless for the source-visible self-authoring fields.
        parsed = parse_nodes_from_file(exported)
        assert len(parsed) == 1
        assert parsed[0]["provenance"] == "graduated"
        assert parsed[0]["graduated_via"] == "human-edit"
        assert parsed[0]["statement"] == "A function must not exceed twenty lines."
        # (b) re-importing the exported node is a no-op: it stays graduated, not reverted.
        clean = {k: v for k, v in parsed[0].items()
                 if k not in ("node_type", "edges") and not k.startswith("_")}
        await db.create_rule(clean, source_origin="ingest")
        assert await _field(db, CAND, "provenance") == "graduated"
        assert await _field(db, CAND, "graduated_via") == "human-edit"
