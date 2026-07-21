"""1.8b: push re-surfaces through exclude_ids (D-A).

The action push exists to deliver methodology AT the action moment -- even if the
node was already injected at turn-start (so it sits in the turn's exclude_ids).
Floor and pull still honor exclude_ids (no re-dump); only PUSH bypasses it, because
timing IS the value of push-by-action. Making this a property of the index (push
computed from the unfiltered node set) means a hook gets re-surface for free,
regardless of what exclude_ids it passes.
"""

from __future__ import annotations

from writ.retrieval.trigger_index import MethodologyTriggerIndex


def _node(node_id, *, floor_modes=None, action_triggers=None, trigger_keywords=None,
          trigger="", statement="x" * 40) -> dict:
    return {
        "id": node_id, "node_type": "Skill",
        "floor_modes": floor_modes or [],
        "action_triggers": action_triggers or [],
        "trigger_keywords": trigger_keywords or [],
        "trigger": trigger, "statement": statement, "severity": "high",
    }


def _ids(result):
    return [n["id"] for n in result["nodes"]]


class TestPushResurfacesThroughExclude:
    def test_push_resurfaces_when_excluded(self) -> None:
        # The node is in exclude_ids (already injected this turn) yet the action
        # push re-surfaces it -- timing is the value (D-A).
        idx = MethodologyTriggerIndex([_node("A", action_triggers=["worktree"])])
        r = idx.match(None, "", action="worktree", exclude_ids={"A"})
        assert _ids(r) == ["A"]
        assert r["nodes"][0]["channel"] == "push"

    def test_floor_still_honors_exclude(self) -> None:
        # Only push bypasses exclude; an already-injected floor node is NOT re-dumped.
        idx = MethodologyTriggerIndex([_node("A", floor_modes=["work"])])
        assert _ids(idx.match("work", "", exclude_ids={"A"})) == []

    def test_pull_still_honors_exclude(self) -> None:
        # Pull also honors exclude -- no re-dump of already-injected keyword hits.
        idx = MethodologyTriggerIndex([_node("A", trigger_keywords=["worktree"])])
        assert _ids(idx.match("work", "fix the worktree", exclude_ids={"A"})) == []

    def test_push_floor_overlap_excluded_resurfaces_as_push(self) -> None:
        # A node that is BOTH floored and pushed, and is excluded: floor (filtered)
        # drops it, push (unfiltered) re-surfaces it -> appears once, channel=push.
        idx = MethodologyTriggerIndex([
            _node("A", floor_modes=["work"], action_triggers=["worktree"]),
        ])
        r = idx.match("work", "", action="worktree", exclude_ids={"A"})
        assert _ids(r) == ["A"]
        assert r["nodes"][0]["channel"] == "push"

    def test_push_floor_overlap_not_excluded_is_floor(self) -> None:
        # Same node, NOT excluded: floor-first wins, appears once as floor.
        idx = MethodologyTriggerIndex([
            _node("A", floor_modes=["work"], action_triggers=["worktree"]),
        ])
        r = idx.match("work", "", action="worktree")
        assert _ids(r) == ["A"]
        assert r["nodes"][0]["channel"] == "floor"
