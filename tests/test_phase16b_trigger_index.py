"""1.6b: the methodology-trigger index matching model.

Deterministic floor u push u pull, deduped (flat index = add-on #3 path-redundancy
prune for free), floor-first, budget-capped (floor+push never dropped; pull is the
flexible tail). Pure in-memory tests pin the matching logic with no DB.
"""

from __future__ import annotations

from writ.retrieval.trigger_index import MethodologyTriggerIndex


def _node(node_id, *, floor_modes=None, action_triggers=None, trigger_keywords=None,
          trigger="", statement="x" * 40) -> dict:
    # default statement len 40, trigger "" -> est_tokens = 40 // 4 = 10
    return {
        "id": node_id, "node_type": "Skill",
        "floor_modes": floor_modes or [],
        "action_triggers": action_triggers or [],
        "trigger_keywords": trigger_keywords or [],
        "trigger": trigger, "statement": statement, "severity": "high",
    }


def _ids(result):
    return [n["id"] for n in result["nodes"]]


class TestFloorPushPull:
    def test_floor_matches_only_its_modes(self) -> None:
        idx = MethodologyTriggerIndex([_node("A", floor_modes=["work"])])
        assert _ids(idx.match("work", "")) == ["A"]
        assert _ids(idx.match("debug", "")) == []

    def test_push_matches_action(self) -> None:
        idx = MethodologyTriggerIndex([_node("A", action_triggers=["plan"])])
        assert _ids(idx.match("work", "", action="plan")) == ["A"]
        assert _ids(idx.match("work", "", action="gate-denial")) == []

    def test_pull_matches_keyword_whole_word(self) -> None:
        idx = MethodologyTriggerIndex([_node("A", trigger_keywords=["worktree"])])
        assert _ids(idx.match("work", "please fix the worktree now")) == ["A"]
        # whole-word: a superstring token does NOT match
        assert _ids(idx.match("work", "worktreezilla")) == []
        assert _ids(idx.match("work", "nothing relevant")) == []

    def test_pull_ordered_by_match_count(self) -> None:
        idx = MethodologyTriggerIndex([
            _node("ONE", trigger_keywords=["alpha"]),
            _node("TWO", trigger_keywords=["alpha", "beta"]),
        ])
        # prompt hits both keywords of TWO, one of ONE -> TWO first
        assert _ids(idx.match("work", "alpha and beta")) == ["TWO", "ONE"]


class TestDedupeAndOrder:
    def test_node_in_two_channels_appears_once_floor_first(self) -> None:
        idx = MethodologyTriggerIndex([
            _node("D", floor_modes=["work"], trigger_keywords=["gamma"]),
        ])
        res = idx.match("work", "gamma here")
        assert _ids(res) == ["D"]
        assert res["nodes"][0]["channel"] == "floor"  # floor wins over pull

    def test_floor_before_pull(self) -> None:
        idx = MethodologyTriggerIndex([
            _node("P", trigger_keywords=["delta"]),
            _node("F", floor_modes=["work"]),
        ])
        res = idx.match("work", "delta")
        assert _ids(res) == ["F", "P"]
        assert res["nodes"][0]["channel"] == "floor"
        assert res["nodes"][1]["channel"] == "pull"


class TestBudget:
    def test_floor_never_dropped_flags_over_budget(self) -> None:
        # one floor node costs 10 tokens; budget 5 -> kept, over_budget True
        idx = MethodologyTriggerIndex([_node("F", floor_modes=["work"])])
        res = idx.match("work", "", budget_tokens=5)
        assert _ids(res) == ["F"]
        assert res["over_budget"] is True

    def test_pull_truncated_to_budget_lowest_count_first(self) -> None:
        # two pull nodes, 10 tokens each; budget 15 -> only the 2-match one fits
        idx = MethodologyTriggerIndex([
            _node("LOW", trigger_keywords=["alpha"]),
            _node("HIGH", trigger_keywords=["alpha", "beta"]),
        ])
        res = idx.match("work", "alpha beta", budget_tokens=15)
        assert _ids(res) == ["HIGH"]
        assert res["over_budget"] is False

    def test_empty_when_nothing_matches(self) -> None:
        idx = MethodologyTriggerIndex([_node("A", floor_modes=["debug"])])
        res = idx.match("work", "irrelevant prompt")
        assert res["nodes"] == []
        assert res["total_tokens"] == 0
