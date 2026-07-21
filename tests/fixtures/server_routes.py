"""Shared FastAPI-route pytest fixtures for server-route tests.

Consolidates the byte-identical `client` and `isolated_cache` fixtures
formerly duplicated in the decision-memory capture and commit test files
(Wave-5 Cycle 5.3b). These are imported EXPLICITLY into each consuming test
module (`from tests.fixtures.server_routes import client, isolated_cache`),
never registered in a root conftest, so they cannot leak into the other test
files that define their own divergent `client` fixture.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from writ.server import app


@pytest.fixture()
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture()
def isolated_cache(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Isolate WRIT_CACHE_DIR and WRIT_FRICTION_LOG for server-route tests."""
    cache_dir = tmp_path / "writ-cache"
    cache_dir.mkdir()
    log_path = tmp_path / "workflow-friction.log"
    monkeypatch.setenv("WRIT_CACHE_DIR", str(cache_dir))
    monkeypatch.setenv("WRIT_FRICTION_LOG", str(log_path))
    return tmp_path
