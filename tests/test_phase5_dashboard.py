"""Phase 5: GET /dashboard server-rendered HTML route.

Verifies the route returns 200 + text/html, contains a section for
each documented metric, includes the meta-refresh tag, and renders
gracefully when the friction log is empty.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from writ.server import app


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture
def empty_log(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    p = tmp_path / "empty.log"
    p.write_text("")
    monkeypatch.setenv("WRIT_FRICTION_LOG", str(p))
    return p


@pytest.fixture
def synthetic_log(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    # Recent timestamps so events stay inside the analyzers' rolling since_days
    # windows; absolute past dates previously aged out (a time-bomb).
    base = datetime.now(UTC) - timedelta(days=1)

    def ts(offset: int) -> str:
        return (base + timedelta(seconds=offset)).strftime("%Y-%m-%dT%H:%M:%SZ")

    p = tmp_path / "synth.log"
    p.write_text(
        f'{{"ts":"{ts(0)}","session":"s1","mode":"work","event":"rag_query","rule_id":"ENF-X"}}\n'
        f'{{"ts":"{ts(1)}","session":"s1","mode":"work","event":"gate_denial","rule_id":"ENF-X","gate":"phase-a"}}\n'
        f'{{"ts":"{ts(5)}","session":"s1","mode":"work","event":"quality_judgment","judgment_id":"j1","rubric":"R1","decision":"fail","override":true,"latency_ms":120}}\n'
    )
    monkeypatch.setenv("WRIT_FRICTION_LOG", str(p))
    return p


class TestDashboardResponse:
    def test_returns_200_html(self, client: TestClient, empty_log: Path) -> None:
        resp = client.get("/dashboard")
        assert resp.status_code == 200
        assert "text/html" in resp.headers.get("content-type", "")

    def test_meta_refresh_tag_present(self, client: TestClient, empty_log: Path) -> None:
        resp = client.get("/dashboard")
        body = resp.text.lower()
        assert "<meta" in body and "http-equiv" in body and "refresh" in body, (
            "Dashboard must auto-refresh via meta tag (no JS framework)"
        )

    def test_no_javascript_framework(self, client: TestClient, empty_log: Path) -> None:
        body = client.get("/dashboard").text.lower()
        # A bit of inline JS is tolerable; framework imports are not.
        for blacklisted in ("react", "vue.js", "angular", "<script src"):
            assert blacklisted not in body, (
                f"Dashboard must render without JS framework; found {blacklisted!r}"
            )


class TestDashboardSections:
    """Each Phase 5 metric gets a section heading on the page."""

    EXPECTED_SECTIONS = [
        "rule effectiveness",
        "skill usage",
        "playbook compliance",
        "graduation",
        "trim",
        "quality judge",
    ]

    @pytest.mark.parametrize("phrase", EXPECTED_SECTIONS)
    def test_section_present(self, phrase: str, client: TestClient, synthetic_log: Path) -> None:
        body = client.get("/dashboard").text.lower()
        assert phrase in body, f"Dashboard missing section: {phrase!r}"


class TestDashboardEmptyLog:
    def test_renders_when_log_is_empty(self, client: TestClient, empty_log: Path) -> None:
        resp = client.get("/dashboard")
        assert resp.status_code == 200
        assert resp.text.strip(), "Dashboard must render content even on empty log"

    def test_does_not_throw_on_missing_log(self, client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("WRIT_FRICTION_LOG", str(tmp_path / "does-not-exist.log"))
        resp = client.get("/dashboard")
        assert resp.status_code == 200, (
            "Dashboard must degrade gracefully when the configured log is absent"
        )


class TestDashboardUsesAnalyzers:
    """ARCH-SSOT-001: dashboard reads from analyzer functions, not raw events."""

    def test_recompute_signal_present_in_response(self, client: TestClient, synthetic_log: Path) -> None:
        """Indirect check: data that requires the analyzer's stuck-denial
        logic (e.g. ENF-X rule appearing on the rule-effectiveness panel
        only when the analyzer aggregates it) is rendered. If the
        dashboard recomputed inline with different math the row would
        not match the analyzer's output."""
        body = client.get("/dashboard").text
        # Synthetic log has one ENF-X gate_denial. The analyzer should
        # surface it on the rule-effectiveness panel.
        assert "ENF-X" in body


def _row(event: str, session: str = "s1") -> str:
    ts = (datetime.now(UTC) - timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
    return f'{{"ts":"{ts}","session":"{session}","mode":"work","event":"{event}"}}\n'


@pytest.fixture
def split_streams(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, Path]:
    """The layout hooks write since the log split: one file per stream under
    WRIT_LOG_ROOT/<project>/, with WRIT_FRICTION_LOG unset. A legacy
    workflow-friction.log sits in the cwd, as it does in the daemon's checkout."""
    from writ.shared.logging import stream_path

    monkeypatch.delenv("WRIT_FRICTION_LOG", raising=False)
    monkeypatch.setenv("WRIT_LOG_ROOT", str(tmp_path / "logs"))
    monkeypatch.setenv("WRIT_LOG_PROJECT", "demo")
    monkeypatch.chdir(tmp_path)

    paths = {s: stream_path("demo", s) for s in ("audit", "friction", "metrics")}
    paths["audit"].parent.mkdir(parents=True)
    paths["audit"].write_text(_row("split_audit_row", "s1"))
    paths["friction"].write_text(_row("split_friction_row", "s2"))
    paths["metrics"].write_text(_row("split_metrics_row", "s3"))
    (tmp_path / "workflow-friction.log").write_text(_row("legacy_only_row", "old") * 5)
    return paths


class TestDashboardReadsSplitStreams:
    """Since the log split, hooks write to WRIT_LOG_ROOT/<project>/<stream>.jsonl.
    The dashboard kept reading ./workflow-friction.log, so it froze on the day
    of the split."""

    def test_counts_rows_from_every_split_stream(self, client: TestClient, split_streams: dict[str, Path]) -> None:
        body = client.get("/dashboard").text
        for event in ("split_audit_row", "split_friction_row", "split_metrics_row"):
            assert f"<td>{event}</td><td>1</td>" in body, f"{event} missing from Live counts"
        # Exact totals hold on a first GET: its own daemon_request row lands after render.
        assert "<td>total events</td><td>3</td>" in body
        assert "<td>distinct sessions</td><td>3</td>" in body

    def test_ignores_legacy_file_in_cwd(self, client: TestClient, split_streams: dict[str, Path]) -> None:
        body = client.get("/dashboard").text
        assert "legacy_only_row" not in body

    def test_footer_names_the_stream_directory(self, client: TestClient, split_streams: dict[str, Path]) -> None:
        body = client.get("/dashboard").text
        assert f"log: {split_streams['friction'].parent}" in body
        assert "log: workflow-friction.log" not in body

    def test_row_appended_after_a_render_shows_on_the_next(self, client: TestClient, split_streams: dict[str, Path]) -> None:
        assert "late_row" not in client.get("/dashboard").text
        with split_streams["friction"].open("a") as f:
            f.write(_row("late_row", "s4"))
        body = client.get("/dashboard").text
        # No exact total: the first GET logged its own daemon_request row into these streams.
        assert "<td>late_row</td><td>1</td>" in body

    def test_friction_log_env_still_names_one_file(
        self, client: TestClient, split_streams: dict[str, Path], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        single = tmp_path / "single.log"
        single.write_text(_row("single_file_row"))
        monkeypatch.setenv("WRIT_FRICTION_LOG", str(single))
        body = client.get("/dashboard").text
        assert "<td>single_file_row</td><td>1</td>" in body
        assert "split_friction_row" not in body
        assert f"log: {single}" in body
