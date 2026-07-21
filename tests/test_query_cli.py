"""Tests for the `writ query` CLI command: server-routing default with a
graceful in-process fallback.

Per TEST-EDGE-001 the fallback (error) path is tested, not just the happy
path. Regression for the except-clause that previously caught only
ConnectError/ReadTimeout and let an HTTPStatusError from raise_for_status()
propagate as an uncaught traceback instead of falling back. The in-process
path is mocked so the test needs no Neo4j/encoder.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
from typer.testing import CliRunner

from writ.cli import app

runner = CliRunner()

_RESULT = {
    "rules": [
        {"score": 0.9, "rule_id": "SEC-INJ-SQL-001", "statement": "Parameterized queries only."}
    ],
    "mode": "full",
    "total_candidates": 3,
    "latency_ms": 1.2,
}


def _in_process_patches():
    """Patch the in-process pipeline path so it needs no real DB/encoder.

    Returns (context-managers list, pipeline mock) for the caller to enter.
    """
    pipeline = MagicMock()
    pipeline.query.return_value = _RESULT
    db = MagicMock()
    db.close = AsyncMock()
    cms = [
        patch("writ.cli.get_neo4j_uri", return_value="bolt://localhost:7687"),
        patch("writ.cli.get_neo4j_user", return_value="neo4j"),
        patch("writ.cli.get_neo4j_password", return_value="x"),
        patch("writ.graph.db.Neo4jConnection", return_value=db),
        patch("writ.retrieval.pipeline.build_pipeline", AsyncMock(return_value=pipeline)),
    ]
    return cms, pipeline


def test_query_uses_server_when_reachable() -> None:
    """Default path POSTs to the server and renders its response."""
    ok_resp = MagicMock()
    ok_resp.raise_for_status.return_value = None
    ok_resp.json.return_value = _RESULT
    with patch("httpx.post", return_value=ok_resp) as post:
        result = runner.invoke(app, ["query", "sql in controller"])
    assert result.exit_code == 0, result.output
    post.assert_called_once()
    assert "Querying via server" in result.output
    assert "SEC-INJ-SQL-001" in result.output


def test_query_local_skips_server() -> None:
    """--local bypasses the server entirely (no httpx.post call)."""
    cms, _pipeline = _in_process_patches()
    with patch("httpx.post") as post:
        for cm in cms:
            cm.start()
        try:
            result = runner.invoke(app, ["query", "sql in controller", "--local"])
        finally:
            for cm in cms:
                cm.stop()
    assert result.exit_code == 0, result.output
    post.assert_not_called()
    assert "SEC-INJ-SQL-001" in result.output


def test_query_falls_back_on_http_error_status() -> None:
    """A server error status (raise_for_status -> HTTPStatusError) must fall
    back to the in-process pipeline, not crash with an uncaught exception."""
    bad_resp = MagicMock()
    bad_resp.raise_for_status.side_effect = httpx.HTTPStatusError(
        "500 Server Error", request=MagicMock(), response=MagicMock()
    )
    cms, pipeline = _in_process_patches()
    with patch("httpx.post", return_value=bad_resp):
        for cm in cms:
            cm.start()
        try:
            result = runner.invoke(app, ["query", "sql in controller"])
        finally:
            for cm in cms:
                cm.stop()
    assert result.exit_code == 0, result.output
    assert "falling back to" in result.output.lower()
    pipeline.query.assert_called_once()
    assert "SEC-INJ-SQL-001" in result.output
