"""Tests for the relevance floor (hook-token audit 2026-07-02).

Covers: apply_relevance_floor filtering, disable semantics, config accessor
default and override, and min_relevance_score wiring on RetrievalPipeline.
"""

from __future__ import annotations

import inspect
import tempfile

from writ.config import DEFAULT_MIN_RELEVANCE_SCORE, get_min_relevance_score
from writ.retrieval.pipeline import RetrievalPipeline
from writ.retrieval.ranking import apply_relevance_floor


def _rules(ids_and_scores: list[tuple[str, float]]) -> list[dict]:
    return [{"rule_id": rid, "score": score} for rid, score in ids_and_scores]


class TestApplyRelevanceFloor:
    def test_drops_rules_below_floor(self) -> None:
        rules = _rules([("A", 0.73), ("B", 0.458), ("C", 0.296)])
        result = apply_relevance_floor(rules, 0.30)
        assert [r["rule_id"] for r in result] == ["A", "B"]

    def test_keeps_rule_exactly_at_floor(self) -> None:
        rules = _rules([("A", 0.30)])
        result = apply_relevance_floor(rules, 0.30)
        assert [r["rule_id"] for r in result] == ["A"]

    def test_zero_floor_disables_filtering(self) -> None:
        rules = _rules([("A", 0.05)])
        assert apply_relevance_floor(rules, 0.0) is rules

    def test_negative_floor_disables_filtering(self) -> None:
        rules = _rules([("A", 0.05)])
        assert apply_relevance_floor(rules, -1.0) is rules

    def test_all_below_floor_returns_empty(self) -> None:
        rules = _rules([("A", 0.1), ("B", 0.2)])
        assert apply_relevance_floor(rules, 0.30) == []

    def test_empty_input(self) -> None:
        assert apply_relevance_floor([], 0.30) == []

    def test_missing_score_treated_as_zero(self) -> None:
        rules = [{"rule_id": "A"}]
        assert apply_relevance_floor(rules, 0.30) == []


class TestMinRelevanceScoreConfig:
    def test_default_when_config_missing(self) -> None:
        assert get_min_relevance_score("/nonexistent/writ.toml") == DEFAULT_MIN_RELEVANCE_SCORE

    def test_reads_override_from_toml(self) -> None:
        with tempfile.NamedTemporaryFile(mode="w", suffix=".toml") as f:
            f.write("[ranking]\nmin_relevance_score = 0.42\n")
            f.flush()
            assert get_min_relevance_score(f.name) == 0.42

    def test_default_when_ranking_section_missing(self) -> None:
        with tempfile.NamedTemporaryFile(mode="w", suffix=".toml") as f:
            f.write("[service]\nport = 8765\n")
            f.flush()
            assert get_min_relevance_score(f.name) == DEFAULT_MIN_RELEVANCE_SCORE


class TestPipelineWiring:
    def test_pipeline_accepts_min_relevance_score(self) -> None:
        sig = inspect.signature(RetrievalPipeline.__init__)
        assert "min_relevance_score" in sig.parameters
        assert sig.parameters["min_relevance_score"].default == 0.0
