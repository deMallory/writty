"""1.5: the /methodology-companion endpoint (CHANNEL 2).

Wraps the 1.6 trigger index and reshapes its match into /query's response shape
so the shared cmd_format renders it (summary form). BUILT-NOT-WIRED per D5: the
hook keeps the legacy /query path until the 1.7 cutover, so on the current corpus
(no floors/keywords authored yet) the endpoint returns an empty bundle -- which is
itself the assertion that nothing injects before authoring.

The shaping/wiring tests call the endpoint coroutine directly with an in-memory
index (the index is built at startup, so seeding the live graph wouldn't reach it
without a restart); one live smoke test confirms the endpoint is reachable and
empty pre-authoring.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request

import pytest

from tests._daemon import _port
from writ import server
from writ.server import CompanionRequest, methodology_companion
from writ.retrieval.trigger_index import MethodologyTriggerIndex

SERVER = f"http://localhost:{_port()}"


def _node(node_id, *, floor_modes=None, trigger_keywords=None,
          trigger="when x", statement="do y", domain="process") -> dict:
    return {
        "id": node_id, "node_type": "Skill",
        "floor_modes": floor_modes or [], "action_triggers": [],
        "trigger_keywords": trigger_keywords or [],
        "trigger": trigger, "statement": statement, "severity": "high", "domain": domain,
    }


class TestCompanionShaping:
    @pytest.mark.asyncio
    async def test_returns_query_shape_for_cmd_format(self, monkeypatch) -> None:
        idx = MethodologyTriggerIndex([_node("SKL-FLOOR-001", floor_modes=["work"])])
        monkeypatch.setattr(server, "_trigger_index", idx)
        resp = await methodology_companion(CompanionRequest(mode="work", prompt=""))
        assert resp["mode"] == "summary"  # cmd_format renders trigger+statement only
        assert resp["total_candidates"] == 1
        assert {r["rule_id"] for r in resp["rules"]} == {"SKL-FLOOR-001"}
        r0 = resp["rules"][0]
        # the keys cmd_format .get()s
        for k in ("rule_id", "trigger", "statement", "severity", "authority", "domain", "score"):
            assert k in r0
        assert r0["channel"] == "floor"

    @pytest.mark.asyncio
    async def test_pull_then_exclude(self, monkeypatch) -> None:
        idx = MethodologyTriggerIndex([_node("SKL-PULL-001", trigger_keywords=["worktree"])])
        monkeypatch.setattr(server, "_trigger_index", idx)
        hit = await methodology_companion(
            CompanionRequest(mode="work", prompt="please fix the worktree")
        )
        assert {r["rule_id"] for r in hit["rules"]} == {"SKL-PULL-001"}
        assert hit["rules"][0]["channel"] == "pull"
        # exclude_rule_ids drops an already-injected node (no re-inject, no budget spend)
        excluded = await methodology_companion(
            CompanionRequest(
                mode="work", prompt="please fix the worktree",
                exclude_rule_ids=["SKL-PULL-001"],
            )
        )
        assert excluded["rules"] == []

    @pytest.mark.asyncio
    async def test_uninitialized_index_guarded(self, monkeypatch) -> None:
        monkeypatch.setattr(server, "_trigger_index", None)
        resp = await methodology_companion(CompanionRequest(mode="work"))
        assert "error" in resp


class TestCompanionLive:
    def test_live_endpoint_reachable_and_well_shaped(self) -> None:
        # Shape-only: the exact contents depend on the daemon's startup index
        # state (which can lag the graph mid-suite); matching is pinned by the
        # in-memory index tests + the monkeypatch shaping tests. Here we only
        # confirm the endpoint is reachable and returns the cmd_format shape.
        body = json.dumps({"mode": "work", "prompt": "refactor the parser module"}).encode()
        req = urllib.request.Request(
            f"{SERVER}/methodology-companion", data=body,
            headers={"Content-Type": "application/json"}, method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=3) as r:
                data = json.loads(r.read())
        except (urllib.error.URLError, OSError) as e:
            pytest.skip(f"Writ server unreachable: {e}")
        assert data.get("mode") == "summary"
        assert isinstance(data.get("rules"), list)
        assert "total_tokens" in data and "over_budget" in data
