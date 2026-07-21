"""KG S4: CRAG-style abstention gate tests.

RED skeleton (plan.md, "Plan: KG S4 -- CRAG-style abstention gate"). These
assertions describe the gate `writ/retrieval/pipeline.py` does not implement
yet:

- `RetrievalPipeline.__init__` gains `abstention_threshold: float = 0.0`,
  stored as `self._abstention_threshold`.
- `query()` computes `top_raw_cosine` (the raw top-1 vector cosine) and, when
  `abstention_threshold > 0.0` and `top_raw_cosine` is below it, returns early
  with `{"rules": [], "mode": "abstained", "total_candidates": 0,
  "latency_ms": ..., "abstain_signal": ...}`.
- The normal (non-abstained) return also gains an `"abstain_signal"` float key.
- `build_pipeline` ships `abstention_threshold=0.30` by default, making the
  gate live on the fixture (`live_pipeline`) pipeline.

Until that lands, every test in `TestAbstentionGateToggle` below is expected
to ERROR (no `_abstention_threshold` attribute exists to set) and
`test_false_injection_cut_on_negatives` is expected to FAIL (the ungated
pipeline injects on ~100% of negatives, well over the 0.40 ceiling). The two
gold-floor tests may already pass -- they exercise pre-existing behavior the
gate must not regress.

Requires Neo4j running + onnxruntime; uses the shared session-scoped
`live_pipeline` fixture from `tests/conftest.py`.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

pytest.importorskip("onnxruntime")

from tests.fixtures.regression_floors import HIT_RATE_FLOOR, MRR5_FLOOR
from tests.fixtures.retrieval_scoring import hit_rate_at_5, mrr_at_5
from writ.retrieval.pipeline import RULE_INJECTION_ABSTENTION_THRESHOLD

_FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"

GOLD_QUERIES = json.loads(
    (_FIXTURES_DIR / "ground_truth_queries.json").read_text()
)["queries"]
NEGATIVES = json.loads(
    (_FIXTURES_DIR / "ground_truth_negatives.json").read_text()
)["negatives"]

# A clearly off-domain negative (flavor A, high-confidence "no rule applies").
OFFDOMAIN_QUERY = NEGATIVES[0]["query"]

# A strong on-domain gold query: the first "keyword"-set query reliably scores
# a high raw top-1 cosine (keyword queries closely echo a rule's trigger text).
STRONG_GOLD_QUERY = next(q["query"] for q in GOLD_QUERIES if q["set"] == "keyword")


@pytest.fixture()
def gated_pipeline(live_pipeline):
    """`live_pipeline` with its `_abstention_threshold` captured and restored.

    `live_pipeline` is session-scoped and shared across the whole file
    (TEST-ISOLATE-001); any test that flips the gate threshold on it must not
    leak that mutation into other tests, so this fixture snapshots the
    original value and restores it in a finally block regardless of what the
    test sets it to.
    """
    original = live_pipeline._abstention_threshold
    try:
        yield live_pipeline
    finally:
        live_pipeline._abstention_threshold = original


class TestAbstentionGateToggle:
    """Direct on/off behavior of the gate via `_abstention_threshold`."""

    def test_gate_off_returns_rules_for_offdomain(self, gated_pipeline) -> None:
        """Gate OFF (threshold=0.0) must never abstain, even on a clearly
        off-domain query."""
        gated_pipeline._abstention_threshold = 0.0
        result = gated_pipeline.query(OFFDOMAIN_QUERY)
        assert result["rules"], (
            "gate OFF (abstention_threshold=0.0) must still inject rules; "
            "abstention is opt-in via a positive threshold"
        )

    def test_gate_on_abstains_on_offdomain(self, gated_pipeline) -> None:
        """Gate ON at the shipped threshold (0.30) abstains on an off-domain
        negative: empty rules, mode == 'abstained', zero candidates."""
        gated_pipeline._abstention_threshold = RULE_INJECTION_ABSTENTION_THRESHOLD
        result = gated_pipeline.query(OFFDOMAIN_QUERY)
        assert result["rules"] == []
        assert result["mode"] == "abstained"
        assert result["total_candidates"] == 0

    def test_gate_on_keeps_strong_ondomain_query(self, gated_pipeline) -> None:
        """Gate ON at 0.30 must not starve a strong on-domain keyword query:
        it still returns rules and is not marked abstained."""
        gated_pipeline._abstention_threshold = RULE_INJECTION_ABSTENTION_THRESHOLD
        result = gated_pipeline.query(STRONG_GOLD_QUERY)
        assert result["rules"], "a strong on-domain query must clear the gate"
        assert result["mode"] != "abstained"

    def test_normal_result_has_abstain_signal(self, gated_pipeline) -> None:
        """A non-abstained result carries an 'abstain_signal' float that
        cleared the 0.30 gate (i.e. is >= the threshold)."""
        gated_pipeline._abstention_threshold = RULE_INJECTION_ABSTENTION_THRESHOLD
        result = gated_pipeline.query(STRONG_GOLD_QUERY)
        assert "abstain_signal" in result
        assert isinstance(result["abstain_signal"], float)
        assert result["abstain_signal"] >= RULE_INJECTION_ABSTENTION_THRESHOLD

    def test_abstained_result_shape(self, gated_pipeline) -> None:
        """The abstained result's full shape: signal below threshold, empty
        rules, 'abstained' mode, zero candidates."""
        gated_pipeline._abstention_threshold = RULE_INJECTION_ABSTENTION_THRESHOLD
        result = gated_pipeline.query(OFFDOMAIN_QUERY)
        assert "abstain_signal" in result
        assert isinstance(result["abstain_signal"], float)
        assert result["abstain_signal"] < RULE_INJECTION_ABSTENTION_THRESHOLD
        assert result["rules"] == []
        assert result["mode"] == "abstained"
        assert result["total_candidates"] == 0

    def test_gate_boundary_around_signal_is_two_sided(self, gated_pipeline) -> None:
        """The gate is a strict `<`: a threshold just ABOVE a query's own raw
        cosine abstains, one just BELOW retains (ENF-POST-005 boundary
        coverage). Derived from the query's measured abstain_signal so it is
        deterministic regardless of the absolute cosine value."""
        gated_pipeline._abstention_threshold = 0.0
        sig = gated_pipeline.query(OFFDOMAIN_QUERY)["abstain_signal"]

        gated_pipeline._abstention_threshold = sig + 1e-3
        above = gated_pipeline.query(OFFDOMAIN_QUERY)
        assert above["rules"] == []
        assert above["mode"] == "abstained"

        gated_pipeline._abstention_threshold = sig - 1e-3
        below = gated_pipeline.query(OFFDOMAIN_QUERY)
        assert below["mode"] != "abstained"


class TestFalseInjectionAndGoldFloors:
    """Regression coverage at the rule-injection operating point.

    The shared factory (`build_pipeline`) is now gate-OFF by default, so each
    test sets the injection threshold explicitly to mirror what the daemon and
    `writ query` configure (RULE_INJECTION_ABSTENTION_THRESHOLD)."""

    def test_false_injection_cut_on_negatives(self, gated_pipeline) -> None:
        """Over the 20 off-domain/uncovered negatives, the fraction that still
        get a rule injected is well below the ungated 100% baseline (measured
        0.30 at the injection threshold; allow up to 0.40 for variance)."""
        gated_pipeline._abstention_threshold = RULE_INJECTION_ABSTENTION_THRESHOLD
        injected = sum(
            1 for n in NEGATIVES if gated_pipeline.query(n["query"])["rules"]
        )
        rate = injected / len(NEGATIVES)
        print(
            f"\nfalse-injection rate on {len(NEGATIVES)} negatives "
            f"(injection threshold): {rate:.2%}"
        )
        assert rate <= 0.40

    def test_gold_hit_rate_floor_holds_with_gate_live(self, gated_pipeline) -> None:
        """hit@5 over all 193 gold queries stays >= HIT_RATE_FLOOR at the
        rule-injection threshold."""
        gated_pipeline._abstention_threshold = RULE_INJECTION_ABSTENTION_THRESHOLD
        hit, _ = hit_rate_at_5(gated_pipeline, GOLD_QUERIES)
        print(
            f"\nhit-rate@5 (all {len(GOLD_QUERIES)}, injection threshold): "
            f"{hit:.4f} (floor {HIT_RATE_FLOOR})"
        )
        assert hit >= HIT_RATE_FLOOR

    def test_gold_ambiguous_mrr_floor_holds_with_gate_live(self, gated_pipeline) -> None:
        """MRR@5 over the ambiguous gold subset stays >= MRR5_FLOOR at the
        rule-injection threshold."""
        gated_pipeline._abstention_threshold = RULE_INJECTION_ABSTENTION_THRESHOLD
        ambiguous = [q for q in GOLD_QUERIES if q["set"] == "ambiguous"]
        mrr, _ = mrr_at_5(gated_pipeline, ambiguous)
        print(
            f"\nMRR@5 (ambiguous {len(ambiguous)}, injection threshold): "
            f"{mrr:.4f} (floor {MRR5_FLOOR})"
        )
        assert mrr >= MRR5_FLOOR


class TestFactoryDefaultAndScope:
    """The gate is opt-in: the shared factory and the bare constructor default
    OFF, so only rule-injection callers that pass the threshold are gated."""

    def test_build_pipeline_factory_defaults_gate_off(self, live_pipeline) -> None:
        """`build_pipeline` (the shared factory used by authoring + diagnostics)
        leaves the gate off, so those callers are never silently gated by a
        threshold measured only for rule injection."""
        assert live_pipeline._abstention_threshold == 0.0

    def test_injection_threshold_constant_matches_measured_point(self) -> None:
        """Pin the shipped rule-injection operating point (measured do-no-harm
        value) so a drift is caught."""
        assert RULE_INJECTION_ABSTENTION_THRESHOLD == 0.30

    def test_init_default_abstention_threshold_is_off(self) -> None:
        """RetrievalPipeline.__init__ defaults the gate OFF (0.0) so direct
        constructions (offline sweeps, stub tests) are ungated by construction.
        Pure constructor-default check -- no Neo4j / embeddings needed."""
        from unittest.mock import MagicMock

        from writ.retrieval.pipeline import RetrievalPipeline

        pipe = RetrievalPipeline(
            keyword_index=MagicMock(),
            vector_store=MagicMock(),
            adjacency_cache=MagicMock(),
            embedding_model=MagicMock(),
            rule_metadata={},
        )
        assert pipe._abstention_threshold == 0.0
