"""T0.5 server: retrieval_mode field on QueryRequest, endpoint plumbing, /health counts.

RED gate for:
- QueryRequest.retrieval_mode field (defaults to 'semantic', accepts 'literal')
- POST /query passes retrieval_mode through to pipeline.query
- GET /health returns category_count and route_distribution
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio

try:
    from httpx import AsyncClient, ASGITransport
except ImportError:
    pytestmark = pytest.mark.skip(reason="httpx not installed")

from writ.server import app, QueryRequest  # type: ignore[import]


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture()
def mock_pipeline():
    """Minimal pipeline mock that records query() call args."""
    mock = MagicMock()
    mock.query.return_value = {
        "rules": [],
        "mode": "full",
        "total_candidates": 0,
        "latency_ms": 1.0,
    }
    return mock


@pytest.fixture()
def mock_db():
    mock = MagicMock()
    mock.count_rules = AsyncMock(return_value=0)
    mock.close = AsyncMock()
    # category_count query support -- will be used by health endpoint after T0.5
    mock._driver = MagicMock()
    session_cm = AsyncMock()
    session_cm.__aenter__ = AsyncMock(return_value=session_cm)
    session_cm.__aexit__ = AsyncMock(return_value=None)
    run_result = AsyncMock()
    run_result.single = AsyncMock(
        return_value={"count": 0, "category_count": 3}
    )
    session_cm.run = AsyncMock(return_value=run_result)
    mock._driver.session.return_value = session_cm
    mock._database = "neo4j"
    return mock


@pytest_asyncio.fixture()
async def client(mock_pipeline, mock_db):
    """Test client with mocked pipeline and db injected into server module state."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        with (
            patch("writ.server._pipeline", mock_pipeline),
            patch("writ.server._db", mock_db),
        ):
            yield ac, mock_pipeline, mock_db


# ---------------------------------------------------------------------------
# TestQueryRequestRetrievalMode
# ---------------------------------------------------------------------------


class TestQueryRequestRetrievalMode:
    """QueryRequest Pydantic model exposes retrieval_mode with a 'semantic' default."""

    def test_defaults_to_semantic(self) -> None:
        """QueryRequest(query='x').retrieval_mode == 'semantic' when field is omitted."""
        req = QueryRequest(query="x")
        assert req.retrieval_mode == "semantic", (
            f"retrieval_mode must default to 'semantic'; got {req.retrieval_mode!r}"
        )

    def test_accepts_literal(self) -> None:
        """QueryRequest accepts retrieval_mode='literal' without raising."""
        req = QueryRequest(query="x", retrieval_mode="literal")
        assert req.retrieval_mode == "literal"

    def test_model_dump_includes_retrieval_mode(self) -> None:
        """model_dump() serialises retrieval_mode so it round-trips over HTTP."""
        req = QueryRequest(query="x", retrieval_mode="literal")
        dumped = req.model_dump()
        assert "retrieval_mode" in dumped, (
            f"model_dump() must include 'retrieval_mode'; keys={list(dumped.keys())}"
        )
        assert dumped["retrieval_mode"] == "literal"


# ---------------------------------------------------------------------------
# TestQueryEndpointPlumbing
# ---------------------------------------------------------------------------


class TestQueryEndpointPlumbing:
    """POST /query threads retrieval_mode through to pipeline.query()."""

    @pytest.mark.asyncio
    async def test_passes_literal_to_pipeline(self, client) -> None:
        """POST /query with retrieval_mode='literal' calls pipeline.query(retrieval_mode='literal')."""
        ac, mock_pipeline, _ = client
        response = await ac.post("/query", json={"query": "sql injection", "retrieval_mode": "literal"})
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        mock_pipeline.query.assert_called_once()
        call_kwargs = mock_pipeline.query.call_args.kwargs
        assert call_kwargs.get("retrieval_mode") == "literal", (
            f"pipeline.query must receive retrieval_mode='literal'; "
            f"got call_kwargs={call_kwargs!r}"
        )

    @pytest.mark.asyncio
    async def test_default_is_semantic(self, client) -> None:
        """POST /query with retrieval_mode omitted calls pipeline.query(retrieval_mode='semantic')."""
        ac, mock_pipeline, _ = client
        response = await ac.post("/query", json={"query": "sql injection"})
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        mock_pipeline.query.assert_called_once()
        call_kwargs = mock_pipeline.query.call_args.kwargs
        assert call_kwargs.get("retrieval_mode") == "semantic", (
            f"pipeline.query must receive retrieval_mode='semantic' by default; "
            f"got call_kwargs={call_kwargs!r}"
        )


# ---------------------------------------------------------------------------
# TestHealthCategoryRouteCounts
# ---------------------------------------------------------------------------


class TestHealthCategoryRouteCounts:
    """GET /health returns category_count and route_distribution after T0.5."""

    @pytest.mark.asyncio
    async def test_health_returns_category_count_and_route_distribution(self, client) -> None:
        """GET /health JSON has 'category_count':int and 'route_distribution':dict."""
        ac, _, _ = client
        response = await ac.get("/health")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        body: dict[str, Any] = response.json()
        assert "category_count" in body, (
            f"/health response must include 'category_count'; keys={list(body.keys())}"
        )
        assert isinstance(body["category_count"], int), (
            f"'category_count' must be int; got {type(body['category_count'])!r}"
        )
        assert "route_distribution" in body, (
            f"/health response must include 'route_distribution'; keys={list(body.keys())}"
        )
        assert isinstance(body["route_distribution"], dict), (
            f"'route_distribution' must be dict; got {type(body['route_distribution'])!r}"
        )
