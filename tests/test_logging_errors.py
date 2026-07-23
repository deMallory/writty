"""Hermetic unit tests for the `errors` stream and `emit_exception`.

RED PHASE: `emit_exception` and the "errors" stream do not exist yet. Every test
here imports the helper directly; until it is added these fail on ImportError /
AttributeError. That failure IS the expected outcome.

Pins the "## Capabilities" lines in plan.md covering the helper and the stream:
routing, payload shape, bounded traceback, never-raises, WRIT_FRICTION_LOG
collapse, caller context, and read/rotate participation.

Hermetic: WRIT_LOG_ROOT is monkeypatched to tmp_path in every test; no live
Neo4j, no daemon.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from writ.shared.logging import read_streams, stream_path

# RED until emit_exception exists. Guarded so a missing name produces genuine
# per-test failures rather than aborting collection of this file and its
# siblings (pytest has no --continue-on-collection-errors here).
try:
    from writ.shared.logging import emit_exception
except ImportError as _import_error:

    def emit_exception(*_args, **_kwargs):  # type: ignore[misc]
        raise ImportError(
            "writ.shared.logging.emit_exception does not exist yet"
        ) from _import_error


@pytest.fixture(autouse=True)
def _hermetic_log_env(tmp_path, monkeypatch):
    monkeypatch.setenv("WRIT_LOG_ROOT", str(tmp_path / "logs"))
    monkeypatch.setenv("WRIT_LOG_PROJECT", "errproj")
    monkeypatch.delenv("WRIT_FRICTION_LOG", raising=False)
    return tmp_path


def _errors_rows(project: str = "errproj") -> list[dict]:
    path = stream_path(project, "errors")
    if not path.is_file():
        return []
    return [json.loads(ln) for ln in path.read_text().splitlines() if ln.strip()]


def _boom(message: str = "disk gone") -> Exception:
    """Return a raised-and-caught exception so it carries a real traceback."""
    try:
        raise OSError(message)
    except OSError as exc:
        return exc


# --- routing + payload -------------------------------------------------------


def test_emit_exception_writes_one_row_to_the_errors_stream():
    emit_exception("session.cache.read", _boom(), "sid-e1", "work")
    rows = _errors_rows()
    assert len(rows) == 1


def test_emit_exception_row_carries_component_type_and_message():
    emit_exception("session.cache.read", _boom("disk gone"), "sid-e2", "work")
    row = _errors_rows()[0]
    assert row["component"] == "session.cache.read"
    assert row["exc_type"] == "OSError"
    assert "disk gone" in row["message"]


def test_emit_exception_row_carries_a_traceback():
    emit_exception("session.cache.read", _boom(), "sid-e3", "work")
    row = _errors_rows()[0]
    assert "Traceback" in row["traceback"] or "_boom" in row["traceback"]


def test_emit_exception_row_keeps_the_standard_base_schema():
    """ts/session/mode/event come from the shared base entry, like every stream."""
    emit_exception("session.cache.read", _boom(), "sid-e4", "work")
    row = _errors_rows()[0]
    assert row["session"] == "sid-e4"
    assert row["mode"] == "work"
    assert row["event"] == "exception"
    assert row["ts"]


def test_emit_exception_includes_caller_supplied_context():
    emit_exception("session.cache.read", _boom(), "sid-e5", "work",
                   session_file="/tmp/writ-session-x.json", attempt=2)
    row = _errors_rows()[0]
    assert row["session_file"] == "/tmp/writ-session-x.json"
    assert row["attempt"] == 2


# --- bounded traceback -------------------------------------------------------


def test_emit_exception_truncates_a_long_traceback():
    """An uncapped traceback is how this stream becomes the next unbounded log."""
    def deep(n: int):
        if n == 0:
            raise RuntimeError("x" * 20000)
        deep(n - 1)

    try:
        deep(40)
    except RuntimeError as exc:
        emit_exception("test.deep", exc, "sid-e6", "work")

    row = _errors_rows()[0]
    assert len(row["traceback"]) <= 2200, "traceback must be capped"


def test_emit_exception_truncation_keeps_the_innermost_frames():
    """Tail-biased: the innermost frames are the useful ones."""
    def deep(n: int):
        if n == 0:
            raise RuntimeError("INNERMOST-MARKER")
        deep(n - 1)

    try:
        deep(60)
    except RuntimeError as exc:
        emit_exception("test.deep", exc, "sid-e7", "work")

    row = _errors_rows()[0]
    assert "INNERMOST-MARKER" in row["traceback"]


# --- never raises ------------------------------------------------------------


def test_emit_exception_never_raises_when_log_root_is_unwritable(tmp_path, monkeypatch):
    unwritable = tmp_path / "nope"
    unwritable.write_text("i am a file, not a directory")
    monkeypatch.setenv("WRIT_LOG_ROOT", str(unwritable))
    emit_exception("session.cache.read", _boom(), "sid-e8", "work")  # must not raise


def test_emit_exception_never_raises_on_an_unserializable_context_value():
    emit_exception("test.ctx", _boom(), "sid-e9", "work", weird=object())  # must not raise


def test_emit_exception_never_raises_when_given_a_non_exception():
    emit_exception("test.bad", "not an exception", "sid-e10", "work")  # must not raise


def test_emit_exception_accepts_a_missing_session_and_mode():
    emit_exception("test.nosession", _boom())  # must not raise
    assert len(_errors_rows()) == 1


# --- back-compat + integration ----------------------------------------------


def test_emit_exception_collapses_to_writ_friction_log_when_set(tmp_path, monkeypatch):
    single = tmp_path / "wf-single.log"
    monkeypatch.setenv("WRIT_FRICTION_LOG", str(single))
    emit_exception("session.cache.read", _boom(), "sid-e11", "work")
    rows = [json.loads(ln) for ln in single.read_text().splitlines() if ln.strip()]
    assert len(rows) == 1
    assert rows[0]["component"] == "session.cache.read"


def test_errors_stream_is_readable_via_read_streams():
    emit_exception("session.cache.read", _boom(), "sid-e12", "work")
    events = read_streams("errproj", ["errors"])
    assert [e["event"] for e in events] == ["exception"]


def test_errors_stream_does_not_leak_into_the_other_streams():
    emit_exception("session.cache.read", _boom(), "sid-e13", "work")
    assert read_streams("errproj", ["audit", "friction", "metrics"]) == []


def test_emit_exception_sanitizes_newlines_in_the_message():
    """SEC-INJ-LOG-001: a forged newline must not fake a second log record."""
    try:
        raise ValueError("line one\nline two")
    except ValueError as exc:
        emit_exception("test.inj", exc, "sid-e14", "work")

    path = stream_path("errproj", "errors")
    assert len(path.read_text().strip().splitlines()) == 1
