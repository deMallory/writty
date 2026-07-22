"""Hermetic delegation tests: the three writers route through the P1 router,
and the analyzers/metrics readers union the split audit+friction+metrics streams.

RED PHASE: writ/shared/logging.py, the `--stream` flag on friction-append.py,
and the multi-stream reader wiring in writ/analysis/friction.py and
writ/session/metrics.py do not exist yet. Import/attribute/CLI-flag failures
here are the expected outcome.

Covers:
  - writ/session/friction.py::_log_friction_event delegates to emit(), keeps
    its (session_id, mode, event, **extra) signature.
  - writ/analysis/friction.py::log_friction_event delegates to emit() while
    still honoring an explicit log_path; resolve_log_path is retained.
  - bin/lib/friction-append.py --stream STREAM (default "friction"), routes
    through the router + durable fallback; positional and
    --stdin-json/--stdin-jsonl modes classify by `event` via STREAM_MAP.
  - writ/analysis/friction.py readers union split streams via read_streams.
  - writ/session/metrics.py::cmd_metrics reads the split streams.

Hermetic: WRIT_LOG_ROOT / WRIT_LOG_PROJECT / WRIT_FRICTION_LOG monkeypatched
per test to tmp_path. No live Neo4j, no daemon.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
FRICTION_APPEND = REPO / "bin" / "lib" / "friction-append.py"

# The import is wrapped so collection succeeds even when the module is
# entirely absent (a module-level ImportError would abort collection of this
# whole file AND any sibling file in the same pytest invocation, per pytest's
# "Interrupted: N errors during collection" behavior with no
# --continue-on-collection-errors flag). A missing module must still produce
# genuine per-test RED failures, not a suite-wide collection abort.
try:
    from writ.shared.logging import stream_path  # RED until writ/shared/logging.py exists
except ModuleNotFoundError as _import_error:

    def stream_path(*_args, **_kwargs):
        raise ModuleNotFoundError(
            "writ.shared.logging does not exist yet"
        ) from _import_error


def _read_jsonl(path: Path) -> list[dict]:
    if not path.is_file():
        return []
    return [json.loads(ln) for ln in path.read_text().splitlines() if ln.strip()]


@pytest.fixture(autouse=True)
def _hermetic_log_env(tmp_path, monkeypatch):
    monkeypatch.setenv("WRIT_LOG_ROOT", str(tmp_path / "logs"))
    monkeypatch.setenv("WRIT_LOG_PROJECT", "delegation-proj")
    monkeypatch.delenv("WRIT_FRICTION_LOG", raising=False)
    return tmp_path


# --- writ/session/friction.py::_log_friction_event delegation ---------------


def test_session_friction_log_friction_event_keeps_public_signature(tmp_path, monkeypatch):
    """(session_id, mode, event, **extra) must still be the call shape after
    the delegation to the router."""
    from writ.session.friction import _log_friction_event

    _log_friction_event("sid-1", "work", "phase_transition", to_phase="testing")
    rows = _read_jsonl(stream_path("delegation-proj", "audit"))
    assert len(rows) == 1
    assert rows[0]["event"] == "phase_transition"
    assert rows[0]["to_phase"] == "testing"
    assert rows[0]["session"] == "sid-1"
    assert rows[0]["mode"] == "work"


def test_session_friction_delegates_classification_to_stream_map(tmp_path, monkeypatch):
    """A metrics-classified event from the session writer lands in metrics.jsonl,
    not the legacy single file -- proof the delegation, not a bespoke path, is
    doing the routing."""
    from writ.session.friction import _log_friction_event

    _log_friction_event("sid-2", "work", "hook_execution", hook_name="x", duration_ms=5)
    assert _read_jsonl(stream_path("delegation-proj", "metrics")) != []
    assert _read_jsonl(stream_path("delegation-proj", "audit")) == []
    assert _read_jsonl(stream_path("delegation-proj", "friction")) == []


def test_session_friction_honors_writ_friction_log_backcompat(tmp_path, monkeypatch):
    single_log = tmp_path / "wf.log"
    monkeypatch.setenv("WRIT_FRICTION_LOG", str(single_log))
    from writ.session.friction import _log_friction_event

    _log_friction_event("sid-3", "work", "mode_change", to="work")
    assert _read_jsonl(single_log) != []


# --- writ/analysis/friction.py::log_friction_event delegation ---------------


def test_analysis_log_friction_event_delegates_when_no_log_path(tmp_path, monkeypatch):
    from writ.analysis.friction import log_friction_event

    log_friction_event("sid-4", "work", "quality_judgment", rubric="tdd", decision="pass")
    rows = _read_jsonl(stream_path("delegation-proj", "audit"))
    assert len(rows) == 1
    assert rows[0]["rubric"] == "tdd"
    assert rows[0]["decision"] == "pass"


def test_analysis_log_friction_event_honors_explicit_log_path_override(tmp_path):
    """An explicit log_path argument writes there directly, bypassing the
    router-resolved split-stream location (explicit beats implicit)."""
    from writ.analysis.friction import log_friction_event

    explicit = tmp_path / "explicit.log"
    log_friction_event("sid-5", "work", "quality_judgment", log_path=explicit, rubric="tdd")
    rows = _read_jsonl(explicit)
    assert len(rows) == 1
    assert rows[0]["rubric"] == "tdd"
    # And it must NOT also have gone to the router-resolved audit stream.
    assert _read_jsonl(stream_path("delegation-proj", "audit")) == []


def test_analysis_resolve_log_path_still_works_for_cli_compat(tmp_path):
    from writ.analysis.friction import resolve_log_path

    explicit = tmp_path / "cli-explicit.log"
    assert resolve_log_path(explicit) == explicit


def test_analysis_resolve_log_path_honors_writ_friction_log_env(tmp_path, monkeypatch):
    from writ.analysis.friction import resolve_log_path

    env_path = tmp_path / "env.log"
    monkeypatch.setenv("WRIT_FRICTION_LOG", str(env_path))
    assert resolve_log_path(None) == env_path


# --- bin/lib/friction-append.py --stream override ---------------------------


def test_friction_append_stream_flag_defaults_to_friction(tmp_path, monkeypatch):
    """No --stream given: an event absent from STREAM_MAP still lands in the
    friction stream by default."""
    monkeypatch.setenv("WRIT_LOG_ROOT", str(tmp_path))
    monkeypatch.setenv("WRIT_LOG_PROJECT", "cli-proj")
    env = {**__import__("os").environ, "WRIT_LOG_ROOT": str(tmp_path), "WRIT_LOG_PROJECT": "cli-proj"}
    env.pop("WRIT_FRICTION_LOG", None)
    res = subprocess.run(
        [sys.executable, str(FRICTION_APPEND), "sid-6", "work", "brand_new_unclassified_event"],
        capture_output=True, text=True, env=env,
    )
    assert res.returncode == 0, res.stderr
    rows = _read_jsonl(stream_path("cli-proj", "friction"))
    assert len(rows) == 1
    assert rows[0]["event"] == "brand_new_unclassified_event"


def test_friction_append_stream_flag_overrides_classification(tmp_path):
    """--stream STREAM forces the destination stream regardless of STREAM_MAP."""
    import os

    env = {**os.environ, "WRIT_LOG_ROOT": str(tmp_path / "logs"), "WRIT_LOG_PROJECT": "cli-proj2"}
    env.pop("WRIT_FRICTION_LOG", None)
    res = subprocess.run(
        [sys.executable, str(FRICTION_APPEND), "--stream", "audit",
         "sid-7", "work", "custom_forced_audit_event"],
        capture_output=True, text=True, env=env,
    )
    assert res.returncode == 0, res.stderr
    rows = _read_jsonl(stream_path("cli-proj2", "audit"))
    assert len(rows) == 1
    assert rows[0]["event"] == "custom_forced_audit_event"


def test_friction_append_positional_mode_classifies_by_event_field(tmp_path):
    import os

    env = {**os.environ, "WRIT_LOG_ROOT": str(tmp_path / "logs"), "WRIT_LOG_PROJECT": "cli-proj3"}
    env.pop("WRIT_FRICTION_LOG", None)
    res = subprocess.run(
        [sys.executable, str(FRICTION_APPEND), "sid-8", "work", "write_attempt",
         json.dumps({"file_path": "/a.py"})],
        capture_output=True, text=True, env=env,
    )
    assert res.returncode == 0, res.stderr
    # write_attempt is STREAM_MAP-classified as audit.
    rows = _read_jsonl(stream_path("cli-proj3", "audit"))
    assert len(rows) == 1
    assert rows[0]["file_path"] == "/a.py"


def test_friction_append_stdin_json_classifies_by_event_field(tmp_path):
    import os

    env = {**os.environ, "WRIT_LOG_ROOT": str(tmp_path / "logs"), "WRIT_LOG_PROJECT": "cli-proj4"}
    env.pop("WRIT_FRICTION_LOG", None)
    entry = {"session": "sid-9", "mode": "work", "event": "subagent_complete", "agent_type": "Explore"}
    res = subprocess.run(
        [sys.executable, str(FRICTION_APPEND), "--stdin-json"],
        input=json.dumps(entry), capture_output=True, text=True, env=env,
    )
    assert res.returncode == 0, res.stderr
    # subagent_complete -> metrics per STREAM_MAP.
    rows = _read_jsonl(stream_path("cli-proj4", "metrics"))
    assert len(rows) == 1
    assert rows[0]["agent_type"] == "Explore"


def test_friction_append_stdin_jsonl_classifies_each_entry_independently(tmp_path):
    import os

    env = {**os.environ, "WRIT_LOG_ROOT": str(tmp_path / "logs"), "WRIT_LOG_PROJECT": "cli-proj5"}
    env.pop("WRIT_FRICTION_LOG", None)
    batch = "\n".join([
        json.dumps({"session": "sid-10", "mode": "work", "event": "mode_change"}),
        json.dumps({"session": "sid-10", "mode": "work", "event": "hook_execution", "hook_name": "h"}),
    ])
    res = subprocess.run(
        [sys.executable, str(FRICTION_APPEND), "--stdin-jsonl"],
        input=batch, capture_output=True, text=True, env=env,
    )
    assert res.returncode == 0, res.stderr
    assert len(_read_jsonl(stream_path("cli-proj5", "audit"))) == 1
    assert len(_read_jsonl(stream_path("cli-proj5", "metrics"))) == 1


def test_friction_append_durable_fallback_moved_off_tmp(tmp_path):
    """The plan moves the durable fallback to ~/.claude/writ/logs/_fallback.jsonl
    (off /tmp). Read the module source to confirm the /tmp fallback constant is
    gone (this is a RED source-inspection test until the move happens)."""
    source = FRICTION_APPEND.read_text()
    assert "/tmp/writ-friction-fallback.log" not in source
    assert "_fallback.jsonl" in source


def test_friction_append_honors_writ_friction_log_backcompat_with_stream_flag(tmp_path):
    """Even with --stream given, WRIT_FRICTION_LOG set routes to the single
    file (back-compat takes priority over the split)."""
    import os

    single_log = tmp_path / "single.log"
    env = {**os.environ, "WRIT_FRICTION_LOG": str(single_log)}
    res = subprocess.run(
        [sys.executable, str(FRICTION_APPEND), "--stream", "metrics",
         "sid-11", "work", "hook_execution"],
        capture_output=True, text=True, env=env,
    )
    assert res.returncode == 0, res.stderr
    assert _read_jsonl(single_log) != []


# --- writ/analysis/friction.py multi-stream readers --------------------------


def test_load_events_unions_split_streams_for_a_project(tmp_path, monkeypatch):
    from writ.shared.logging import emit
    from writ.analysis.friction import load_events

    emit(None, "mode_change", "sid-12", "work")     # audit
    emit(None, "write_failure", "sid-12", "work")   # friction
    emit(None, "hook_execution", "sid-12", "work")  # metrics

    events = load_events(project="delegation-proj")
    assert {e["event"] for e in events} == {"mode_change", "write_failure", "hook_execution"}


def test_load_events_still_accepts_explicit_single_log_path(tmp_path):
    from writ.analysis.friction import load_events

    explicit = tmp_path / "explicit-single.log"
    explicit.write_text(json.dumps({"session": "s", "mode": "work", "event": "phase_advance"}) + "\n")
    events = load_events(explicit)
    assert len(events) == 1
    assert events[0]["event"] == "phase_advance"


def test_load_events_honors_writ_friction_log_over_split_streams(tmp_path, monkeypatch):
    from writ.shared.logging import emit
    from writ.analysis.friction import load_events

    single_log = tmp_path / "wf-single.log"
    monkeypatch.setenv("WRIT_FRICTION_LOG", str(single_log))
    emit(None, "mode_change", "sid-13", "work")
    events = load_events(project="delegation-proj")
    assert len(events) == 1
    assert events[0]["event"] == "mode_change"


# --- CLI default log resolution (audit item E) -------------------------------
# RED until `analyze-friction` and `audit-session` default --log to None. Today
# both declare typer.Option(Path("workflow-friction.log")), so `path` is never
# None and the stream branch in _read_raw_rows is unreachable from the CLI:
# `writ analyze-friction --json` reports the legacy file, frozen 2026-07-01.


def _invoke_cli(args: list[str]):
    """Run a writ.cli command in-process via Typer's CliRunner."""
    from typer.testing import CliRunner

    from writ.cli import app

    return CliRunner().invoke(app, args)


def test_analyze_friction_without_log_flag_reads_split_streams(tmp_path, monkeypatch):
    from writ.shared.logging import emit

    monkeypatch.chdir(tmp_path)
    emit(None, "gate_denial", "sid-cli-1", "work", rule_id="ENF-1")

    result = _invoke_cli(["analyze-friction", "--json"])
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["by_event"].get("gate_denial") == 1


def test_analyze_friction_does_not_read_cwd_workflow_friction_log(tmp_path, monkeypatch):
    """The legacy filename in cwd must no longer be the implicit default."""
    monkeypatch.chdir(tmp_path)
    legacy = tmp_path / "workflow-friction.log"
    legacy.write_text(json.dumps(
        {"ts": "2026-01-01T00:00:00Z", "session": "s", "mode": "work", "event": "stale_marker"}
    ) + "\n")

    result = _invoke_cli(["analyze-friction", "--json"])
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert "stale_marker" not in payload["by_event"]


def test_analyze_friction_still_honors_explicit_log_flag(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    explicit = tmp_path / "explicit.log"
    explicit.write_text(json.dumps(
        {"ts": "2026-01-01T00:00:00Z", "session": "s", "mode": "work", "event": "phase_advance"}
    ) + "\n")

    result = _invoke_cli(["analyze-friction", "--json", "--log", str(explicit)])
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["by_event"].get("phase_advance") == 1


def test_audit_session_without_log_flag_reads_split_streams(tmp_path, monkeypatch):
    from writ.shared.logging import emit

    monkeypatch.chdir(tmp_path)
    emit(None, "phase_advance", "sid-cli-2", "work",
         from_phase="planning", to_phase="testing", confirmation_source="explicit")

    result = _invoke_cli(["audit-session", "sid-cli-2", "--json"])
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["event_count"] == 1
    assert payload["event_counts"].get("phase_advance") == 1


def test_audit_session_still_honors_explicit_log_flag(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    explicit = tmp_path / "explicit-audit.log"
    explicit.write_text(json.dumps(
        {"ts": "2026-01-01T00:00:00Z", "session": "sid-cli-3", "mode": "work",
         "event": "gate_denial"}
    ) + "\n")

    result = _invoke_cli(["audit-session", "sid-cli-3", "--json", "--log", str(explicit)])
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["event_counts"].get("gate_denial") == 1


def test_cli_default_resolution_still_honors_writ_friction_log_env(tmp_path, monkeypatch):
    """Precedence is unchanged: explicit --log, then WRIT_FRICTION_LOG, then streams."""
    monkeypatch.chdir(tmp_path)
    env_log = tmp_path / "env.log"
    env_log.write_text(json.dumps(
        {"ts": "2026-01-01T00:00:00Z", "session": "s", "mode": "work", "event": "read_blocked"}
    ) + "\n")
    monkeypatch.setenv("WRIT_FRICTION_LOG", str(env_log))

    result = _invoke_cli(["analyze-friction", "--json"])
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["by_event"].get("read_blocked") == 1


def test_analyze_friction_sees_archived_generations_after_rotation(tmp_path, monkeypatch):
    """End-to-end of D1a + E: rotation must not empty out the CLI's view."""
    import gzip

    from writ.shared.logging import archive_dir

    monkeypatch.chdir(tmp_path)
    arc = archive_dir("delegation-proj")
    arc.mkdir(parents=True, exist_ok=True)
    with gzip.open(arc / "audit-2026-07-21.jsonl.gz", "wt", encoding="utf-8") as fh:
        fh.write(json.dumps(
            {"ts": "2026-07-21T01:00:00Z", "session": "s", "mode": "work",
             "event": "gate_denial"}
        ) + "\n")

    result = _invoke_cli(["analyze-friction", "--json"])
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["by_event"].get("gate_denial") == 1


def test_parse_log_unions_split_streams_into_typed_friction_events(tmp_path, monkeypatch):
    from writ.shared.logging import emit
    from writ.analysis.friction import parse_log

    emit(None, "gate_denial", "sid-14", "work", rule_id="ENF-1")   # audit
    emit(None, "repeated_denial", "sid-14", "work", rule_id="ENF-1")  # friction

    events = parse_log(project="delegation-proj")
    event_names = {e.event for e in events}
    assert event_names == {"gate_denial", "repeated_denial"}


# --- writ/session/metrics.py::cmd_metrics reads split streams ---------------


def test_cmd_metrics_reads_union_of_split_streams(tmp_path, monkeypatch, capsys):
    from writ.shared.logging import emit
    from writ.session.metrics import cmd_metrics

    emit(None, "gate_denial", "sid-15", "work", rule_id="ENF-1")
    emit(None, "phase_transition_time", "sid-15", "work", elapsed_seconds=12)
    emit(None, "hook_execution", "sid-15", "work", hook_name="x", duration_ms=3)

    cmd_metrics()  # no explicit log_path -> falls through to split-stream union
    out = capsys.readouterr().out
    report = json.loads(out)
    assert report["total_events"] == 3
    assert report["denial_metrics"]["total_denials"] == 1


def test_cmd_metrics_explicit_log_path_still_takes_priority(tmp_path, monkeypatch, capsys):
    """An explicit log_path argument must be read verbatim, ignoring both the
    router-resolved split streams AND any WRIT_FRICTION_LOG override -- proof
    that explicit beats implicit, not just that the call doesn't raise."""
    from writ.shared.logging import emit
    from writ.session.metrics import cmd_metrics

    # Populate the split streams AND a WRIT_FRICTION_LOG file with events that
    # must NOT influence the report when an explicit log_path is given.
    single_log = tmp_path / "wf-should-be-ignored.log"
    monkeypatch.setenv("WRIT_FRICTION_LOG", str(single_log))
    emit(None, "gate_denial", "sid-ignored-1", "work")
    emit(None, "gate_denial", "sid-ignored-2", "work")
    monkeypatch.delenv("WRIT_FRICTION_LOG", raising=False)

    explicit = tmp_path / "explicit-metrics.log"
    explicit.write_text(json.dumps({"session": "s", "mode": "work", "event": "gate_denial"}) + "\n")

    cmd_metrics(str(explicit))
    out = capsys.readouterr().out
    report = json.loads(out)
    assert report["total_events"] == 1
    assert report["denial_metrics"]["total_denials"] == 1


def test_cmd_metrics_honors_writ_friction_log_over_split_streams(tmp_path, monkeypatch, capsys):
    from writ.shared.logging import emit
    from writ.session.metrics import cmd_metrics

    single_log = tmp_path / "wf-metrics.log"
    monkeypatch.setenv("WRIT_FRICTION_LOG", str(single_log))
    emit(None, "gate_denial", "sid-16", "work")
    cmd_metrics()
    out = capsys.readouterr().out
    report = json.loads(out)
    assert report["total_events"] == 1
