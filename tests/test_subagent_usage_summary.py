"""Task 2 skeletons: the SubagentStop hook saves a durable per-subagent usage summary.

Plan: token-audit correctness repair, "Task 2 design (commit 2)". RED until
`hooks/scripts/writ-subagent-stop.sh` emits a `subagent_usage` row, `writ/shared/logging.py`
registers it in STREAM_MAP as `metrics`, and `writ/analysis/token_audit.py` gains
`load_usage_summaries`, `aggregate_file_usage` and `scorecard(..., usage_summaries=...)`.

ENF-SYS-005: the append-only / first-row-wins / never-blocks-the-stop claims are proven by
running the REAL hook in a subprocess against a sandboxed `WRIT_LOG_ROOT` with real files.
Neither `emit` nor friction-append is mocked.

SANDBOX. Every path the hook can reach is under `tmp_path`: WRIT_LOG_ROOT, WRIT_LOG_PROJECT
(so the metrics stream is `<root>/<project>/metrics.jsonl`), WRIT_CACHE_DIR, WRIT_PROJECTS_DIR,
the stop-payload capture file, HOME and XDG_STATE_HOME. `WRIT_FRICTION_LOG` is deliberately
UNSET: with it set, `emit` collapses every stream into that one file and the metrics stream
is never exercised. The Writ server port is pointed at an unreachable address and autostart
is disabled. Every inherited `WRIT_*` variable is dropped first.

Assumptions about interfaces that do not exist yet (pinned here so the implementer sees them):
- `aggregate_file_usage(path)` lives in `writ.analysis.token_audit` and returns a mapping with
  a `model_usage` key shaped like the summary row's `model_usage`.
- `load_usage_summaries(session_id, project)` returns `{agent_id: row}` (first row wins) and
  the `summary_conflict` warning surfaces on the scorecard's `warnings` when those summaries
  are audited.
"""
from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest

from tests.fixtures.token_audit_helpers import (
    agent_tool_use,
    load_token_audit,
    response_records,
    tool_result_record,
    usage,
    write_records,
    write_session_tree,
    write_subagent,
)

REPO = Path(__file__).resolve().parent.parent
STOP_HOOK = REPO / "hooks" / "scripts" / "writ-subagent-stop.sh"

PROJECT = "usage-summary-test"
PARENT_SESSION = "parent-sess"
AGENT_ID = "aaa1"
DISPATCH_ID = "toolu_P"


# --------------------------------------------------------------------------- #
# Sandbox harness (private to this file)
# --------------------------------------------------------------------------- #

class Sandbox:
    """Every writable location of one hook run, all under one tmp_path."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.log_root = root / "logs"
        self.cache = root / "cache"
        self.projects = root / "projects"
        self.home = root / "home"
        self.state = root / "state"
        self.capture = root / "stop-payloads.jsonl"
        for d in (self.log_root, self.cache, self.projects, self.home, self.state):
            d.mkdir(parents=True, exist_ok=True)
        # projects/<encoded-cwd>/<parent-session>/  (Claude Code's layout)
        self.session_dir = self.projects / "-sandbox-proj" / PARENT_SESSION
        self.parent_transcript = self.projects / "-sandbox-proj" / f"{PARENT_SESSION}.jsonl"

    @property
    def metrics(self) -> Path:
        return self.log_root / PROJECT / "metrics.jsonl"

    def env(self) -> dict:
        base = {k: v for k, v in os.environ.items() if not k.startswith("WRIT_")}
        env = {
            **base,
            "HOME": str(self.home),
            "XDG_STATE_HOME": str(self.state),
            "WRIT_LOG_ROOT": str(self.log_root),
            "WRIT_LOG_PROJECT": PROJECT,
            "WRIT_CACHE_DIR": str(self.cache),
            "WRIT_PROJECTS_DIR": str(self.projects),
            "WRIT_SUBAGENT_STOP_CAPTURE": str(self.capture),
            "WRIT_PORT": "59999",
            "WRIT_HOST": "127.0.0.1",
            "WRIT_NO_AUTOSTART": "1",
            "WRIT_DIR": str(REPO),
            "SKILL_DIR": str(REPO),
        }
        assert "WRIT_FRICTION_LOG" not in env
        return env

    def payload(self, agent_id: str = AGENT_ID, transcript: Path | None = None,
                agent_type: str = "") -> dict:
        p = {
            "agent_id": agent_id,
            "agent_type": agent_type,
            "session_id": PARENT_SESSION,
            "transcript_path": str(self.parent_transcript),
            "hook_event_name": "SubagentStop",
        }
        if transcript is not None:
            p["agent_transcript_path"] = str(transcript)
        return p

    def run_hook(self, payload: dict) -> subprocess.CompletedProcess:
        self.parent_transcript.parent.mkdir(parents=True, exist_ok=True)
        if not self.parent_transcript.exists():
            write_records(self.parent_transcript, [{"type": "user", "message": {"role": "user"}}])
        return subprocess.run(["bash", str(STOP_HOOK)], input=json.dumps(payload),
                              capture_output=True, text=True, env=self.env(), timeout=120)

    def metrics_rows(self, event: str | None = None) -> list[dict]:
        if not self.metrics.exists():
            return []
        rows = []
        for line in self.metrics.read_text(errors="replace").splitlines():
            try:
                row = json.loads(line)
            except ValueError:
                continue
            if event is None or row.get("event") == event:
                rows.append(row)
        return rows


@pytest.fixture()
def sandbox(tmp_path) -> Sandbox:
    return Sandbox(tmp_path)


def _hook_transcript(sandbox: Sandbox, agent_id: str = AGENT_ID) -> Path:
    """A subagent transcript with 4 unique responses across 3 raw models and 5 records.

    msg_1 opus-5-5 written as 2 records (a collapsed duplicate), msg_2 sonnet-5-5,
    msg_3 opus-5-5, msg_4 dated haiku that dispatches a child (toolu_X -> agent zzz).
    """
    records = (
        response_records("msg_1", "claude-opus-5-5",
                         usage(inp=1000, out=2000, read=100000, write=10000, c5=4000, c1=6000),
                         n_records=2, ts="2026-09-01T10:00:00Z")
        + response_records("msg_2", "claude-sonnet-5-5",
                           usage(inp=300, out=50, read=0, write=0), ts="2026-09-01T10:01:00Z")
        + response_records("msg_3", "claude-opus-5-5",
                           usage(inp=500, out=1000, read=200000, write=0),
                           ts="2026-09-01T10:02:00Z")
        + response_records("msg_4", "claude-haiku-4-5-20251001",
                           usage(inp=10000, out=1000, read=0, write=0),
                           tool_uses=[agent_tool_use("toolu_X", "writ-explorer")],
                           ts="2026-09-01T10:03:00Z")
        + [tool_result_record("toolu_X", "zzz", ts="2026-09-01T10:04:00Z")]
    )
    return write_subagent(
        sandbox.session_dir, agent_id, records,
        meta={"agentType": "writ:writ-explorer", "toolUseId": DISPATCH_ID, "spawnDepth": 1})


# --------------------------------------------------------------------------- #
# Sandbox soundness
# --------------------------------------------------------------------------- #

class TestSandbox:

    def test_every_env_path_is_under_tmp_and_friction_override_is_unset(self, sandbox,
                                                                       tmp_path) -> None:
        env = sandbox.env()
        assert "WRIT_FRICTION_LOG" not in env
        for key in ("HOME", "XDG_STATE_HOME", "WRIT_LOG_ROOT", "WRIT_CACHE_DIR",
                    "WRIT_PROJECTS_DIR", "WRIT_SUBAGENT_STOP_CAPTURE"):
            assert Path(env[key]).resolve().is_relative_to(tmp_path.resolve()), key
        assert env["WRIT_PORT"] == "59999"

    def test_a_hook_run_writes_only_inside_the_sandbox(self, sandbox, tmp_path) -> None:
        real_state = Path.home() / ".local" / "state" / "writ"
        before = sorted(p.name for p in real_state.iterdir()) if real_state.is_dir() else None
        transcript = _hook_transcript(sandbox)
        result = sandbox.run_hook(sandbox.payload(transcript=transcript))
        assert result.returncode == 0, result.stderr
        after = sorted(p.name for p in real_state.iterdir()) if real_state.is_dir() else None
        assert before == after, "the hook touched the real state root"
        assert sandbox.metrics.is_relative_to(tmp_path)


# --------------------------------------------------------------------------- #
# Capability: the hook appends one subagent_usage row
# --------------------------------------------------------------------------- #

class TestHookWritesUsageSummary:

    def test_exactly_one_subagent_usage_row_lands_in_the_metrics_stream(self, sandbox) -> None:
        transcript = _hook_transcript(sandbox)
        result = sandbox.run_hook(sandbox.payload(transcript=transcript))
        assert result.returncode == 0, result.stderr
        rows = sandbox.metrics_rows("subagent_usage")
        assert len(rows) == 1, f"expected one subagent_usage row, got {rows}"

    def test_row_identity_fields(self, sandbox) -> None:
        transcript = _hook_transcript(sandbox)
        sandbox.run_hook(sandbox.payload(transcript=transcript))
        row = sandbox.metrics_rows("subagent_usage")[0]
        assert row["agent_id"] == AGENT_ID
        assert row["session"] == AGENT_ID
        assert row["parent_session"] == PARENT_SESSION
        assert row["status"] == "ok"
        assert row["schema"] == 1

    def test_dispatch_id_comes_from_the_meta_tool_use_id(self, sandbox) -> None:
        transcript = _hook_transcript(sandbox)
        sandbox.run_hook(sandbox.payload(transcript=transcript))
        row = sandbox.metrics_rows("subagent_usage")[0]
        assert row["dispatch_id"] == DISPATCH_ID

    def test_role_is_normalized_and_its_source_recorded(self, sandbox) -> None:
        transcript = _hook_transcript(sandbox)
        sandbox.run_hook(sandbox.payload(transcript=transcript))
        row = sandbox.metrics_rows("subagent_usage")[0]
        assert row["role"] == "writ-explorer", "the writ: prefix must be stripped"
        assert row["role_source"] == "sidecar"

    def test_envelope_role_is_normalized_too(self, sandbox) -> None:
        transcript = _hook_transcript(sandbox)
        sandbox.run_hook(sandbox.payload(transcript=transcript, agent_type="writ:writ-planner"))
        row = sandbox.metrics_rows("subagent_usage")[0]
        assert row["role"] == "writ-planner"
        assert row["role_source"] == "envelope"

    def test_counts_and_per_model_tokens_are_deduped_by_response(self, sandbox) -> None:
        transcript = _hook_transcript(sandbox)
        sandbox.run_hook(sandbox.payload(transcript=transcript))
        row = sandbox.metrics_rows("subagent_usage")[0]
        assert row["responses"] == 4
        assert row["records"] == 5
        assert row["duplicates_collapsed"] == 1
        assert row["conflicts"] == 0
        assert row["model_usage"] == {
            "claude-opus-5-5": {"responses": 2, "input": 1500, "output": 3000,
                                "cache_read": 300000, "cache_write_5m": 4000,
                                "cache_write_1h": 6000},
            "claude-sonnet-5-5": {"responses": 1, "input": 300, "output": 50,
                                  "cache_read": 0, "cache_write_5m": 0,
                                  "cache_write_1h": 0},
            # the RAW model id is stored; normalization happens at audit time
            "claude-haiku-4-5-20251001": {"responses": 1, "input": 10000, "output": 1000,
                                          "cache_read": 0, "cache_write_5m": 0,
                                          "cache_write_1h": 0},
        }

    def test_model_usage_equals_aggregate_file_usage_on_the_same_transcript(
        self, sandbox
    ) -> None:
        transcript = _hook_transcript(sandbox)
        sandbox.run_hook(sandbox.payload(transcript=transcript))
        row = sandbox.metrics_rows("subagent_usage")[0]
        ta = load_token_audit()
        assert hasattr(ta, "aggregate_file_usage"), "aggregate_file_usage does not exist yet"
        agg = ta.aggregate_file_usage(str(transcript))
        assert row["model_usage"] == agg["model_usage"]

    def test_child_dispatches_map_tool_use_id_to_agent_id(self, sandbox) -> None:
        transcript = _hook_transcript(sandbox)
        sandbox.run_hook(sandbox.payload(transcript=transcript))
        row = sandbox.metrics_rows("subagent_usage")[0]
        assert row["child_dispatches"] == {"toolu_X": "zzz"}

    def test_timestamps_span_the_transcript(self, sandbox) -> None:
        transcript = _hook_transcript(sandbox)
        sandbox.run_hook(sandbox.payload(transcript=transcript))
        row = sandbox.metrics_rows("subagent_usage")[0]
        assert row["first_ts"] == "2026-09-01T10:00:00Z"
        assert row["last_ts"] == "2026-09-01T10:04:00Z"

    def test_row_stores_tokens_only_never_dollars(self, sandbox) -> None:
        transcript = _hook_transcript(sandbox)
        sandbox.run_hook(sandbox.payload(transcript=transcript))
        raw = json.dumps(sandbox.metrics_rows("subagent_usage")[0]).lower()
        assert "usd" not in raw and "cost" not in raw

    def test_hook_prints_nothing_on_stdout(self, sandbox) -> None:
        """A Stop-family additionalContext acts as a turn block."""
        transcript = _hook_transcript(sandbox)
        result = sandbox.run_hook(sandbox.payload(transcript=transcript))
        assert result.returncode == 0
        assert result.stdout == ""

    def test_the_existing_subagent_complete_row_is_still_written_once(self, sandbox) -> None:
        transcript = _hook_transcript(sandbox)
        sandbox.run_hook(sandbox.payload(transcript=transcript))
        rows = sandbox.metrics_rows("subagent_complete")
        assert len(rows) == 1
        assert rows[0]["agent_id"] == AGENT_ID

    def test_a_second_stop_appends_a_second_row_and_never_rewrites_the_first(
        self, sandbox
    ) -> None:
        """Append-only: the hook never edits history; first-row-wins is a READ rule."""
        transcript = _hook_transcript(sandbox)
        sandbox.run_hook(sandbox.payload(transcript=transcript))
        first = sandbox.metrics_rows("subagent_usage")[0]
        sandbox.run_hook(sandbox.payload(transcript=transcript))
        rows = sandbox.metrics_rows("subagent_usage")
        assert len(rows) == 2
        assert rows[0] == first

    def test_transcript_without_agent_transcript_path_is_derived_from_the_parent(
        self, sandbox
    ) -> None:
        """The resolver's flat derivation applies to the summary block too."""
        _hook_transcript(sandbox)
        sandbox.run_hook(sandbox.payload(transcript=None))
        rows = sandbox.metrics_rows("subagent_usage")
        assert len(rows) == 1 and rows[0]["status"] == "ok"
        assert rows[0]["responses"] == 4

    def test_parent_collapse_is_refused_not_summarised_as_the_subagent(self, sandbox) -> None:
        """agent_transcript_path == transcript_path must not price the PARENT's usage
        as the subagent's."""
        write_records(sandbox.parent_transcript, response_records(
            "msg_parent", "claude-opus-5-5", usage(inp=999999, out=1, read=0, write=0)))
        result = sandbox.run_hook(sandbox.payload(transcript=sandbox.parent_transcript))
        assert result.returncode == 0
        for row in sandbox.metrics_rows("subagent_usage"):
            assert row["status"] != "ok"
            assert "claude-opus-5-5" not in row.get("model_usage", {})


# --------------------------------------------------------------------------- #
# Capability: no transcript problem ever blocks the stop
# --------------------------------------------------------------------------- #

class TestHookNeverBlocksTheStop:

    def _assert_stop_survives(self, sandbox: Sandbox, result) -> None:
        assert result.returncode == 0, result.stderr
        assert result.stdout == ""
        usage_rows = sandbox.metrics_rows("subagent_usage")
        assert len(usage_rows) <= 1, usage_rows
        for row in usage_rows:
            assert row["status"] in ("no_transcript", "error"), row
            assert row["agent_id"] == AGENT_ID
        complete = sandbox.metrics_rows("subagent_complete")
        assert len(complete) == 1, f"subagent_complete must still be written: {complete}"
        assert complete[0]["agent_id"] == AGENT_ID

    def test_missing_transcript(self, sandbox) -> None:
        gone = sandbox.session_dir / "subagents" / f"agent-{AGENT_ID}.jsonl"
        assert not gone.exists()
        result = sandbox.run_hook(sandbox.payload(transcript=gone))
        self._assert_stop_survives(sandbox, result)

    def test_missing_transcript_and_no_path_in_envelope(self, sandbox) -> None:
        result = sandbox.run_hook(sandbox.payload(transcript=None))
        self._assert_stop_survives(sandbox, result)

    @pytest.mark.skipif(os.geteuid() == 0, reason="root ignores file modes")
    def test_unreadable_transcript(self, sandbox) -> None:
        transcript = _hook_transcript(sandbox)
        transcript.chmod(0o000)
        try:
            result = sandbox.run_hook(sandbox.payload(transcript=transcript))
        finally:
            transcript.chmod(0o600)
        self._assert_stop_survives(sandbox, result)

    def test_transcript_path_that_is_a_directory(self, sandbox) -> None:
        directory = sandbox.session_dir / "subagents" / f"agent-{AGENT_ID}.jsonl"
        directory.mkdir(parents=True)
        result = sandbox.run_hook(sandbox.payload(transcript=directory))
        self._assert_stop_survives(sandbox, result)

    def test_malformed_usage_record(self, sandbox) -> None:
        """A truncated JSON line plus an assistant record whose usage lacks required fields."""
        path = sandbox.session_dir / "subagents" / f"agent-{AGENT_ID}.jsonl"
        path.parent.mkdir(parents=True)
        path.write_text(
            '{"type": "assistant", "message": {"id": "m1", "model": "claude-opus-5-5", "usa\n'
            + json.dumps({"type": "assistant",
                          "message": {"id": "m2", "model": "claude-opus-5-5",
                                      "usage": {"output_tokens": 5}}}) + "\n")
        result = sandbox.run_hook(sandbox.payload(transcript=path))
        self._assert_stop_survives(sandbox, result)

    def test_binary_garbage_transcript(self, sandbox) -> None:
        path = sandbox.session_dir / "subagents" / f"agent-{AGENT_ID}.jsonl"
        path.parent.mkdir(parents=True)
        path.write_bytes(b"\x00\xff\xfe\x80not json at all\n\x01\x02")
        result = sandbox.run_hook(sandbox.payload(transcript=path))
        assert result.returncode == 0, result.stderr
        assert result.stdout == ""
        for row in sandbox.metrics_rows("subagent_usage"):
            assert row["status"] in ("no_transcript", "error", "ok")
            if row["status"] == "ok":
                assert row["responses"] == 0 and row["model_usage"] == {}
        assert len(sandbox.metrics_rows("subagent_complete")) == 1


# --------------------------------------------------------------------------- #
# Capability: the audit prices a deleted transcript from its summary
# --------------------------------------------------------------------------- #

def _summary_row(agent_id: str, dispatch_id: str, model_usage: dict, *,
                 role: str = "writ-explorer", status: str = "ok",
                 child_dispatches: dict | None = None,
                 parent_session: str = "sess-sum") -> dict:
    return {
        "event": "subagent_usage", "session": agent_id, "agent_id": agent_id,
        "parent_session": parent_session, "dispatch_id": dispatch_id, "role": role,
        "role_source": "sidecar", "status": status, "schema": 1,
        "responses": sum(m["responses"] for m in model_usage.values()),
        "records": sum(m["responses"] for m in model_usage.values()),
        "duplicates_collapsed": 0, "conflicts": 0, "model_usage": model_usage,
        "child_dispatches": child_dispatches or {},
        "first_ts": "2026-09-01T10:01:00Z", "last_ts": "2026-09-01T10:02:00Z",
    }


# plan fixture, literal arithmetic: 2,000x2 + 4,000x10 + 50,000x0.20 + 8,000x2.5 = 74,000 / 1e6
SONNET_AAA = {"claude-sonnet-5-5": {"responses": 1, "input": 2000, "output": 4000,
                                    "cache_read": 50000, "cache_write_5m": 8000,
                                    "cache_write_1h": 0}}
SONNET_AAA_USD = 0.074
HAIKU_CCC = {"claude-haiku-4-5-20251001": {"responses": 1, "input": 10000, "output": 1000,
                                           "cache_read": 0, "cache_write_5m": 0,
                                           "cache_write_1h": 0}}
HAIKU_CCC_USD = 0.015  # 10,000 + 5,000 = 15,000 / 1e6
MAIN_M1_USD = 0.132  # plan fixture: 132,000 / 1e6


def _main_records() -> list[dict]:
    """One opus-5-5 response ($0.132) that dispatches toolu_A -> agent aaa."""
    return (
        response_records("msg_m1", "claude-opus-5-5",
                         usage(inp=1000, out=2000, read=100000, write=10000, c5=4000, c1=6000),
                         n_records=2, tool_uses=[agent_tool_use("toolu_A", "writ:writ-explorer")],
                         ts="2026-09-01T10:00:00Z")
        + [tool_result_record("toolu_A", "aaa", ts="2026-09-01T10:02:00Z")]
    )


def _audit(main: Path, summaries: dict | None):
    ta = load_token_audit()
    return ta.scorecard(str(main), None, None, usage_summaries=summaries)


def _kinds(card: dict) -> list[str]:
    return [w.get("kind") for w in card.get("warnings", [])]


def _dispatch(card: dict, agent_id: str) -> dict:
    hits = [d for d in card["cost_by_dispatch"] if d["agent_id"] == agent_id]
    assert len(hits) == 1, f"expected one dispatch for {agent_id}: {card['cost_by_dispatch']}"
    return hits[0]


class TestAuditFallsBackToSummary:

    def test_deleted_transcript_is_priced_from_its_summary(self, tmp_path) -> None:
        main = write_session_tree(tmp_path, "sess-sum", _main_records())  # no subagents/
        summaries = {"aaa": _summary_row("aaa", "toolu_A", SONNET_AAA)}
        card = _audit(main, summaries)
        d = _dispatch(card, "aaa")
        assert d["status"] == "accounted"
        assert d["source"] == "summary"
        assert d["dispatch_id"] == "toolu_A"
        assert d["role"] == "writ-explorer"
        assert d["usd"] == pytest.approx(SONNET_AAA_USD)
        assert card["session"]["subagents_usd"] == pytest.approx(SONNET_AAA_USD)
        assert card["session"]["total_usd"] == pytest.approx(MAIN_M1_USD + SONNET_AAA_USD)
        assert card["session"]["partial"] is False

    def test_summary_dispatch_counts_in_coverage_by_source(self, tmp_path) -> None:
        main = write_session_tree(tmp_path, "sess-sum", _main_records())
        card = _audit(main, {"aaa": _summary_row("aaa", "toolu_A", SONNET_AAA)})
        cov = card["dispatch_coverage"]
        assert cov["summary"] == "1/1 dispatches accounted"
        assert cov["missing_transcript"] == 0
        assert cov["by_source"].get("summary") == 1
        assert cov["by_source"].get("transcript", 0) == 0

    def test_summary_is_priced_by_the_rate_card_with_model_normalization(
        self, tmp_path
    ) -> None:
        """The dated haiku id in a stored summary normalizes at audit time."""
        main = write_session_tree(tmp_path, "sess-sum", _main_records())
        card = _audit(main, {"aaa": _summary_row("aaa", "toolu_A", HAIKU_CCC)})
        assert _dispatch(card, "aaa")["usd"] == pytest.approx(HAIKU_CCC_USD)
        assert "claude-haiku-4-5" in card["cost_by_model"]

    def test_unknown_model_in_summary_is_unpriced_and_partial(self, tmp_path) -> None:
        mystery = {"claude-opus-5-6": dict(SONNET_AAA["claude-sonnet-5-5"])}
        main = write_session_tree(tmp_path, "sess-sum", _main_records())
        card = _audit(main, {"aaa": _summary_row("aaa", "toolu_A", mystery)})
        assert card["session"]["partial"] is True
        assert "claude-opus-5-6" in card["unpriced"]
        assert "unpriced_model" in _kinds(card)
        assert card["session"]["total_usd"] == pytest.approx(MAIN_M1_USD)

    def test_none_key_in_summary_uses_the_model_fallback(self, tmp_path) -> None:
        none_keyed = {"<none>": dict(SONNET_AAA["claude-sonnet-5-5"])}
        main = write_session_tree(tmp_path, "sess-sum", _main_records())
        ta = load_token_audit()
        card = ta.scorecard(str(main), None, "claude-sonnet-5-5",
                            usage_summaries={"aaa": _summary_row("aaa", "toolu_A", none_keyed)})
        assert _dispatch(card, "aaa")["usd"] == pytest.approx(SONNET_AAA_USD)

    def test_live_transcript_is_preferred_over_a_summary(self, tmp_path) -> None:
        live = response_records("msg_live", "claude-haiku-4-5-20251001",
                                usage(inp=10000, out=1000, read=0, write=0))
        main = write_session_tree(tmp_path, "sess-sum", _main_records(), {
            "aaa": {"records": live, "meta": {"agentType": "writ-explorer",
                                              "toolUseId": "toolu_A"}}})
        card = _audit(main, {"aaa": _summary_row("aaa", "toolu_A", SONNET_AAA)})
        d = _dispatch(card, "aaa")
        assert d["source"] == "transcript"
        assert d["usd"] == pytest.approx(HAIKU_CCC_USD)

    def test_no_summaries_means_no_fallback(self, tmp_path) -> None:
        main = write_session_tree(tmp_path, "sess-sum", _main_records())
        card = _audit(main, None)
        assert _dispatch(card, "aaa")["status"] == "missing_transcript"
        assert card["session"]["partial"] is True

    def test_no_transcript_summary_leaves_the_dispatch_missing(self, tmp_path) -> None:
        main = write_session_tree(tmp_path, "sess-sum", _main_records())
        row = _summary_row("aaa", "toolu_A", {}, status="no_transcript")
        card = _audit(main, {"aaa": row})
        d = _dispatch(card, "aaa")
        assert d["status"] == "missing_transcript"
        assert d["summary_status"] == "no_transcript"
        assert card["session"]["partial"] is True
        assert card["session"]["total_usd"] == pytest.approx(MAIN_M1_USD)

    def test_error_summary_leaves_the_dispatch_missing(self, tmp_path) -> None:
        main = write_session_tree(tmp_path, "sess-sum", _main_records())
        card = _audit(main, {"aaa": _summary_row("aaa", "toolu_A", {}, status="error")})
        d = _dispatch(card, "aaa")
        assert d["status"] == "missing_transcript"
        assert d["summary_status"] == "error"

    def test_summary_from_another_parent_session_matches_by_agent_id_with_a_warning(
        self, tmp_path
    ) -> None:
        main = write_session_tree(tmp_path, "sess-sum", _main_records())
        row = _summary_row("aaa", "toolu_A", SONNET_AAA, parent_session="some-other-session")
        card = _audit(main, {"aaa": row})
        assert _dispatch(card, "aaa")["source"] == "summary"
        assert "summary_parent_mismatch" in _kinds(card)


class TestSummaryChildDispatches:

    def test_nested_child_is_followed_through_child_dispatches_to_its_summary(
        self, tmp_path
    ) -> None:
        main = write_session_tree(tmp_path, "sess-sum", _main_records())
        summaries = {
            "aaa": _summary_row("aaa", "toolu_A", SONNET_AAA,
                                child_dispatches={"toolu_C": "ccc"}),
            "ccc": _summary_row("ccc", "toolu_C", HAIKU_CCC, role="writ-planner"),
        }
        card = _audit(main, summaries)
        parent, child = _dispatch(card, "aaa"), _dispatch(card, "ccc")
        assert child["status"] == "accounted" and child["source"] == "summary"
        assert child["dispatch_id"] == "toolu_C"
        assert child["parent_dispatch_id"] == "toolu_A"
        assert child["depth"] == parent["depth"] + 1
        assert card["dispatch_coverage"]["summary"] == "2/2 dispatches accounted"
        expected = MAIN_M1_USD + SONNET_AAA_USD + HAIKU_CCC_USD
        assert card["session"]["total_usd"] == pytest.approx(expected)
        assert sum(v["usd"] for v in card["cost_by_role"].values()) == pytest.approx(expected)
        assert sum(v["usd"] for v in card["cost_by_model"].values()) == pytest.approx(expected)

    def test_nested_child_with_a_live_transcript_is_found_from_a_summary_parent(
        self, tmp_path
    ) -> None:
        live_child = response_records("msg_c", "claude-haiku-4-5-20251001",
                                      usage(inp=10000, out=1000, read=0, write=0))
        main = write_session_tree(tmp_path, "sess-sum", _main_records(), {
            "ccc": {"records": live_child,
                    "meta": {"agentType": "writ-planner", "toolUseId": "toolu_C",
                             "spawnDepth": 2}}})
        summaries = {"aaa": _summary_row("aaa", "toolu_A", SONNET_AAA,
                                         child_dispatches={"toolu_C": "ccc"})}
        card = _audit(main, summaries)
        child = _dispatch(card, "ccc")
        assert child["source"] == "transcript"
        assert child["parent_dispatch_id"] == "toolu_A"
        assert card["orphans"] == [], "a linked child must not be reported as an orphan"
        assert card["session"]["total_usd"] == pytest.approx(
            MAIN_M1_USD + SONNET_AAA_USD + HAIKU_CCC_USD)

    def test_child_with_null_agent_id_is_missing_metadata(self, tmp_path) -> None:
        main = write_session_tree(tmp_path, "sess-sum", _main_records())
        summaries = {"aaa": _summary_row("aaa", "toolu_A", SONNET_AAA,
                                         child_dispatches={"toolu_C": None})}
        card = _audit(main, summaries)
        assert card["dispatch_coverage"]["missing_metadata"] == 1
        assert card["session"]["partial"] is True

    def test_child_with_no_transcript_and_no_summary_is_missing_transcript(
        self, tmp_path
    ) -> None:
        main = write_session_tree(tmp_path, "sess-sum", _main_records())
        summaries = {"aaa": _summary_row("aaa", "toolu_A", SONNET_AAA,
                                         child_dispatches={"toolu_C": "ccc"})}
        card = _audit(main, summaries)
        assert _dispatch(card, "ccc")["status"] == "missing_transcript"
        assert card["dispatch_coverage"]["summary"] == "1/2 dispatches accounted"
        assert card["session"]["partial"] is True

    def test_a_summary_cycle_terminates(self, tmp_path) -> None:
        main = write_session_tree(tmp_path, "sess-sum", _main_records())
        summaries = {
            "aaa": _summary_row("aaa", "toolu_A", SONNET_AAA,
                                child_dispatches={"toolu_C": "ccc"}),
            "ccc": _summary_row("ccc", "toolu_C", HAIKU_CCC,
                                child_dispatches={"toolu_A": "aaa"}),
        }
        card = _audit(main, summaries)
        assert card["session"]["total_usd"] == pytest.approx(
            MAIN_M1_USD + SONNET_AAA_USD + HAIKU_CCC_USD)


# --------------------------------------------------------------------------- #
# Capability: first row wins, conflicts warn
# --------------------------------------------------------------------------- #

def _write_metrics(log_root: Path, project: str, rows: list[dict]) -> Path:
    path = log_root / project / "metrics.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(r) + "\n" for r in rows))
    return path


@pytest.fixture()
def metrics_env(tmp_path, monkeypatch):
    log_root = tmp_path / "logs"
    monkeypatch.setenv("WRIT_LOG_ROOT", str(log_root))
    monkeypatch.delenv("WRIT_FRICTION_LOG", raising=False)
    monkeypatch.setenv("WRIT_LOG_PROJECT", PROJECT)
    return log_root


class TestFirstRowWins:

    def test_load_usage_summaries_keeps_only_subagent_usage_rows(self, metrics_env) -> None:
        _write_metrics(metrics_env, PROJECT, [
            {"event": "subagent_complete", "agent_id": "aaa"},
            _summary_row("aaa", "toolu_A", SONNET_AAA),
            {"event": "hook_execution", "agent_id": "bbb"},
        ])
        ta = load_token_audit()
        loaded = ta.load_usage_summaries("sess-sum", PROJECT)
        assert set(loaded) == {"aaa"}
        assert loaded["aaa"]["model_usage"] == SONNET_AAA

    def test_first_row_wins_when_two_rows_differ(self, metrics_env) -> None:
        second = {"claude-sonnet-5-5": {**SONNET_AAA["claude-sonnet-5-5"], "output": 999999}}
        _write_metrics(metrics_env, PROJECT, [
            _summary_row("aaa", "toolu_A", SONNET_AAA),
            _summary_row("aaa", "toolu_A", second),
        ])
        ta = load_token_audit()
        loaded = ta.load_usage_summaries("sess-sum", PROJECT)
        assert loaded["aaa"]["model_usage"] == SONNET_AAA

    def test_audit_prices_the_first_row_and_warns_summary_conflict(
        self, metrics_env, tmp_path
    ) -> None:
        second = {"claude-sonnet-5-5": {**SONNET_AAA["claude-sonnet-5-5"], "output": 999999}}
        _write_metrics(metrics_env, PROJECT, [
            _summary_row("aaa", "toolu_A", SONNET_AAA),
            _summary_row("aaa", "toolu_A", second),
        ])
        main = write_session_tree(tmp_path / "t", "sess-sum", _main_records())
        ta = load_token_audit()
        card = ta.scorecard(str(main), None, None,
                            usage_summaries=ta.load_usage_summaries("sess-sum", PROJECT))
        assert _dispatch(card, "aaa")["usd"] == pytest.approx(SONNET_AAA_USD)
        conflicts = [w for w in card["warnings"] if w.get("kind") == "summary_conflict"]
        assert len(conflicts) == 1
        assert conflicts[0].get("agent_id") == "aaa"

    def test_identical_duplicate_rows_do_not_warn(self, metrics_env, tmp_path) -> None:
        row = _summary_row("aaa", "toolu_A", SONNET_AAA)
        _write_metrics(metrics_env, PROJECT, [row, dict(row)])
        main = write_session_tree(tmp_path / "t", "sess-sum", _main_records())
        ta = load_token_audit()
        card = ta.scorecard(str(main), None, None,
                            usage_summaries=ta.load_usage_summaries("sess-sum", PROJECT))
        assert "summary_conflict" not in _kinds(card)
        assert _dispatch(card, "aaa")["usd"] == pytest.approx(SONNET_AAA_USD)

    def test_a_later_ok_row_does_not_replace_an_earlier_no_transcript_row(
        self, metrics_env, tmp_path
    ) -> None:
        """First row wins even when the first row is the worse one."""
        _write_metrics(metrics_env, PROJECT, [
            _summary_row("aaa", "toolu_A", {}, status="no_transcript"),
            _summary_row("aaa", "toolu_A", SONNET_AAA),
        ])
        main = write_session_tree(tmp_path / "t", "sess-sum", _main_records())
        ta = load_token_audit()
        card = ta.scorecard(str(main), None, None,
                            usage_summaries=ta.load_usage_summaries("sess-sum", PROJECT))
        assert _dispatch(card, "aaa")["status"] == "missing_transcript"

    def test_load_reads_rotated_archives_too(self, metrics_env) -> None:
        """read_streams unions the live file with archive generations."""
        import gzip
        arc = metrics_env / PROJECT / "archive"
        arc.mkdir(parents=True)
        with gzip.open(arc / "metrics-2026-08-01.jsonl.gz", "wt") as fh:
            fh.write(json.dumps(_summary_row("old", "toolu_O", SONNET_AAA)) + "\n")
        _write_metrics(metrics_env, PROJECT, [_summary_row("aaa", "toolu_A", SONNET_AAA)])
        ta = load_token_audit()
        assert set(ta.load_usage_summaries("sess-sum", PROJECT)) == {"old", "aaa"}

    def test_no_metrics_stream_yields_an_empty_mapping(self, metrics_env) -> None:
        ta = load_token_audit()
        assert ta.load_usage_summaries("sess-sum", PROJECT) == {}


# --------------------------------------------------------------------------- #
# Integration: what the real hook wrote is what the audit reads back
# --------------------------------------------------------------------------- #

class TestHookToAuditRoundTrip:

    def test_summary_written_by_the_real_hook_prices_the_deleted_transcript(
        self, sandbox, monkeypatch
    ) -> None:
        transcript = _hook_transcript(sandbox)
        result = sandbox.run_hook(sandbox.payload(transcript=transcript))
        assert result.returncode == 0, result.stderr
        # Claude Code deletes the subagent transcript when the session ends.
        transcript.unlink()

        monkeypatch.setenv("WRIT_LOG_ROOT", str(sandbox.log_root))
        monkeypatch.delenv("WRIT_FRICTION_LOG", raising=False)
        main = write_records(
            sandbox.root / "audit" / "sess-rt.jsonl",
            response_records("msg_m", "claude-opus-5-5",
                             usage(inp=1000, out=0, read=0, write=0),
                             tool_uses=[agent_tool_use(DISPATCH_ID, "writ:writ-explorer")])
            + [tool_result_record(DISPATCH_ID, AGENT_ID)])
        ta = load_token_audit()
        summaries = ta.load_usage_summaries("sess-rt", PROJECT)
        assert AGENT_ID in summaries
        card = ta.scorecard(str(main), None, None, usage_summaries=summaries)
        d = _dispatch(card, AGENT_ID)
        assert d["status"] == "accounted" and d["source"] == "summary"
        assert d["role"] == "writ-explorer"
        # opus-5-5: 1,500x4 + 3,000x20 + 300,000x0.20 + 4,000x5 + 6,000x8 = 194,000
        # sonnet-5-5: 300x2 + 50x10 = 1,100 ; dated haiku-4-5: 10,000x1 + 1,000x5 = 15,000
        assert card["session"]["subagents_usd"] == pytest.approx(
            (194000 + 1100 + 15000) / 1e6)
        assert card["session"]["main_usd"] == pytest.approx(1000 * 4 / 1e6)
        # the stored summary's own child (toolu_X -> zzz) has neither transcript nor summary
        assert _dispatch(card, "zzz")["status"] == "missing_transcript"
        assert card["session"]["partial"] is True


# --------------------------------------------------------------------------- #
# Review fixes: dispatch-id lookup never raises; unsupported summary schemas skip
# --------------------------------------------------------------------------- #

def _plain_subagent(tmp_path: Path, meta: dict | None) -> Path:
    return write_subagent(
        tmp_path / "proj" / PARENT_SESSION, AGENT_ID,
        response_records("msg_1", "claude-opus-5-5", usage(inp=1000, out=0, read=0, write=0)),
        meta=meta)


class TestUsageSummaryDispatchLookupNeverRaises:

    @pytest.fixture(autouse=True)
    def _projects_sandbox(self, tmp_path, monkeypatch):
        monkeypatch.setenv("WRIT_PROJECTS_DIR", str(tmp_path / "no-projects"))

    def test_read_meta_failure_yields_null_dispatch_id_and_ok_row(
        self, tmp_path, monkeypatch
    ) -> None:
        ta = load_token_audit()
        path = _plain_subagent(tmp_path, {"toolUseId": DISPATCH_ID})

        def boom(*_a, **_k):
            raise RuntimeError("sidecar exploded")
        monkeypatch.setattr(ta.token_tree, "read_meta", boom)
        row = ta.usage_summary_event(AGENT_ID, PARENT_SESSION, str(path), "writ-explorer",
                                     "sidecar")
        assert row["dispatch_id"] is None
        assert row["status"] == "ok"
        assert row["responses"] == 1

    def test_sidecar_lookup_failure_yields_null_dispatch_id_and_ok_row(
        self, tmp_path, monkeypatch
    ) -> None:
        import writ.session.subagent_role as sr
        ta = load_token_audit()
        path = _plain_subagent(tmp_path, None)   # no .meta.json: falls to sidecar_path

        def boom(*_a, **_k):
            raise PermissionError("projects dir unreadable")
        monkeypatch.setattr(sr, "sidecar_path", boom)
        row = ta.usage_summary_event(AGENT_ID, PARENT_SESSION, str(path), None, None)
        assert row["dispatch_id"] is None
        assert row["status"] == "ok"

    def test_lookup_failure_without_transcript_is_a_no_transcript_row(
        self, tmp_path, monkeypatch
    ) -> None:
        import writ.session.subagent_role as sr
        ta = load_token_audit()

        def boom(*_a, **_k):
            raise RuntimeError("x")
        monkeypatch.setattr(sr, "sidecar_path", boom)
        row = ta.usage_summary_event(AGENT_ID, PARENT_SESSION, None, None, None)
        assert row["dispatch_id"] is None
        assert row["status"] == "no_transcript"

    def test_meta_tool_use_id_still_resolves(self, tmp_path) -> None:
        ta = load_token_audit()
        path = _plain_subagent(tmp_path, {"toolUseId": DISPATCH_ID})
        row = ta.usage_summary_event(AGENT_ID, PARENT_SESSION, str(path), None, None)
        assert row["dispatch_id"] == DISPATCH_ID


class TestUnsupportedSummarySchema:

    def test_row_with_another_schema_is_skipped_with_a_warning(self, metrics_env) -> None:
        _write_metrics(metrics_env, PROJECT, [
            {**_summary_row("aaa", "toolu_A", SONNET_AAA), "schema": 2},
            _summary_row("bbb", "toolu_B", SONNET_AAA),
        ])
        loaded = load_token_audit().load_usage_summaries("sess-sum", PROJECT)
        assert set(loaded) == {"bbb"}
        assert loaded.warnings == [{"kind": "summary_schema_unsupported", "agent_id": "aaa",
                                    "schema": 2}]

    def test_row_without_a_schema_is_skipped(self, metrics_env) -> None:
        row = _summary_row("aaa", "toolu_A", SONNET_AAA)
        del row["schema"]
        _write_metrics(metrics_env, PROJECT, [row])
        loaded = load_token_audit().load_usage_summaries("sess-sum", PROJECT)
        assert loaded == {}
        assert loaded.warnings == [{"kind": "summary_schema_unsupported", "agent_id": "aaa",
                                    "schema": None}]

    def test_skipped_row_neither_wins_nor_conflicts(self, metrics_env) -> None:
        _write_metrics(metrics_env, PROJECT, [
            {**_summary_row("aaa", "toolu_A", HAIKU_CCC), "schema": 2},
            _summary_row("aaa", "toolu_A", SONNET_AAA),
        ])
        loaded = load_token_audit().load_usage_summaries("sess-sum", PROJECT)
        assert loaded["aaa"]["model_usage"] == SONNET_AAA
        assert loaded.conflicts == {}

    def test_audit_surfaces_the_warning_for_a_dispatched_agent_only(
        self, metrics_env, tmp_path
    ) -> None:
        _write_metrics(metrics_env, PROJECT, [
            {**_summary_row("aaa", "toolu_A", SONNET_AAA), "schema": 2},
            {**_summary_row("unrelated", "toolu_U", SONNET_AAA), "schema": 3},
        ])
        main = write_session_tree(tmp_path / "t", "sess-sum", _main_records())
        ta = load_token_audit()
        card = ta.scorecard(str(main), None, None,
                            usage_summaries=ta.load_usage_summaries("sess-sum", PROJECT))
        assert _dispatch(card, "aaa")["status"] == "missing_transcript"
        hits = [w for w in card["warnings"] if w.get("kind") == "summary_schema_unsupported"]
        assert hits == [{"kind": "summary_schema_unsupported", "agent_id": "aaa",
                         "schema": 2}]
