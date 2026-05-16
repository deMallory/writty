"""Item 3a: POST /session/{id}/mode lowercases and validates mode values.

The HTTP endpoint must route through _mode_set so mode is canonicalized
to lowercase and validated against VALID_MODES before being stored in
the session cache.
"""

from __future__ import annotations

import importlib
import importlib.util
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio

try:
    from httpx import AsyncClient, ASGITransport
except ImportError:
    pytestmark = pytest.mark.skip(reason="httpx not installed")

from writ.server import app  # type: ignore[import]

SESSION_ID = "test-mode-canon-001"
SKILL_DIR = "/home/lucio.saldivar/.claude/skills/writ"
WRIT_SESSION_PY = f"{SKILL_DIR}/bin/lib/writ-session.py"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _base_cache(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "session_id": SESSION_ID,
        "mode": None,
        "current_phase": "planning",
        "remaining_budget": 8000,
        "context_percent": 0,
        "loaded_rule_ids": [],
        "pending_violations": [],
        "escalation": {"needed": False},
        "invalidation_history": {},
        "gates_approved": [],
    }
    base.update(overrides)
    return base


@pytest.fixture()
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture()
def mock_writ_session():
    """Mock writ_session: _mode_set and _read_cache are wired to track calls."""
    written_cache: dict[str, Any] = _base_cache()
    mock = MagicMock()
    mock._read_cache = MagicMock(return_value=dict(written_cache))

    def _fake_mode_set(session_id: str, mode: str, **kwargs: Any) -> None:
        written_cache["mode"] = mode

    mock._mode_set = MagicMock(side_effect=_fake_mode_set)
    mock._write_cache = MagicMock()
    mock.DEFAULT_SESSION_BUDGET = 8000

    # Expose the written_cache so tests can inspect it
    mock._written_cache = written_cache
    return mock


@pytest_asyncio.fixture()
async def client(mock_writ_session):
    transport = ASGITransport(app=app)
    with patch("writ.server.writ_session", mock_writ_session):
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            yield ac


# ---------------------------------------------------------------------------
# TestModeCanonicalization
# ---------------------------------------------------------------------------


class TestModeCanonicalization:
    """POST /session/{id}/mode stores mode in lowercase regardless of input case."""

    @pytest.mark.asyncio
    async def test_title_case_work_stored_as_lowercase(
        self, client: AsyncClient, mock_writ_session
    ) -> None:
        """POST with 'Work' results in cache['mode'] == 'work'."""
        response = await client.post(
            f"/session/{SESSION_ID}/mode", json={"mode": "Work"}
        )
        assert response.status_code == 200
        assert mock_writ_session._written_cache["mode"] == "work", (
            f"Expected cache mode 'work'; got {mock_writ_session._written_cache['mode']!r}"
        )

    @pytest.mark.asyncio
    async def test_uppercase_work_stored_as_lowercase(
        self, client: AsyncClient, mock_writ_session
    ) -> None:
        """POST with 'WORK' results in cache['mode'] == 'work'."""
        response = await client.post(
            f"/session/{SESSION_ID}/mode", json={"mode": "WORK"}
        )
        assert response.status_code == 200
        assert mock_writ_session._written_cache["mode"] == "work", (
            f"Expected cache mode 'work'; got {mock_writ_session._written_cache['mode']!r}"
        )

    @pytest.mark.asyncio
    async def test_lowercase_work_stored_as_lowercase(
        self, client: AsyncClient, mock_writ_session
    ) -> None:
        """POST with 'work' results in cache['mode'] == 'work' (no change)."""
        response = await client.post(
            f"/session/{SESSION_ID}/mode", json={"mode": "work"}
        )
        assert response.status_code == 200
        assert mock_writ_session._written_cache["mode"] == "work"

    @pytest.mark.asyncio
    async def test_conversation_mode_canonicalized(
        self, client: AsyncClient, mock_writ_session
    ) -> None:
        """POST with 'Conversation' results in cache['mode'] == 'conversation'."""
        response = await client.post(
            f"/session/{SESSION_ID}/mode", json={"mode": "Conversation"}
        )
        assert response.status_code == 200
        assert mock_writ_session._written_cache["mode"] == "conversation"

    @pytest.mark.asyncio
    async def test_response_mode_field_is_lowercase(
        self, client: AsyncClient
    ) -> None:
        """Response body mode field is also lowercased."""
        response = await client.post(
            f"/session/{SESSION_ID}/mode", json={"mode": "Work"}
        )
        assert response.status_code == 200
        body = response.json()
        assert body.get("mode") == "work", (
            f"Response mode must be lowercase 'work'; got {body.get('mode')!r}"
        )


# ---------------------------------------------------------------------------
# TestModeValidation
# ---------------------------------------------------------------------------


class TestModeValidation:
    """Invalid mode values are rejected with HTTP 400."""

    @pytest.mark.asyncio
    async def test_invalid_mode_workflow_returns_400(
        self, client: AsyncClient
    ) -> None:
        """POST with 'Workflow' (not in VALID_MODES) returns HTTP 400."""
        response = await client.post(
            f"/session/{SESSION_ID}/mode", json={"mode": "Workflow"}
        )
        assert response.status_code == 400, (
            f"'Workflow' is not a valid mode; expected 400, got {response.status_code}"
        )

    @pytest.mark.asyncio
    async def test_invalid_mode_random_string_returns_400(
        self, client: AsyncClient
    ) -> None:
        """POST with an arbitrary unknown string returns HTTP 400."""
        response = await client.post(
            f"/session/{SESSION_ID}/mode", json={"mode": "bogusmode"}
        )
        assert response.status_code == 400

    @pytest.mark.asyncio
    async def test_invalid_mode_empty_string_returns_400(
        self, client: AsyncClient
    ) -> None:
        """POST with an empty string mode returns HTTP 400."""
        response = await client.post(
            f"/session/{SESSION_ID}/mode", json={"mode": ""}
        )
        assert response.status_code in (400, 422)

    @pytest.mark.asyncio
    async def test_400_response_contains_detail(
        self, client: AsyncClient
    ) -> None:
        """400 response includes a detail string describing the valid modes."""
        response = await client.post(
            f"/session/{SESSION_ID}/mode", json={"mode": "BadMode"}
        )
        assert response.status_code == 400
        body = response.json()
        # Must include some error description (detail key is standard FastAPI)
        assert "detail" in body or "error" in body, (
            f"400 response must include detail; body={body!r}"
        )


# ---------------------------------------------------------------------------
# TestModeSetRoutesThroughModeset
# ---------------------------------------------------------------------------


class TestModeSetRoutesThroughModeset:
    """HTTP endpoint delegates to _mode_set rather than writing cache directly."""

    @pytest.mark.asyncio
    async def test_mode_set_calls_underscore_mode_set(
        self, client: AsyncClient, mock_writ_session
    ) -> None:
        """_mode_set is called exactly once when POST /mode is invoked."""
        await client.post(f"/session/{SESSION_ID}/mode", json={"mode": "work"})
        mock_writ_session._mode_set.assert_called_once()

    @pytest.mark.asyncio
    async def test_mode_set_passes_lowercase_mode_to_underscore_mode_set(
        self, client: AsyncClient, mock_writ_session
    ) -> None:
        """_mode_set receives the lowercased mode string, not the raw input."""
        await client.post(f"/session/{SESSION_ID}/mode", json={"mode": "Work"})
        call_args = mock_writ_session._mode_set.call_args
        # The mode argument (positional or keyword) must be lowercase
        if call_args.args:
            passed_mode = call_args.args[1] if len(call_args.args) > 1 else call_args.args[0]
        else:
            passed_mode = call_args.kwargs.get("mode")
        assert passed_mode == "work", (
            f"_mode_set must receive lowercase mode; got {passed_mode!r}"
        )

    def test_server_source_imports_mode_set(self) -> None:
        """writ/server.py imports _mode_set from writ-session so routes use it."""
        import writ.server as server_module
        import importlib.util

        spec = importlib.util.find_spec("writ.server")
        assert spec is not None
        with open(spec.origin) as f:
            source = f.read()

        # The implementation must reference _mode_set (not inline the write logic)
        assert "_mode_set" in source, (
            "writ/server.py must import and call _mode_set from writ-session "
            "so CLI and HTTP paths share identical behavior"
        )
