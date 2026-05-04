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
    monkeypatch.setattr(writ_session, "CACHE_DIR", str(cache_dir))
    return p


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
