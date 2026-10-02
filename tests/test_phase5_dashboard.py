"""Phase 5: GET /dashboard server-rendered HTML route.

Verifies the route returns 200 + text/html, contains a section for
each documented metric, includes the meta-refresh tag, and renders
gracefully when the friction log is empty.
"""
from __future__ import annotations

import html
import json
import os
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from writ import server
from writ.dashboard import render_dashboard
from writ.server import app

# Captured at import, before any fixture moves HOME.
_REAL_HOME = os.path.expanduser("~")


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture(autouse=True)
def isolated_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """The Pair Ledger sections read ~/.claude and the graph. Point both away from
    the operator: HOME at an empty temp dir, and no graph connection."""
    home = tmp_path / "home"
    (home / ".claude").mkdir(parents=True)
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setattr(server, "_db", None)
    return home


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
        assert '<div class="fig"><b>3</b><span>events</span></div>' in body
        assert '<div class="fig"><b>3</b><span>sessions</span></div>' in body

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


class _StubDb:
    """Stands in for server._db: only list_all_memories, with the real row shape."""

    def __init__(self, rows: list[dict] | None = None, error: Exception | None = None) -> None:
        self.rows = rows or []
        self.error = error

    async def list_all_memories(self) -> list[dict]:
        if self.error:
            raise self.error
        return self.rows


def _memory_project(home: Path, cwd: str, notes: dict[str, str]) -> str:
    """~/.claude/projects/<encoded>/ with a transcript naming cwd and the given note bodies."""
    encoded = cwd.replace("/", "-")
    project_dir = home / ".claude" / "projects" / encoded
    (project_dir / "memory").mkdir(parents=True)
    (project_dir / "s1.jsonl").write_text(json.dumps({"cwd": cwd}) + "\n")
    for name, body in notes.items():
        (project_dir / "memory" / f"{name}.md").write_text(
            f"---\nname: {name}\ndescription: d\nmetadata:\n  type: project\n---\n\n{body}\n"
        )
    return encoded


class TestDashboardPairLedger:
    """Step 2 of the Pair Ledger: rule sources, memory copies and stale notes."""

    @pytest.mark.parametrize("phrase", [
        "what we follow",
        "copied into writ",
        "notes untouched for 90 days or more",
    ])
    def test_section_present(self, phrase: str, client: TestClient, empty_log: Path) -> None:
        assert phrase in client.get("/dashboard").text.lower()

    def test_rule_source_row_comes_from_home(
        self, client: TestClient, empty_log: Path, isolated_home: Path
    ) -> None:
        (isolated_home / ".claude" / "CLAUDE.md").write_text("- one\n- two\n")
        body = client.get("/dashboard").text
        assert '<td>global<span class="sub mono">~/.claude/CLAUDE.md</span></td><td>2 rules</td>' in body

    def test_an_untracked_source_is_a_marked_check_row(
        self, client: TestClient, empty_log: Path, isolated_home: Path
    ) -> None:
        (isolated_home / ".claude" / "CLAUDE.md").write_text("- one\n")
        body = client.get("/dashboard").text
        row = body[body.index('<tr class="gap"><td>global'):]
        row = row[:row.index("</tr>")]
        assert '<span class="chip check">this Mac only</span>' in row

    def test_memory_section_says_graph_not_reachable_without_db(
        self, client: TestClient, empty_log: Path
    ) -> None:
        resp = client.get("/dashboard")
        assert resp.status_code == 200
        assert "graph not reachable" in resp.text.lower()

    def test_memory_counts_use_rows_from_db(
        self, client: TestClient, empty_log: Path, isolated_home: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        encoded = _memory_project(isolated_home, "/work/alpha", {"n1": "body"})
        row = {"name": "n1", "project": encoded, "path": "", "status": "live", "type": "project",
               "updated_at": "2026-09-01T00:00:00Z", "description": "d", "body": "body"}
        monkeypatch.setattr(server, "_db", _StubDb([row]))
        body = client.get("/dashboard").text
        assert '<span class="lab">alpha</span>' in body
        assert '<span class="val">1 of 1</span>' in body
        assert "graph not reachable" not in body.lower()

    def test_memory_meter_shares_one_scale_and_names_outdated_notes(
        self, client: TestClient, empty_log: Path, isolated_home: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        alpha = _memory_project(isolated_home, "/work/alpha", {"n1": "body", "n2": "new"})
        _memory_project(isolated_home, "/work/beta", {"m1": "x"})

        def row(name: str, body: str) -> dict:
            return {"name": name, "project": alpha, "path": "", "status": "live", "type": "project",
                    "updated_at": "2026-09-01T00:00:00Z", "description": "d", "body": body}

        monkeypatch.setattr(server, "_db", _StubDb([row("n1", "body"), row("n2", "old")]))
        body = client.get("/dashboard").text
        # alpha has 2 notes, beta 1: the longest bar is 100%, the others are measured against it.
        assert '<span class="lab">alpha</span><div class="m-bar" style="width:100.0%">' in body
        assert '<span class="lab">beta</span><div class="m-bar" style="width:50.0%">' in body
        assert '<span class="val">2 of 2, 1 outdated</span>' in body
        assert '<span class="val">0 of 1</span>' in body
        assert "Outdated copies: n2 (alpha)" in body

    def test_stale_note_row_shows_date_and_age(
        self, client: TestClient, empty_log: Path, isolated_home: Path
    ) -> None:
        encoded = _memory_project(isolated_home, "/work/alpha", {"n_old": "body"})
        note = isolated_home / ".claude" / "projects" / encoded / "memory" / "n_old.md"
        mtime = time.time() - 120 * 86400 - 3600
        os.utime(note, (mtime, mtime))
        date = datetime.fromtimestamp(mtime, UTC).strftime("%Y-%m-%d")
        body = client.get("/dashboard").text
        assert f"<td>n_old</td><td>alpha</td><td>{date}, 120 days</td>" in body

    def test_raising_db_read_still_renders_200(
        self, client: TestClient, empty_log: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(server, "_db", _StubDb(error=RuntimeError("graph down")))
        resp = client.get("/dashboard")
        assert resp.status_code == 200
        assert "graph not reachable" in resp.text.lower()

    def test_render_without_arguments_still_works(self, empty_log: Path) -> None:
        assert "graph not reachable" in render_dashboard().lower()

    def test_never_reads_the_operator_home(self, client: TestClient, empty_log: Path) -> None:
        assert _REAL_HOME not in client.get("/dashboard").text


BANDS = {
    "What we follow": ["Rule sources"],
    "What holds": [
        "Live counts", "Rule effectiveness", "Skill usage", "Playbook compliance",
        "Graduation candidates", "Quality judge false positives",
    ],
    "What's gone stale": [
        "Claude's memory, copied into Writ", "Notes untouched for 90 days or more",
        "Trim candidates",
    ],
}


def _bands(body: str) -> list[str]:
    """The page split at each band, masthead dropped."""
    return body.split('<section class="band"')[1:]


class TestDashboardDesign:
    """Step 3 of the Pair Ledger: the sketch's design applied to the whole page."""

    def test_masthead_names_the_page_and_its_source(
        self, client: TestClient, split_streams: dict[str, Path]
    ) -> None:
        body = client.get("/dashboard").text
        assert "<title>Pair Ledger</title>" in body
        assert "<h1>Pair Ledger</h1>" in body
        assert "The rules you and Claude both work by." in body
        masthead = body[:body.index('<section class="band"')]
        assert f"log: {split_streams['friction'].parent}" in masthead
        assert "refreshes every 60s" in masthead

    def test_three_bands_in_order(self, client: TestClient, empty_log: Path) -> None:
        bands = _bands(client.get("/dashboard").text)
        assert len(bands) == 3
        for band, title in zip(bands, BANDS, strict=True):
            assert f"<h2>{html.escape(title)}</h2>" in band, title

    @pytest.mark.parametrize("band_title", list(BANDS))
    def test_each_section_sits_in_its_band(
        self, band_title: str, client: TestClient, synthetic_log: Path
    ) -> None:
        bands = dict(zip(BANDS, _bands(client.get("/dashboard").text), strict=True))
        for section in BANDS[band_title]:
            assert html.escape(section) in bands[band_title], f"{section!r} not under {band_title!r}"

    def test_friction_headers_are_plain_words(self, client: TestClient, synthetic_log: Path) -> None:
        body = client.get("/dashboard").text
        assert "<th>Stick rate</th>" in body
        assert "stick_rate" not in body

    def test_tables_scroll_inside_their_own_box(self, client: TestClient, synthetic_log: Path) -> None:
        body = client.get("/dashboard").text
        assert body.count("<table>") == body.count('<div class="table-wrap"><table>') > 0

    @pytest.mark.parametrize("sync,kind", [
        ("in git", "ok"),
        ("copy in dotfiles, same", "ok"),
        ("copy in dotfiles, differs", "check"),
        ("this Mac only", "check"),
        ("missing", "check"),
    ])
    def test_every_sync_state_maps_to_a_chip(self, sync: str, kind: str) -> None:
        from writ.dashboard import _sync_chip

        assert _sync_chip(sync) == f'<span class="chip {kind}">{sync}</span>'

    def test_dark_mode_and_narrow_screens_are_styled(self, client: TestClient, empty_log: Path) -> None:
        body = client.get("/dashboard").text
        assert "@media (prefers-color-scheme: dark)" in body
        assert "@media (max-width: 760px)" in body

    def test_page_loads_nothing_from_outside(self, client: TestClient, empty_log: Path) -> None:
        body = client.get("/dashboard").text.lower()
        for marker in ("<script", "<link", "googleapis", "http://", "https://"):
            assert marker not in body, marker
