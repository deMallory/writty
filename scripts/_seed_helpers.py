"""Shared helpers for the one-off scripts/seed_phase_*.py rulebook seeders.

Both fragments below were inlined byte-identically in all 10 seed_phase scripts;
this module is their single source. Each seed script keeps its own _rule factory
(per-phase domain), RULES list, print format, counters, and pre/post steps.
"""
from __future__ import annotations

from writ.config import get_neo4j_password, get_neo4j_uri, get_neo4j_user
from writ.graph.db import Neo4jConnection


def connect() -> Neo4jConnection:
    """The seed scripts' shared env-configured Neo4j connection."""
    return Neo4jConnection(get_neo4j_uri(), get_neo4j_user(), get_neo4j_password())


async def upsert_rule(session, rule: dict) -> bool:
    """MERGE a Rule by rule_id and SET all other props. Returns True if the rule
    already existed (so callers can tally created vs updated). Mirrors the block
    every seed_phase_*.py inlined."""
    result = await session.run(
        "MATCH (r:Rule {rule_id: $rid}) RETURN r.rule_id AS x", rid=rule["rule_id"]
    )
    existed = await result.single() is not None
    props = {k: v for k, v in rule.items() if k != "rule_id"}
    await session.run(
        """
        MERGE (r:Rule {rule_id: $rid})
        SET r += $props
        """,
        rid=rule["rule_id"], props=props,
    )
    return existed
