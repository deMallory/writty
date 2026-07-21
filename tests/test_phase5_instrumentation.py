"""Phase 5: instrumentation prereqs.

Verifies the two new friction-event types emit and round-trip:
  - quality_judgment (POST /session/{sid}/quality-judgment)
  - playbook_step_complete (POST /session/{sid}/active-playbook)

Both tests write to a real on-disk friction log via WRIT_FRICTION_LOG
(TEST-INT-001) and parse events back through FrictionEvent so the
JSON shape is verified end-to-end.
"""
from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from writ.analysis.friction import (
    FrictionEvent,
    analyze_playbook_compliance,
    analyze_quality_judge_false_positives,
    parse_log,
)
from writ.server import app


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture
def tmp_log(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    p = tmp_path / "workflow-friction.log"
    monkeypatch.setenv("WRIT_FRICTION_LOG", str(p))
    # Isolate the writ-session cache so prior runs of these tests cannot
    # pollute step_index counts via leftover playbook history files.
    cache_dir = tmp_path / "writ-cache"
    cache_dir.mkdir()
    monkeypatch.setenv("WRIT_CACHE_DIR", str(cache_dir))
    # writ-session.py reads CACHE_DIR at import time, so reach in and
    # override the module-level constant after the env var is set.
    from writ.server import writ_session
    monkeypatch.setenv("WRIT_CACHE_DIR", str(cache_dir))
    return p


class TestQualityJudgmentTypedBody:
    """Wave1 Cycle6 Target 3: quality-judgment validates its body through a
    typed SessionQualityJudgmentRequest model instead of the bare
    `int(body.get("score", 0))` at server.py:1616.
    """

    def test_nonnumeric_score_returns_422_not_500(self, tmp_log: Path) -> None:
        """RED today: `int("not-a-number")` raises an unhandled ValueError,
        which surfaces as a bare 500 -- confirmed live on HEAD via
        `TestClient(app, raise_server_exceptions=False)` (the module's
        shared `client` fixture uses the default raise_server_exceptions=True,
        which would instead propagate the ValueError as a Python exception in
        this process; using a local client here observes the actual HTTP
        status the route returns). After the Pydantic model lands, a
        non-numeric score must be a clean 422 validation error.
        """
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.post(
            "/session/quality-422-sess/quality-judgment",
            json={"artifact_path": "/tmp/x.md", "score": "not-a-number"},
        )
        assert resp.status_code == 422, (
            f"expected 422 (validation error), not a bare 500; "
            f"got {resp.status_code}: {resp.text}"
        )

    def test_numeric_score_still_returns_200(self, client: TestClient, tmp_log: Path) -> None:
        """Stability guard: the existing numeric-score happy path is
        unaffected by the typed-body fix. Passes both before and after."""
        resp = client.post(
            "/session/quality-200-sess/quality-judgment",
            json={"artifact_path": "/tmp/x.md", "score": 4, "rubric": "r"},
        )
        assert resp.status_code == 200
        assert resp.json()["ok"] is True

    def test_bool_score_returns_422(self, client: TestClient, tmp_log: Path) -> None:
        """A JSON bool score must be rejected with 422, not coerced to 0/1.

        Pydantic v2 lax mode coerces true->1 (bool subclasses int); the
        field_validator(mode="before") on `score` blocks the bool so a
        wrong-typed value fails validation.
        """
        resp = client.post(
            "/session/quality-bool-sess/quality-judgment",
            json={"artifact_path": "/tmp/x.md", "score": True, "rubric": "r"},
        )
        assert resp.status_code == 422, (
            f"expected 422 (validation error), got {resp.status_code}: {resp.text}"
        )


class TestActivePlaybookTypedBody:
    """Wave1 Cycle6 Target 3: active-playbook validates total_steps through a
    typed SessionActivePlaybookRequest model.
    """

    def test_wrong_typed_total_steps_returns_422(
        self, client: TestClient, tmp_log: Path
    ) -> None:
        """RED today: `body: dict` never casts total_steps at all --
        `body.get("total_steps")` is stored and returned as-is, so a
        non-numeric string is silently accepted, returning 200 (confirmed
        live on HEAD). Once total_steps is a typed `int | None` field, a
        non-numeric string must fail Pydantic validation with 422.
        """
        resp = client.post(
            "/session/playbook-422-sess/active-playbook",
            json={"playbook_id": "pb1", "phase_id": "p1", "total_steps": "ten"},
        )
        assert resp.status_code == 422, (
            f"expected 422 (validation error), got {resp.status_code}: {resp.text}"
        )

    def test_bool_total_steps_returns_422(
        self, client: TestClient, tmp_log: Path
    ) -> None:
        """A JSON bool total_steps must be rejected with 422, not coerced.

        Pydantic v2 lax mode coerces true->1 (bool subclasses int); the
        field_validator(mode="before") on `total_steps` blocks the bool while
        still passing None and real ints/strings through for lax coercion.
        """
        resp = client.post(
            "/session/playbook-bool-sess/active-playbook",
            json={"playbook_id": "pb1", "phase_id": "p1", "total_steps": True},
        )
        assert resp.status_code == 422, (
            f"expected 422 (validation error), got {resp.status_code}: {resp.text}"
        )

    def test_numeric_total_steps_still_returns_200(
        self, client: TestClient, tmp_log: Path
    ) -> None:
        """Stability guard: a valid numeric total_steps keeps today's 200."""
        resp = client.post(
            "/session/playbook-ok-sess/active-playbook",
            json={"playbook_id": "pb1", "phase_id": "p1", "total_steps": 3},
        )
        assert resp.status_code == 200
        assert resp.json()["ok"] is True


class TestVerificationEvidenceTypedBody:
    """Wave1 Cycle6 / FIX D: verification-evidence validates exit_code through a
    typed SessionVerificationEvidenceRequest model that rejects a JSON bool.
    """

    def test_bool_exit_code_returns_422(self, client: TestClient, tmp_log: Path) -> None:
        """A JSON bool exit_code must be rejected with 422, not coerced to 0/1."""
        resp = client.post(
            "/session/ve-bool-sess/verification-evidence",
            json={"todo_id": "t1", "exit_code": True},
        )
        assert resp.status_code == 422, (
            f"expected 422 (validation error), got {resp.status_code}: {resp.text}"
        )

    def test_numeric_exit_code_still_returns_200(
        self, client: TestClient, tmp_log: Path
    ) -> None:
        """Stability guard: a valid numeric exit_code keeps today's 200."""
        resp = client.post(
            "/session/ve-ok-sess/verification-evidence",
            json={
                "todo_id": "t1", "command": "pytest",
                "output_excerpt": "ok", "exit_code": 0,
            },
        )
        assert resp.status_code == 200
        assert resp.json()["ok"] is True


class TestQualityJudgmentEvent:
    """POST /quality-judgment emits quality_judgment friction events."""

    def test_event_emitted_with_required_fields(self, client: TestClient, tmp_log: Path) -> None:
        resp = client.post(
            "/session/test-sess/quality-judgment",
            json={
                "artifact_path": "/tmp/x.md",
                "score": 1,
                "rationale": "boilerplate",
                "rubric": "plan-specificity",
                "overridden": False,
            },
        )
        assert resp.status_code == 200
        events = parse_log(tmp_log)
        judgments = [e for e in events if e.event == "quality_judgment"]
        assert len(judgments) >= 1, f"no quality_judgment events; saw {[e.event for e in events]}"
        ev = judgments[-1].model_dump()
        for f in ("judgment_id", "rubric", "decision", "override", "latency_ms"):
            assert f in ev, f"quality_judgment must include {f!r}; got {ev}"

    def test_decision_derived_from_score(self, client: TestClient, tmp_log: Path) -> None:
        client.post(
            "/session/s1/quality-judgment",
            json={"artifact_path": "/tmp/pass.md", "score": 4, "rubric": "r"},
        )
        client.post(
            "/session/s1/quality-judgment",
            json={"artifact_path": "/tmp/fail.md", "score": 1, "rubric": "r"},
        )
        events = parse_log(tmp_log)
        judgments = [e.model_dump() for e in events if e.event == "quality_judgment"]
        decisions = {j.get("decision") for j in judgments}
        assert "pass" in decisions
        assert "fail" in decisions

    def test_override_flag_propagates(self, client: TestClient, tmp_log: Path) -> None:
        client.post(
            "/session/s1/quality-judgment",
            json={
                "artifact_path": "/tmp/ovr.md", "score": 1,
                "rubric": "r", "overridden": True,
            },
        )
        events = parse_log(tmp_log)
        ev = next(e for e in events if e.event == "quality_judgment").model_dump()
        assert ev["override"] is True


class TestPlaybookStepCompleteEvent:
    """POST /active-playbook emits playbook_step_complete events."""

    def test_event_emitted_when_step_advances(self, client: TestClient, tmp_log: Path) -> None:
        resp = client.post(
            "/session/sess-pb/active-playbook",
            json={"playbook_id": "PBK-TEST-001", "phase_id": "step-1", "total_steps": 3},
        )
        assert resp.status_code == 200
        events = parse_log(tmp_log)
        steps = [e for e in events if e.event == "playbook_step_complete"]
        assert len(steps) == 1
        ev = steps[0].model_dump()
        for f in ("playbook_id", "step_id", "step_index", "total_steps"):
            assert f in ev, f"playbook_step_complete must include {f!r}"
        assert ev["playbook_id"] == "PBK-TEST-001"
        assert ev["step_id"] == "step-1"

    def test_step_index_increments_across_calls(self, client: TestClient, tmp_log: Path) -> None:
        for step in ("s1", "s2", "s3"):
            client.post(
                "/session/sess-multi/active-playbook",
                json={"playbook_id": "PBK-Q", "phase_id": step, "total_steps": 3},
            )
        events = parse_log(tmp_log)
        steps = [e.model_dump() for e in events if e.event == "playbook_step_complete"]
        indices = [s["step_index"] for s in steps]
        assert indices == [0, 1, 2]


class TestAnalyzersConsumeNewEvents:
    """Confirms downstream analyzers actually read the new events."""

    def test_quality_judgment_feeds_false_positive_analyzer(
        self, client: TestClient, tmp_log: Path
    ) -> None:
        client.post(
            "/session/sf/quality-judgment",
            json={
                "artifact_path": "/tmp/x.md", "score": 1,
                "rubric": "RUB-A", "overridden": True,
            },
        )
        events = parse_log(tmp_log)
        rows = analyze_quality_judge_false_positives(events, since_days=30)
        assert any(r.overrides >= 1 for r in rows)

    def test_playbook_step_complete_feeds_compliance_analyzer(
        self, client: TestClient, tmp_log: Path
    ) -> None:
        for i, step in enumerate(("s1", "s2", "s3")):
            client.post(
                "/session/spc/active-playbook",
                json={"playbook_id": "PBK-X", "phase_id": step, "total_steps": 3},
            )
        events = parse_log(tmp_log)
        rows = analyze_playbook_compliance(events, since_days=30)
        assert any(r.playbook_id == "PBK-X" for r in rows)

    def test_round_trips_through_friction_event(self, client: TestClient, tmp_log: Path) -> None:
        client.post(
            "/session/sr/quality-judgment",
            json={"artifact_path": "/tmp/x.md", "score": 4, "rubric": "r"},
        )
        events = parse_log(tmp_log)
        for ev in events:
            assert isinstance(ev, FrictionEvent)
