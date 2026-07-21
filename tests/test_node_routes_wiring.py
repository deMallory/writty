"""Tests for Plan commit 2 (node_routes wiring) and commit 3 (authority
forwarding).

Targets (none exist yet -- RED before implementation):
  - writ.graph.db.Neo4jConnection.get_category_routes_by_node
  - writ.retrieval.pipeline.build_pipeline calling/guarding on that method
  - writ.retrieval.pipeline.build_pipeline(..., authority_preference_threshold=...)

Read-only against the live migrated graph; skip-if-empty mirrors the
`db` fixture posture in benchmarks/bench_targets.py:88-96. No wipe, no
clear_all() anywhere in this file (plan hard constraint: no new
graph-wipe path).
"""
from __future__ import annotations

import pytest
import pytest_asyncio

from writ.config import get_neo4j_password, get_neo4j_uri, get_neo4j_user
from writ.graph.db import Neo4jConnection
from writ.retrieval.pipeline import _load_candidates, build_pipeline

# All async tests share the module-scoped event loop so that the
# module-scoped async `db` fixture works correctly (mirrors bench_targets.py).
pytestmark = pytest.mark.asyncio(loop_scope="module")

NEO4J_URI = get_neo4j_uri()
NEO4J_USER = get_neo4j_user()
NEO4J_PASSWORD = get_neo4j_password()


@pytest_asyncio.fixture(scope="module", loop_scope="module")
async def db():
    """Shared, read-only Neo4j connection. Does NOT clear the database."""
    conn = Neo4jConnection(NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD)
    count = await conn.count_rules()
    if count == 0:
        pytest.skip("Neo4j has no rules. Run: `writ import-markdown`")
    yield conn
    await conn.close()


# ---------------------------------------------------------------------------
# Commit 2: get_category_routes_by_node bulk BELONGS_TO map
# ---------------------------------------------------------------------------

class TestGetCategoryRoutesByNode:

    async def test_get_category_routes_by_node_covers_all_candidates(self, db) -> None:
        """The bulk map must cover EVERY candidate id build_pipeline loads
        (Rule + all 5 retrievable methodology labels), each with a
        non-empty routes list -- proving coverage across labels, not just
        Rule.
        """
        _all_candidates, rule_metadata = await _load_candidates(db)

        routes_map = await db.get_category_routes_by_node()

        assert isinstance(routes_map, dict)
        assert routes_map, "routes map must be non-empty on a categorized graph"

        missing = [rid for rid in rule_metadata if not routes_map.get(rid)]
        assert not missing, (
            f"{len(missing)} candidate id(s) have no routes entry in the "
            f"bulk map (first few: {missing[:5]})"
        )

    async def test_no_methodology_node_is_semantic_routed(self, db) -> None:
        """Zero-delta invariant pin. Wiring node_routes flips the default
        Stage-1 filter from a hard allowed_types={"Rule"} (legacy excludes ALL
        methodology labels unconditionally) to a route filter, so a methodology
        node (Skill/Playbook/Technique/AntiPattern/ForbiddenResponse) would
        newly surface in default semantic queries IF its Category routes include
        'semantic'. The 237==237 zero-delta only holds because no methodology
        category is semantic-routed today. Pin it so a future re-categorization
        that would widen default output fails here loudly.
        """
        all_candidates, _rule_metadata = await _load_candidates(db)
        routes_map = await db.get_category_routes_by_node()
        offenders = [
            c["rule_id"]
            for c in all_candidates
            if c.get("node_type", "Rule") != "Rule"
            and "semantic" in (routes_map.get(c["rule_id"]) or [])
        ]
        assert not offenders, (
            f"{len(offenders)} methodology node(s) are semantic-routed and would "
            f"newly surface in default queries (legacy excluded all non-Rule): "
            f"{offenders[:5]}"
        )


# ---------------------------------------------------------------------------
# Commit 2: build_pipeline wiring guards
# ---------------------------------------------------------------------------

class TestBuildPipelineNodeRoutesGuards:

    async def test_build_pipeline_partial_map_falls_back_to_legacy(self, db, monkeypatch, caplog) -> None:
        """A node_routes map missing a candidate id is an INCOMPLETE corpus
        (drifted, or a graph-authored rule from `writ add`/`/propose` that has
        no Category), not "no routing data". build_pipeline must NOT crash --
        it runs inside the FastAPI lifespan, so a raise would crash-loop the
        daemon. It falls back to the legacy Stage-1 filter (`_node_routes` None,
        behaviorally identical to the route map on a fully categorized corpus)
        and logs a WARNING naming the gap.
        """
        import logging  # noqa: PLC0415

        pytest.importorskip("onnxruntime")  # build_pipeline needs the embedding model
        _all_candidates, rule_metadata = await _load_candidates(db)
        all_ids = list(rule_metadata.keys())
        if not all_ids:
            pytest.skip("No candidates in corpus")

        missing_id = all_ids[0]
        partial_map = {rid: ["semantic"] for rid in all_ids if rid != missing_id}

        async def _fake_get_category_routes_by_node() -> dict:
            return partial_map

        monkeypatch.setattr(
            db, "get_category_routes_by_node",
            _fake_get_category_routes_by_node, raising=False,
        )

        with caplog.at_level(logging.WARNING, logger="writ.retrieval.pipeline"):
            pipeline = await build_pipeline(db)

        assert pipeline._node_routes is None, (
            "an incomplete node_routes map must fall back to legacy (None), "
            "never wire a partial map (which would fail-closed drop candidates)"
        )
        assert "incomplete" in caplog.text.lower(), (
            f"a WARNING naming the incomplete coverage must be logged; "
            f"got: {caplog.text!r}"
        )

    async def test_build_pipeline_empty_map_falls_back_to_legacy(self, db, monkeypatch) -> None:
        """An EMPTY node_routes map ({}) means "no routing data at all" (a
        graph with no BELONGS_TO/Category edges) and must fall back to the
        pre-Phase-0 legacy Rule-only + domain-exclude filter, leaving
        `_node_routes` at None.

        The monkeypatched method must actually be CALLED by build_pipeline.
        Today build_pipeline never calls get_category_routes_by_node at
        all, so the call-count assertion is what makes this test RED
        before the wiring lands -- without it, a build_pipeline that never
        touches node_routes would spuriously look green (it never
        overrides `_node_routes` either way).
        """
        pytest.importorskip("onnxruntime")  # build_pipeline needs the embedding model
        called = {"count": 0}

        async def _fake_get_category_routes_by_node() -> dict:
            called["count"] += 1
            return {}

        monkeypatch.setattr(
            db, "get_category_routes_by_node",
            _fake_get_category_routes_by_node, raising=False,
        )

        pipeline = await build_pipeline(db)

        assert called["count"] == 1, (
            "build_pipeline must call get_category_routes_by_node() exactly once"
        )
        assert pipeline._node_routes is None


# ---------------------------------------------------------------------------
# Commit 3: authority_preference_threshold settability
# ---------------------------------------------------------------------------

class TestBuildPipelineAuthorityForwarding:

    async def test_build_pipeline_forwards_authority_threshold(self, db) -> None:
        """build_pipeline must accept authority_preference_threshold and
        forward it verbatim into RetrievalPipeline.__init__ (already a
        kwarg there). No such param exists on build_pipeline yet, so this
        call raises TypeError today."""
        pytest.importorskip("onnxruntime")  # build_pipeline needs the embedding model
        pipeline = await build_pipeline(db, authority_preference_threshold=0.05)

        assert pipeline._authority_preference_threshold == 0.05
