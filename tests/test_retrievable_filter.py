"""Phase 1 deliverable 7.2: retrievable node-type filter + retrieval_mode tests.

Validates:
- pipeline.query respects node_types whitelist
- retrieval_mode="literal" activates equal-weight BM25/vector
- retrieval_mode="semantic" preserves coding-rule defaults and excludes
  methodology domains from the default candidate pool
- RETRIEVABLE_NODE_TYPES constant matches plan Section 2.3
"""
from __future__ import annotations

import numpy as np

from writ.graph.schema import (
    NodeType,
    RETRIEVABLE_NODE_TYPES,
)
from writ.retrieval.ranking import (
    DEFAULT_W_BM25,
    DEFAULT_W_VECTOR,
    LITERAL_W_BM25,
    LITERAL_W_VECTOR,
    RankingWeights,
)


class TestRetrievableNodeTypes:
    """Plan Section 2.3 retrievable subset."""

    def test_retrievable_set_matches_plan_section_2_3(self) -> None:
        expected = {
            NodeType.RULE, NodeType.ABSTRACTION,
            NodeType.SKILL, NodeType.PLAYBOOK, NodeType.TECHNIQUE,
            NodeType.ANTIPATTERN, NodeType.FORBIDDEN_RESPONSE,
        }
        assert RETRIEVABLE_NODE_TYPES == frozenset(expected)

    def test_non_retrievable_types_excluded(self) -> None:
        non_retrievable = {
            NodeType.PHASE, NodeType.RATIONALIZATION,
            NodeType.PRESSURE_SCENARIO, NodeType.WORKED_EXAMPLE,
            NodeType.SUBAGENT_ROLE,
        }
        assert not (non_retrievable & RETRIEVABLE_NODE_TYPES)


class TestRetrievalModeWeights:
    """retrieval_mode='literal' returns a distinct RankingWeights from default."""

    def test_literal_weights_factory(self) -> None:
        w = RankingWeights.literal()
        assert w.w_bm25 == LITERAL_W_BM25
        assert w.w_vector == LITERAL_W_VECTOR
        # Equal weights between BM25 and vector.
        assert w.w_bm25 == w.w_vector

    def test_default_weights_unchanged(self) -> None:
        """Phase 1 MUST NOT regress coding-rule defaults."""
        w = RankingWeights()
        assert w.w_bm25 == DEFAULT_W_BM25
        assert w.w_vector == DEFAULT_W_VECTOR
        # Coding-rule default is vector-dominant.
        assert w.w_vector > w.w_bm25

    def test_literal_weights_validate(self) -> None:
        RankingWeights.literal().validate()  # sums to 1.0 — no exception

    def test_default_weights_validate(self) -> None:
        RankingWeights().validate()  # sums to 1.0 — no exception


# ---------------------------------------------------------------------------
# Phase 0 T0.4: category route-driven retrieval filter
# ---------------------------------------------------------------------------


def _make_stub_pipeline(node_routes: dict | None = None, metadata: dict | None = None):
    """Build a RetrievalPipeline with minimal synthetic stubs.

    Mirrors the pattern used in other unit-level pipeline tests: construct
    the pipeline with fake keyword/vector/adjacency/encoder dependencies so
    query() can run in-process without Neo4j or ONNX.

    node_routes is the new Phase 0 parameter mapping node_type -> list[str]
    route tags.  Passing it today raises TypeError (no such param yet) --
    that is the intended RED trigger.

    metadata is a dict[rule_id, dict] carrying at minimum 'node_type' and
    'routes' keys that the phase-0 pipeline is expected to consult when
    choosing the candidate pool.
    """
    from unittest.mock import MagicMock

    from writ.retrieval.pipeline import RetrievalPipeline
    from writ.retrieval.traversal import AdjacencyCache

    # Keyword stub: always returns the two synthetic candidates so both
    # BM25 and vector paths are exercised in the filter stage.
    keyword_stub = MagicMock()
    keyword_stub.search.return_value = [
        {"rule_id": "ENF-SEC-001", "score": 0.9},
        {"rule_id": "SKL-PROC-MODE-001", "score": 0.8},
    ]

    # Vector stub: mirrors BM25 results as ScoredResult-like objects.
    from writ.retrieval.embeddings import ScoredResult

    vector_stub = MagicMock()
    vector_stub.search.return_value = [
        ScoredResult(rule_id="ENF-SEC-001", score=0.9),
        ScoredResult(rule_id="SKL-PROC-MODE-001", score=0.8),
    ]

    # Encoder stub: returns a zero vector; shape is irrelevant because
    # vector_stub.search is mocked.
    encoder_stub = MagicMock()
    encoder_stub.encode.return_value = np.zeros(384, dtype=np.float32)

    adjacency = AdjacencyCache()  # empty - no graph traversal needed

    _metadata: dict = metadata or {
        "ENF-SEC-001": {
            "node_type": "Rule",
            "routes": ["semantic"],
            "domain": "security",
            "severity": "high",
            "confidence": "production-validated",
            "statement": "Never expose secrets.",
            "trigger": "secret exposure",
        },
        "SKL-PROC-MODE-001": {
            "node_type": "Skill",
            "routes": ["state"],
            "domain": "process",
            "severity": "medium",
            "confidence": "production-validated",
            "statement": "Set mode before work.",
            "trigger": "mode missing",
        },
    }

    # Phase 0 implementation is expected to accept node_routes as a
    # keyword argument.  Pre-implementation this raises TypeError,
    # which is the RED trigger for TestCategoryRouteFilter.
    if node_routes is not None:
        return RetrievalPipeline(
            keyword_index=keyword_stub,
            vector_store=vector_stub,
            adjacency_cache=adjacency,
            embedding_model=encoder_stub,
            rule_metadata=_metadata,
            node_routes=node_routes,
        )
    else:
        return RetrievalPipeline(
            keyword_index=keyword_stub,
            vector_store=vector_stub,
            adjacency_cache=adjacency,
            embedding_model=encoder_stub,
            rule_metadata=_metadata,
        )


class TestCategoryRouteFilter:
    """Phase 0 T0.4: route-driven candidate filter on RetrievalPipeline.

    Three tests that are RED today for distinct reasons documented inline.
    All three go GREEN when the T0.4 implementation lands.
    """

    def test_semantic_query_includes_only_semantic_routed(self) -> None:
        """A default semantic query returns only nodes whose category routes
        contain 'semantic'; nodes routed exclusively via 'state' are excluded.

        RED reason: RetrievalPipeline.__init__ does not accept node_routes,
        so constructing the pipeline raises TypeError.  Once T0.4 adds
        node_routes to the constructor and wires it into the Stage 1 filter,
        the assertion will also be verified.
        """
        # node_routes maps node_type label to the route tags that govern
        # whether that type enters the default semantic candidate pool.
        node_routes = {
            "Rule": ["semantic"],
            "Skill": ["state"],
        }
        # This line raises TypeError today (no node_routes param).
        pipeline = _make_stub_pipeline(node_routes=node_routes)

        result = pipeline.query("never expose secrets")
        returned_ids = [r["rule_id"] for r in result["rules"]]

        # ENF-SEC-001 has routes=['semantic'] -> must appear.
        assert "ENF-SEC-001" in returned_ids, (
            "Rule with 'semantic' route must be included in default semantic query"
        )
        # SKL-PROC-MODE-001 has routes=['state'] -> must be excluded.
        assert "SKL-PROC-MODE-001" not in returned_ids, (
            "Skill with only 'state' route must be excluded from default semantic query"
        )

    def test_legacy_fallback_when_node_routes_none(self) -> None:
        """When node_routes=None (pre-migration graph, no route metadata),
        the pipeline falls back to the pre-Phase-0 behavior: no TypeError,
        and process-domain methodology nodes remain excluded from the default
        semantic query (the existing methodology_domain_exclude path).

        RED reason: RetrievalPipeline.__init__ does not accept node_routes
        today, so even node_routes=None raises TypeError.  Once T0.4 adds
        the parameter with a default of None, this test goes GREEN and acts
        as a guard that the legacy fallback is not broken.
        """
        # node_routes=None triggers the legacy fallback path.
        pipeline = _make_stub_pipeline(node_routes=None)

        # Must not raise - legacy graph has no route metadata.
        result = pipeline.query("never expose secrets")

        # Legacy fallback: process-domain methodology node still excluded.
        returned_ids = [r["rule_id"] for r in result["rules"]]
        assert "SKL-PROC-MODE-001" not in returned_ids, (
            "process-domain Skill must remain excluded via legacy "
            "methodology_domain_exclude fallback when node_routes=None"
        )

    def test_explicit_node_types_overrides_route_filter(self) -> None:
        """Passing node_types=['Skill'] to query() includes Skill regardless
        of its route tag.  Explicit node_types wins over the route-based filter.

        RED reason: RetrievalPipeline.__init__ does not accept node_routes,
        so constructing the pipeline raises TypeError.  Once T0.4 lands, the
        assertion verifies that explicit node_types overrides route filtering
        (plan Section 4, bullet 3: 'node_types passed to query() wins').
        """
        node_routes = {
            "Rule": ["semantic"],
            "Skill": ["state"],
        }
        pipeline = _make_stub_pipeline(node_routes=node_routes)

        # Explicitly requesting 'Skill' must bypass the route filter and
        # include SKL-PROC-MODE-001 in the results.
        result = pipeline.query(
            "set mode before work",
            node_types=["Skill"],
        )
        returned_ids = [r["rule_id"] for r in result["rules"]]

        assert "SKL-PROC-MODE-001" in returned_ids, (
            "Skill must appear when node_types=['Skill'] overrides route filter"
        )
