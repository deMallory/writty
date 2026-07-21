"""Phase 6.1: the `provenance` enum field on the node schema.

Originally a 4-state refinement of 0.10's binary `source_origin` (ingest |
graph-authored); the decision-memory feature later added a 5th `record` state, so
VALID_PROVENANCE now has five members:

    hand-authored      <- ingest, the markdown corpus at rest
    proposed           <- graph-first (/propose, cli add), not yet canonical
    graduation_pending <- crossed the frequency threshold, awaiting the human gate
    graduated          <- human-promoted and exported back to bible/ source
    record             <- runtime decision-memory record node (decision-memory feature)

Design (locked in the Phase 6 plan gate):
- D1: provenance LAYERS on source_origin, it does not replace it. `_node_write_spec`
  derives it (ingest->hand-authored, graph-authored->proposed) unless the parsed
  frontmatter (or an explicit caller) sets it, so a re-ingested `graduated` node keeps
  its lineage instead of reverting to hand-authored.
- D2: export OMITS provenance when it is the default `hand-authored` (zero churn on the
  ~350-file corpus) and WRITES it only for a non-default value (graduated).
- provenance is RUNTIME_EXEMPT like source_origin: reconcile/prop-parity must not clear
  or flag it on the hand-authored corpus (its value is absent from those .md files).

These tests are RED until 6.1 lands.
"""
from __future__ import annotations

import pytest
import pytest_asyncio

from writ.config import get_neo4j_password, get_neo4j_uri, get_neo4j_user
from writ.graph.db import Neo4jConnection


# --- schema / model level (no DB) -------------------------------------------

class TestProvenanceSchema:
    def test_valid_provenance_set(self) -> None:
        from writ.graph.schema import VALID_PROVENANCE
        assert set(VALID_PROVENANCE) == {
            "hand-authored", "proposed", "graduation_pending", "graduated", "record"
        }, (
            "VALID_PROVENANCE drifted from the reviewed 5-member baseline (the 4 "
            "original states + `record` from the decision-memory feature); got "
            f"{sorted(VALID_PROVENANCE)!r}"
        )

    def test_rule_model_has_provenance_field(self) -> None:
        from writ.graph.schema import Rule
        assert "provenance" in Rule.model_fields

    def test_every_node_model_carries_provenance(self) -> None:
        from writ.graph.schema import NODE_TYPE_MODELS
        missing = [
            name for name, model in NODE_TYPE_MODELS.items()
            if "provenance" not in model.model_fields
        ]
        assert not missing, f"node models missing provenance: {missing}"

    def test_rule_defaults_to_hand_authored(self, valid_rule_data: dict) -> None:
        from writ.graph.schema import Rule
        assert Rule(**valid_rule_data).provenance == "hand-authored"

    def test_invalid_provenance_value_rejected(self, valid_rule_data: dict) -> None:
        from pydantic import ValidationError
        from writ.graph.schema import Rule
        with pytest.raises(ValidationError):
            Rule(**{**valid_rule_data, "provenance": "human-typo"})

    def test_graduated_is_a_valid_provenance_value(self, valid_rule_data: dict) -> None:
        from writ.graph.schema import Rule
        assert Rule(**{**valid_rule_data, "provenance": "graduated"}).provenance == "graduated"


class TestProvenanceRuntimeExempt:
    """provenance is graph-side state, absent from hand-authored .md files; reconcile and
    prop-parity must treat it like source_origin (never clear, never flag)."""

    def test_provenance_in_runtime_exempt_props(self) -> None:
        from writ.graph.schema import RUNTIME_EXEMPT_PROPS
        assert "provenance" in RUNTIME_EXEMPT_PROPS

    def test_provenance_not_in_managed_props(self) -> None:
        from writ.graph.schema import MANAGED_PROP_NAMES
        assert "provenance" not in MANAGED_PROP_NAMES


# --- write-path level (live Neo4j) ------------------------------------------

def _make_rule(rule_id: str) -> dict:
    return {
        "rule_id": rule_id, "domain": "Test", "severity": "medium", "scope": "file",
        "trigger": "t", "statement": "s", "violation": "v", "pass_example": "p",
        "enforcement": "e", "rationale": "r", "mandatory": False,
        "confidence": "production-validated", "evidence": "doc:original-bible",
        "last_validated": "2026-03-15",
    }


def _make_skill(skill_id: str) -> dict:
    return {
        "skill_id": skill_id, "domain": "process", "severity": "high", "scope": "task",
        "trigger": "t", "statement": "s", "rationale": "r", "last_validated": "2026-03-15",
    }


@pytest_asyncio.fixture()
async def db():
    conn = Neo4jConnection(get_neo4j_uri(), get_neo4j_user(), get_neo4j_password())
    await conn.clear_all()
    yield conn
    await conn.clear_all()
    await conn.close()


async def _node_prov(db: Neo4jConnection, label: str, id_field: str, node_id: str) -> str | None:
    async with db._driver.session(database=db._database) as s:
        r = await s.run(
            f"MATCH (n:{label} {{{id_field}: $id}}) RETURN n.provenance AS p", id=node_id
        )
        rec = await r.single()
        return rec["p"] if rec else None


class TestProvenanceWritePath:
    @pytest.mark.asyncio
    async def test_create_rule_defaults_to_hand_authored(self, db: Neo4jConnection) -> None:
        await db.create_rule(_make_rule("PROV-RULE-HA-001"))
        assert await _node_prov(db, "Rule", "rule_id", "PROV-RULE-HA-001") == "hand-authored"

    @pytest.mark.asyncio
    async def test_create_methodology_node_defaults_to_hand_authored(self, db: Neo4jConnection) -> None:
        await db.create_methodology_node("Skill", _make_skill("PROV-SKILL-HA-001"))
        assert await _node_prov(db, "Skill", "skill_id", "PROV-SKILL-HA-001") == "hand-authored"

    @pytest.mark.asyncio
    async def test_graph_authored_derives_proposed(self, db: Neo4jConnection) -> None:
        await db.create_rule(_make_rule("PROV-RULE-PROP-001"), source_origin="graph-authored")
        assert await _node_prov(db, "Rule", "rule_id", "PROV-RULE-PROP-001") == "proposed"

    @pytest.mark.asyncio
    async def test_frontmatter_provenance_wins_over_derivation(self, db: Neo4jConnection) -> None:
        # A re-ingested graduated node (source_origin='ingest') carries
        # provenance='graduated' in its frontmatter; that must survive, NOT revert to
        # the ingest-default hand-authored (D1: lineage preserved across re-ingest).
        data = {**_make_rule("PROV-RULE-GRAD-001"), "provenance": "graduated"}
        await db.create_rule(data)  # default ingest origin
        assert await _node_prov(db, "Rule", "rule_id", "PROV-RULE-GRAD-001") == "graduated"

    @pytest.mark.asyncio
    async def test_batch_create_nodes_stamps_provenance(self, db: Neo4jConnection) -> None:
        await db.batch_create_nodes([("Rule", _make_rule("PROV-RULE-BATCH-001"))])
        assert await _node_prov(db, "Rule", "rule_id", "PROV-RULE-BATCH-001") == "hand-authored"


# --- export round-trip (D2: default-omit, non-default-write) ----------------

class TestProvenanceExportRoundTrip:
    def test_hand_authored_omitted_from_frontmatter(self) -> None:
        from writ.export import node_to_yaml_frontmatter
        node = {**_make_skill("PROV-SKILL-OMIT-001"), "provenance": "hand-authored"}
        out = node_to_yaml_frontmatter(node, node_type="Skill")
        assert "provenance" not in out, (
            "hand-authored is the default; emitting it would churn every corpus file"
        )

    def test_graduated_written_to_frontmatter(self) -> None:
        from writ.export import node_to_yaml_frontmatter
        node = {**_make_skill("PROV-SKILL-GRAD-001"), "provenance": "graduated"}
        out = node_to_yaml_frontmatter(node, node_type="Skill")
        assert "provenance: graduated" in out

    def test_graduated_roundtrips_through_parse(self, tmp_path) -> None:
        from writ.export import node_to_yaml_frontmatter
        from writ.graph.ingest import parse_nodes_from_file
        node = {
            **_make_skill("PROV-SKILL-RT-001"),
            "provenance": "graduated",
            "body": "Body text.",
        }
        md = node_to_yaml_frontmatter(node, node_type="Skill")
        f = tmp_path / "PROV-SKILL-RT-001.md"
        f.write_text(md, encoding="utf-8")
        parsed = parse_nodes_from_file(f)
        assert len(parsed) == 1
        assert parsed[0].get("provenance") == "graduated"
