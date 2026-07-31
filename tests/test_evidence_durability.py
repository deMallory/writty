"""P2 item 9: verification evidence and citations must outlive the session cache.

`verification_evidence` and `citation_log` lived ONLY in the session cache. Two ways that
loses the record:

  1. The cache is per-session and disposable. A claim whose evidence has evaporated is
     indistinguishable from a claim that never had any, which is the exact ambiguity the
     gate exists to remove.
  2. `citation_log` is trimmed to _CITATION_LOG_MAX on every append, so the OLDEST
     citations are dropped while the session is still running.

Both now mirror to the durable `audit` stream (365-day retention). The cache copy stays
the working set that gates read; the stream copy is the record.
"""
from __future__ import annotations

import json

import pytest


@pytest.fixture
def rows(tmp_path, monkeypatch):
    log = tmp_path / "events.jsonl"
    monkeypatch.setenv("WRIT_FRICTION_LOG", str(log))

    def _read(event: str | None = None) -> list[dict]:
        if not log.exists():
            return []
        out = []
        for line in log.read_text().splitlines():
            if not line.strip():
                continue
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                continue
            if event is None or r.get("event") == event:
                out.append(r)
        return out

    return _read


# --------------------------------------------------------------------------- #
# citations
# --------------------------------------------------------------------------- #
class TestCitationsAreDurable:
    def test_appending_a_citation_emits_an_audit_row(self, rows):
        from writ.session.citations import _append_citation

        cache: dict = {}
        _append_citation(cache, {"artifact_type": "file", "ref": "src/foo.py",
                                 "excerpt": "3 findings"}, "sid-1")
        row = rows("citation_recorded")[0]
        assert row["ref"] == "src/foo.py"
        assert row["artifact_type"] == "file"
        assert row["session"] == "sid-1"

    def test_the_row_carries_the_excerpt_hash(self, rows):
        """INV-7a's staleness signal has to survive too, or drift is undetectable."""
        from writ.session.citations import _append_citation

        cache: dict = {}
        _append_citation(cache, {"artifact_type": "url", "ref": "https://x", "excerpt": "abc"})
        row = rows("citation_recorded")[0]
        assert row["excerpt_hash"] == cache["citation_log"][0]["excerpt_hash"]

    def test_trimmed_citations_survive_on_the_stream(self, rows):
        """The headline case: the cache drops the oldest, the record keeps all of them."""
        from writ.session.citations import _append_citation
        from writ.session.config import _CITATION_LOG_MAX

        cache: dict = {}
        total = _CITATION_LOG_MAX + 5
        for i in range(total):
            _append_citation(cache, {"artifact_type": "file", "ref": f"f{i}.py"}, "sid-trim")

        assert len(cache["citation_log"]) == _CITATION_LOG_MAX, "cache stays bounded"
        recorded = rows("citation_recorded")
        assert len(recorded) == total, "every citation reached the stream"
        refs = [r["ref"] for r in recorded]
        assert "f0.py" in refs, (
            "the oldest citation was trimmed out of the cache; it must still be on the stream"
        )
        assert "f0.py" not in [c["ref"] for c in cache["citation_log"]]

    def test_session_id_is_optional(self, rows):
        """The two cmd_update handlers reach this through a (cache, args, i) dispatch."""
        from writ.session.citations import _append_citation

        cache: dict = {}
        _append_citation(cache, {"artifact_type": "command", "ref": "pytest -q"})
        row = rows("citation_recorded")[0]
        assert row["session"] == ""
        assert row["ref"] == "pytest -q"

    def test_the_stored_row_is_not_polluted_by_telemetry(self, rows):
        """The emit must not add fields to what the cache holds."""
        from writ.session.citations import _append_citation

        cache: dict = {}
        _append_citation(cache, {"artifact_type": "file", "ref": "a.py"}, "sid-x")
        stored = cache["citation_log"][0]
        assert "_session_id" not in stored
        assert set(stored) == {"artifact_type", "ref", "excerpt", "excerpt_hash", "ts"}


# --------------------------------------------------------------------------- #
# verification evidence
# --------------------------------------------------------------------------- #
class TestVerificationEvidenceIsDurable:
    @pytest.fixture
    def client(self, tmp_path, monkeypatch):
        from starlette.testclient import TestClient

        import writ.server as server

        monkeypatch.setenv("WRIT_CACHE_DIR", str(tmp_path / "cache"))
        (tmp_path / "cache").mkdir()
        # No context manager: the lifespan would connect Neo4j, which this route does
        # not need.
        return TestClient(server.app, raise_server_exceptions=False)

    def _post(self, client, sid="sid-ev", todo_id="todo-1"):
        return client.post(
            f"/session/{sid}/verification-evidence",
            json={"todo_id": todo_id, "command": "pytest -q",
                  "output_excerpt": "12 passed", "exit_code": 0},
        )

    def test_recording_evidence_emits_an_audit_row(self, client, rows):
        assert self._post(client).json()["ok"] is True
        row = rows("verification_evidence")[0]
        assert row["todo_id"] == "todo-1"
        assert row["command"] == "pytest -q"
        assert row["exit_code"] == 0
        assert row["output_excerpt"] == "12 passed"
        assert row["session"] == "sid-ev"

    def test_a_failing_command_is_recorded_too(self, client, rows):
        """A claim backed by a FAILING command is the most important row in the set."""
        client.post(
            "/session/sid-fail/verification-evidence",
            json={"todo_id": "t", "command": "pytest -q", "output_excerpt": "1 failed",
                  "exit_code": 1},
        )
        row = rows("verification_evidence")[0]
        assert row["exit_code"] == 1
        assert "failed" in row["output_excerpt"]

    def test_a_rejected_request_records_nothing(self, client, rows):
        """No todo_id means nothing was stored, so nothing may claim it was."""
        resp = client.post(
            "/session/sid-bad/verification-evidence",
            json={"todo_id": "", "command": "x", "output_excerpt": "y", "exit_code": 0},
        )
        assert resp.json()["ok"] is False
        assert rows("verification_evidence") == [], (
            "an audit row for evidence that was never stored is worse than no row"
        )

    def test_the_cache_copy_still_works(self, client, rows):
        """Gate 5 Tier 1 reads the cache; the stream is additive, not a replacement."""
        self._post(client, todo_id="todo-9")
        got = client.get("/session/sid-ev/verification-evidence?todo_id=todo-9").json()
        assert got["evidence"]["command"] == "pytest -q"


class TestStreamRegistration:
    @pytest.mark.parametrize("event", ["verification_evidence", "citation_recorded"])
    def test_evidence_events_route_to_audit(self, event):
        """Audit, not metrics: this is the oversight record, and it needs 365-day
        retention rather than the 90 metrics gets."""
        from writ.session.log_rotation import RETENTION_DAYS
        from writ.shared.logging import STREAM_MAP

        assert STREAM_MAP.get(event) == "audit"
        assert RETENTION_DAYS["audit"] == 365
