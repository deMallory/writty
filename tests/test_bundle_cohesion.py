"""Phase 1 deliverable 7.3: bundle-cohesion ranking-weight tests.

(The get_bundle depth-N BFS tests were removed in 1.6b -- get_bundle was dead in
production; AdjacencyCache exposes get_neighbors / get_enrichment as the live
traversal surface. These tests cover the w_bundle_cohesion ranking weight, which
is independent of how a bundle_cohesion value is sourced.)
"""
from __future__ import annotations

import pytest

from writ.retrieval.ranking import RankingWeights, compute_score


class TestBundleCohesionScoring:
    """compute_score accepts bundle_cohesion and applies w_bundle_cohesion."""

    def test_default_bundle_cohesion_zero(self) -> None:
        s = compute_score(
            bm25_norm=1.0, vector_norm=1.0, severity="high",
            confidence="production-validated", bundle_cohesion=0.0,
        )
        assert s > 0

    def test_bundle_cohesion_contributes_when_weight_set(self) -> None:
        weights_no_cohesion = RankingWeights(
            w_bm25=0.198, w_vector=0.594, w_severity=0.099, w_confidence=0.099,
            w_graph=0.01, w_bundle_cohesion=0.0,
        )
        weights_with_cohesion = RankingWeights(
            w_bm25=0.178, w_vector=0.574, w_severity=0.099, w_confidence=0.099,
            w_graph=0.01, w_bundle_cohesion=0.04,
        )
        base_args = dict(
            bm25_norm=0.5, vector_norm=0.5, severity="high",
            confidence="production-validated", bundle_cohesion=1.0,
        )
        s_no = compute_score(**base_args, weights=weights_no_cohesion)
        s_with = compute_score(**base_args, weights=weights_with_cohesion)
        # With cohesion weight active and bundle_cohesion=1.0, score is higher.
        assert s_with > s_no

    def test_weights_validate_with_bundle_cohesion(self) -> None:
        w = RankingWeights(
            w_bm25=0.178, w_vector=0.574, w_severity=0.099, w_confidence=0.099,
            w_graph=0.01, w_bundle_cohesion=0.04,
        )
        w.validate()  # sums to 1.0 — no exception

    def test_weights_reject_non_unit_sum(self) -> None:
        w = RankingWeights(
            w_bm25=0.198, w_vector=0.594, w_severity=0.099, w_confidence=0.099,
            w_graph=0.01, w_bundle_cohesion=0.5,
        )
        with pytest.raises(ValueError):
            w.validate()
