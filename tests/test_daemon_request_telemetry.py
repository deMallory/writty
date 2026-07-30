"""P2 item 7: one metrics row per daemon HTTP request.

The daemon emitted 17 domain events (phase_advance, candidate_promoted, quality_judgment
and so on) but nothing per REQUEST, so latency, status and error rate per route were
unobservable across all ~30 routes -- including /query and /pre-write-check, which every
hook calls every turn. Because hooks fail open by design, a slow or 500-ing daemon showed
up only as enforcement quietly degrading, with nothing in any stream to point at it.

These drive the real app through Starlette's TestClient with WRIT_FRICTION_LOG pointed at a
temp file, so the assertions read the actual emitted rows rather than a mock.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi import FastAPI
from starlette.testclient import TestClient


@pytest.fixture
def rows(tmp_path, monkeypatch):
    """Emitted events, as a callable returning the parsed rows written so far.

    WRIT_FRICTION_LOG collapses every stream to one file (the documented back-compat
    behavior), which is what makes a single-file assertion valid here.
    """
    log = tmp_path / "events.jsonl"
    monkeypatch.setenv("WRIT_FRICTION_LOG", str(log))

    def _read() -> list[dict]:
        if not log.exists():
            return []
        out = []
        for line in log.read_text().splitlines():
            line = line.strip()
            if line:
                try:
                    out.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
        return out

    return _read


@pytest.fixture
def client():
    from writ.server import app

    return TestClient(app, raise_server_exceptions=False)


def _requests(rows) -> list[dict]:
    return [r for r in rows() if r.get("event") == "daemon_request"]


class TestOneRowPerRequest:
    def test_request_emits_a_daemon_request_row(self, client, rows):
        client.get("/session/telemetry-probe/current-phase")
        recorded = _requests(rows)
        assert len(recorded) == 1, f"expected exactly one row; got {recorded}"

    def test_row_carries_route_method_status_and_duration(self, client, rows):
        client.get("/session/telemetry-probe/current-phase")
        row = _requests(rows)[0]
        assert row["method"] == "GET"
        assert row["status"] == 200
        assert isinstance(row["duration_ms"], (int, float))
        assert row["duration_ms"] >= 0
        assert "current-phase" in row["route"]

    def test_route_is_the_template_not_the_concrete_path(self, client, rows):
        """Rows must aggregate: one identity per route, not one per session id.

        With the concrete path, /session/<uuid>/current-phase would produce a distinct
        route value for every session ever seen, and no per-route latency or error rate
        could be computed.
        """
        client.get("/session/aaaaaaaa-1111/current-phase")
        client.get("/session/bbbbbbbb-2222/current-phase")
        routes = {r["route"] for r in _requests(rows)}
        assert len(routes) == 1, f"route should be shared across session ids; got {routes}"
        assert "{session_id}" in routes.pop()

    def test_session_id_is_captured_from_the_path(self, client, rows):
        client.get("/session/sid-from-path/current-phase")
        assert _requests(rows)[0]["session"] == "sid-from-path"


class TestFailurePathsAreRecorded:
    def test_unknown_route_is_recorded_with_its_status(self, client, rows):
        """A 404 has no matched route, so the concrete path is the only identity left."""
        client.get("/no/such/route")
        row = _requests(rows)[0]
        assert row["status"] == 404
        assert row["route"] == "/no/such/route"

    def test_handler_exception_is_recorded_as_500_and_still_raises(self, rows, monkeypatch):
        """A raising handler must still produce a row: that is the case worth seeing.

        A `return`-only middleware records successes and silently drops the failures, which
        would leave exactly the errors invisible.
        """
        from writ.server import _request_telemetry

        probe = FastAPI()
        probe.middleware("http")(_request_telemetry)

        @probe.get("/boom")
        async def boom():
            raise RuntimeError("intentional")

        with TestClient(probe, raise_server_exceptions=False) as c:
            resp = c.get("/boom")
        assert resp.status_code == 500
        row = [r for r in rows() if r.get("event") == "daemon_request"][0]
        assert row["status"] == 500
        assert row["route"] == "/boom"


class TestNoiseAndSafety:
    def test_health_is_not_recorded(self, client, rows):
        """/health is polled by ensure-server, the SessionStart hook, doctor and the tests.

        Recording it would swamp the stream with rows nobody reads.
        """
        client.get("/health")
        assert _requests(rows) == []

    def test_a_broken_emit_cannot_break_the_request(self, client, rows, monkeypatch):
        """Telemetry must never be able to fail the thing it observes."""
        import writ.server as server

        def explode(*a, **k):
            raise RuntimeError("emit is broken")

        monkeypatch.setattr(server, "emit", explode)
        resp = client.get("/session/telemetry-probe/current-phase")
        assert resp.status_code == 200, "a failing emit must not affect the response"


class TestStreamRegistration:
    def test_daemon_request_maps_to_metrics(self):
        """Audit C3 was live events missing from STREAM_MAP; keep the inventory complete."""
        from writ.shared.logging import STREAM_MAP

        assert STREAM_MAP.get("daemon_request") == "metrics"

    def test_rows_land_on_the_metrics_stream(self, tmp_path, monkeypatch):
        """Without WRIT_FRICTION_LOG collapsing streams, the row must go to metrics.jsonl."""
        monkeypatch.delenv("WRIT_FRICTION_LOG", raising=False)
        monkeypatch.setenv("WRIT_LOG_ROOT", str(tmp_path))
        from writ.server import app

        with TestClient(app, raise_server_exceptions=False) as c:
            c.get("/session/stream-probe/current-phase")

        metrics = list(Path(tmp_path).rglob("metrics.jsonl"))
        assert metrics, f"no metrics.jsonl written under {tmp_path}"
        text = "\n".join(p.read_text() for p in metrics)
        assert "daemon_request" in text
