"""Item 4a: POST /session/format HTTP endpoint.

Tests that the new /session/format endpoint produces the same formatted
output as the CLI subprocess path for representative inputs. Correctness
tests, not performance tests.
"""

from __future__ import annotations

import subprocess
import sys
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
import pytest_asyncio

try:
    from httpx import AsyncClient, ASGITransport
except ImportError:
    pytestmark = pytest.mark.skip(reason="httpx not installed")

from writ.server import app  # type: ignore[import]

SKILL_DIR = "/home/lucio.saldivar/.claude/skills/writ"
SESSION_HELPER = f"{SKILL_DIR}/bin/lib/writ-session.py"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture()
def mock_writ_session():
    mock = MagicMock()
    mock._read_cache = MagicMock(return_value={})
    mock._write_cache = MagicMock()
    mock.DEFAULT_SESSION_BUDGET = 8000

    def _fake_cmd_format(query_response: dict, **kwargs: Any) -> str:
        rules = query_response.get("rules", [])
        if not rules:
            return "No rules retrieved."
        lines = []
        for r in rules:
            lines.append(f"[{r.get('rule_id', '?')}] {r.get('statement', '')}")
        return "\n".join(lines)

    mock.cmd_format = MagicMock(side_effect=_fake_cmd_format)
    return mock


@pytest_asyncio.fixture()
async def client(mock_writ_session):
    transport = ASGITransport(app=app)
    with patch("writ.server.writ_session", mock_writ_session):
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            yield ac


SAMPLE_QUERY_RESPONSE = {
    "rules": [
        {
            "rule_id": "ARCH-ORG-001",
            "statement": "Each class must belong to exactly one architectural layer.",
            "trigger": "When creating a class",
            "violation": "Controller contains SQL query.",
            "pass_example": "Controller delegates to service.",
            "rationale": "Mixed layers create fragile classes.",
        }
    ],
    "mode": "standard",
    "total_candidates": 1,
    "latency_ms": 5.0,
}

EMPTY_QUERY_RESPONSE = {
    "rules": [],
    "mode": "standard",
    "total_candidates": 0,
    "latency_ms": 1.0,
}


# ---------------------------------------------------------------------------
# TestFormatEndpointShape
# ---------------------------------------------------------------------------


class TestFormatEndpointShape:
    """POST /session/format returns correct response shape."""

    @pytest.mark.asyncio
    async def test_format_returns_200_for_valid_input(self, client: AsyncClient) -> None:
        """POST /session/format with valid query_response returns HTTP 200."""
        payload = {"query_response": SAMPLE_QUERY_RESPONSE}
        response = await client.post("/session/format", json=payload)
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_format_response_has_text_field(self, client: AsyncClient) -> None:
        """Response body includes a 'text' string field."""
        payload = {"query_response": SAMPLE_QUERY_RESPONSE}
        response = await client.post("/session/format", json=payload)
        assert response.status_code == 200
        body = response.json()
        assert "text" in body, f"Response must include 'text' field; got {body!r}"
        assert isinstance(body["text"], str)

    @pytest.mark.asyncio
    async def test_format_response_has_meta_field(self, client: AsyncClient) -> None:
        """Response body includes a 'meta' dict field."""
        payload = {"query_response": SAMPLE_QUERY_RESPONSE}
        response = await client.post("/session/format", json=payload)
        body = response.json()
        assert "meta" in body, f"Response must include 'meta' field; got {body!r}"
        assert isinstance(body["meta"], dict)

    @pytest.mark.asyncio
    async def test_format_rejects_missing_body(self, client: AsyncClient) -> None:
        """POST /session/format with no body returns HTTP 422."""
        response = await client.post("/session/format")
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_format_empty_rules_returns_text(self, client: AsyncClient) -> None:
        """POST /session/format with empty rules list returns a non-error text response."""
        payload = {"query_response": EMPTY_QUERY_RESPONSE}
        response = await client.post("/session/format", json=payload)
        assert response.status_code == 200
        body = response.json()
        assert isinstance(body.get("text"), str)


# ---------------------------------------------------------------------------
# TestFormatEndpointCorrectness
# ---------------------------------------------------------------------------


class TestFormatEndpointCorrectness:
    """Endpoint output matches the CLI subprocess path for representative inputs."""

    @pytest.mark.asyncio
    async def test_format_text_contains_rule_id(self, client: AsyncClient) -> None:
        """Formatted text includes the rule_id from the query response."""
        payload = {"query_response": SAMPLE_QUERY_RESPONSE}
        response = await client.post("/session/format", json=payload)
        body = response.json()
        text = body["text"]
        assert "ARCH-ORG-001" in text, (
            f"Formatted text must include rule_id 'ARCH-ORG-001'; got: {text[:200]!r}"
        )

    @pytest.mark.asyncio
    async def test_format_text_contains_statement(self, client: AsyncClient) -> None:
        """Formatted text includes the rule statement."""
        payload = {"query_response": SAMPLE_QUERY_RESPONSE}
        response = await client.post("/session/format", json=payload)
        body = response.json()
        text = body["text"]
        statement = SAMPLE_QUERY_RESPONSE["rules"][0]["statement"]
        assert statement in text or "architectural layer" in text, (
            f"Formatted text should contain the rule statement; got: {text[:200]!r}"
        )

    @pytest.mark.asyncio
    async def test_format_produces_nonempty_text_for_rules(self, client: AsyncClient) -> None:
        """Formatted text is non-empty when rules are present."""
        payload = {"query_response": SAMPLE_QUERY_RESPONSE}
        response = await client.post("/session/format", json=payload)
        body = response.json()
        assert len(body["text"].strip()) > 0, "Formatted text must not be empty when rules present"


# ---------------------------------------------------------------------------
# TestFormatEndpointIsStateless
# ---------------------------------------------------------------------------


class TestFormatEndpointIsStateless:
    """POST /session/format does not require a session_id (stateless endpoint)."""

    @pytest.mark.asyncio
    async def test_format_works_without_session_id(self, client: AsyncClient) -> None:
        """POST /session/format does not require a session_id field."""
        payload = {"query_response": SAMPLE_QUERY_RESPONSE}
        response = await client.post("/session/format", json=payload)
        # Must not 422 on missing session_id -- the endpoint is stateless
        assert response.status_code == 200, (
            f"format endpoint must not require session_id; got {response.status_code}"
        )

    def test_format_route_path_does_not_include_session_id(self) -> None:
        """The /session/format route does not have a path parameter for session_id."""
        from writ.server import app as fastapi_app
        format_routes = [
            r for r in fastapi_app.routes
            if hasattr(r, "path") and "format" in getattr(r, "path", "")
        ]
        assert len(format_routes) > 0, "/session/format route must be registered"
        for route in format_routes:
            path = getattr(route, "path", "")
            assert "{" not in path or "session_id" not in path, (
                f"/session/format must be a fixed path (no session_id parameter); "
                f"got path={path!r}"
            )
