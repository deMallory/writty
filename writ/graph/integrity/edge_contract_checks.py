"""Edge-direction/contract invariants + denormalized edge-parity.

Moved verbatim from the former writ/graph/integrity.py (Wave 2 mixin split); methods read self._driver / self._database set by IntegrityChecker.__init__."""
from __future__ import annotations

from writ.graph.integrity._common import (
    _GRAPH_ID_COALESCE,
)


class EdgeContractChecksMixin:
    async def detect_dispatch_invokes_invariant(self) -> dict | None:
        """Enforce the one-level constraint at the edge level (1.3b).

        DISPATCHES means "spawn a SubagentRole"; INVOKES means "the orchestrator
        applies this methodology inline (one level)". So every DISPATCHES edge
        must target a SubagentRole, and every INVOKES edge must target a
        non-SubagentRole node. A DISPATCHES to a Playbook/Skill/Technique is the
        mis-target 1.3b corrects; an INVOKES to a role inverts the meaning.
        Returns None when clean, else {"dispatch_to_non_role": [...],
        "invokes_to_role": [...]} as (src, tgt, tgt_label) tuples.
        """
        if self._driver is None:
            return None
        a_id = _GRAPH_ID_COALESCE.format(v="a")
        b_id = _GRAPH_ID_COALESCE.format(v="b")
        async with self._driver.session(database=self._database) as session:
            res = await session.run(
                f"MATCH (a)-[:DISPATCHES]->(b) WHERE labels(b)[0] <> 'SubagentRole' "
                f"RETURN {a_id} AS src, {b_id} AS tgt, labels(b)[0] AS label"
            )
            dispatch_to_non_role = [
                (r["src"], r["tgt"], r["label"]) async for r in res
            ]
            res = await session.run(
                f"MATCH (a)-[:INVOKES]->(b) WHERE labels(b)[0] = 'SubagentRole' "
                f"RETURN {a_id} AS src, {b_id} AS tgt, labels(b)[0] AS label"
            )
            invokes_to_role = [(r["src"], r["tgt"], r["label"]) async for r in res]
        if not dispatch_to_non_role and not invokes_to_role:
            return None
        return {
            "dispatch_to_non_role": sorted(dispatch_to_non_role),
            "invokes_to_role": sorted(invokes_to_role),
        }

    async def detect_teaches_source_invariant(self) -> list[dict]:
        """Enforce the TEACHES-direction convention (1.3c).

        "A TEACHES B" means the instructional node A (Skill/Playbook/Technique)
        imparts the lesson/subject B. A Rule is a terse enforced mandate: it is
        what gets taught, never the teacher. So a TEACHES edge must NEVER
        originate from a Rule. This pins the convention the 1.3c audit lacked
        (which let it mis-call the PBK-AUTHOR-001 edges "inverted"). Returns the
        offending (src, tgt) edges; empty when clean.
        """
        if self._driver is None:
            return []
        a_id = _GRAPH_ID_COALESCE.format(v="a")
        b_id = _GRAPH_ID_COALESCE.format(v="b")
        async with self._driver.session(database=self._database) as session:
            res = await session.run(
                f"MATCH (a:Rule)-[:TEACHES]->(b) RETURN {a_id} AS src, {b_id} AS tgt"
            )
            return [{"src": r["src"], "tgt": r["tgt"]} async for r in res]

    async def _field_vs_edges_parity(self, query: str) -> list[dict] | None:
        """Compare a denormalized node field (a cached list) against the
        authoritative edge set, per row of `query` (which MUST return `id`,
        `field`, `edges`). Reports [{node_id, missing_from_field, extra_in_field}]
        where the cache diverges from the edges; None when every node is in sync.
        Single source for the counter_nodes + dispatched_by parity checks (3.5b)."""
        if self._driver is None:
            return None
        out: list[dict] = []
        async with self._driver.session(database=self._database) as session:
            res = await session.run(query)
            async for r in res:
                field = set(r["field"] or [])
                edges = {x for x in (r["edges"] or []) if x}
                if field != edges:
                    out.append({
                        "node_id": r["id"],
                        "missing_from_field": sorted(edges - field),
                        "extra_in_field": sorted(field - edges),
                    })
        return out or None

    async def detect_counter_nodes_parity(self) -> list[dict] | None:
        """3.5b: an AntiPattern's `counter_nodes` field == its COUNTERS edge set.

        The denormalized list drifts as a strict subset of the explicitly
        declared COUNTERS edges (the edges are source of truth). Returns
        [{node_id, missing_from_field, extra_in_field}]; None when clean.
        """
        tid = _GRAPH_ID_COALESCE.format(v="t")
        return await self._field_vs_edges_parity(
            f"MATCH (a:AntiPattern) OPTIONAL MATCH (a)-[:COUNTERS]->(t) "
            f"RETURN a.antipattern_id AS id, a.counter_nodes AS field, "
            f"collect(DISTINCT {tid}) AS edges ORDER BY id"
        )

    async def detect_dispatched_by_parity(self) -> list[dict] | None:
        """3.5b: a SubagentRole's `dispatched_by` field == its DISPATCHES sources.

        Reverse-edge cache that drifts as a strict subset of the dispatchers
        declaring `DISPATCHES -> role` (the edges are source of truth). Returns
        [{node_id, missing_from_field, extra_in_field}]; None when clean.
        """
        sid = _GRAPH_ID_COALESCE.format(v="src")
        return await self._field_vs_edges_parity(
            f"MATCH (r:SubagentRole) OPTIONAL MATCH (src)-[:DISPATCHES]->(r) "
            f"RETURN r.role_id AS id, r.dispatched_by AS field, "
            f"collect(DISTINCT {sid}) AS edges ORDER BY id"
        )
