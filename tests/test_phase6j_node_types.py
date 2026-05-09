"""Phase 6j -- node_types opt-in on QueryRequest.

Pins the contract that lets methodology queries (Skill, Playbook, etc.)
flow through the same /query endpoint that defaults to Rule-only. Without
this opt-in, --skill-usage stays empty because no production code path
emits rag_query events containing SKL- IDs.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from writ.server import QueryRequest, app


class TestQueryRequestNodeTypes:
    """The Pydantic model accepts the new field and round-trips it."""

    def test_query_request_accepts_node_types(self) -> None:
        req = QueryRequest(query="x", node_types=["Skill"])
        assert req.node_types == ["Skill"]
        dumped = req.model_dump()
        assert dumped["node_types"] == ["Skill"]

    def test_query_request_node_types_defaults_to_none(self) -> None:
        req = QueryRequest(query="x")
        assert req.node_types is None

    def test_query_request_accepts_multiple_node_types(self) -> None:
        req = QueryRequest(query="x", node_types=["Skill", "Playbook"])
        assert req.node_types == ["Skill", "Playbook"]


class TestQueryEndpointPlumbing:
    """The /query endpoint forwards node_types to the pipeline."""

    def test_query_endpoint_passes_node_types_to_pipeline(self) -> None:
        fake = MagicMock()
        fake.query.return_value = {"rules": [], "mode": "semantic", "total_candidates": 0}
        with patch("writ.server._pipeline", fake):
            client = TestClient(app)
            r = client.post(
                "/query",
                json={"query": "plan first then code", "node_types": ["Skill", "Playbook"]},
            )
        assert r.status_code == 200
        fake.query.assert_called_once()
        kwargs = fake.query.call_args.kwargs
        assert kwargs.get("node_types") == ["Skill", "Playbook"]

    def test_query_endpoint_default_node_types_is_none(self) -> None:
        fake = MagicMock()
        fake.query.return_value = {"rules": [], "mode": "semantic", "total_candidates": 0}
        with patch("writ.server._pipeline", fake):
            client = TestClient(app)
            r = client.post("/query", json={"query": "any prompt"})
        assert r.status_code == 200
        fake.query.assert_called_once()
        assert fake.query.call_args.kwargs.get("node_types") is None
