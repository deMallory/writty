"""RED-phase test skeletons for the P2 logging-rotation cycle.

Pins the router additions to `writ/shared/logging.py` (`ROTATE_SIZE_BYTES`,
`archive_dir`, `archive_path`, and the source-side size-roll wired into
`emit`) plus the new backstop sweep `writ.session.log_rotation.rotate_logs`
(and its `RETENTION_DAYS` / `SCRATCH_MAX_AGE_DAYS` constants).

RED PHASE: none of `ROTATE_SIZE_BYTES`, `archive_dir`, `archive_path` exist
yet on `writ.shared.logging`, and `writ/session/log_rotation.py` does not
exist at all. Every test below is expected to fail on import/attribute
resolution or on the very first behavioral assertion -- that failure IS the
expected outcome per plan.md's RED phase.

Hermetic (TEST-ISOLATE-002 / SOLID-DIP-001):
  - WRIT_LOG_ROOT is monkeypatched to a `tmp_path` subdirectory in every test
    (conftest.py's autouse `_isolate_friction_log` already does this; tests
    below additionally set it explicitly so the file is self-contained).
  - `rotate_logs()` is always called with an injected `now` (a fixed
    `datetime`) and `scratch_dir` (a `tmp_path` subdirectory) -- the real
    `/tmp` and the real wall clock are never touched.
  - `ROTATE_SIZE_BYTES`-crossing tests in the sweep section use `os.truncate()`
    to create a sparse file of the exact real threshold size rather than
    writing ~50 MB of real bytes. Monkeypatching the constant is only used in
    the ROUTER section, where it is provably safe (same-module global lookup
    inside `writ.shared.logging.emit`); it is deliberately NOT used for the
    cross-module sweep tests, where the constant may be bound by-value into
    `writ.session.log_rotation`'s own namespace at import time.

Run ONLY this file (never bare pytest -- that wipes the shared graph):
  .venv/bin/python -m pytest tests/test_log_rotation.py -v
"""
from __future__ import annotations

import gzip
import os
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Imports under test, wrapped so a missing name/module produces a genuine
# per-test RED failure rather than aborting collection of this whole file
# (pytest's "Interrupted: N errors during collection" behavior on a bare
# module-level ImportError with no --continue-on-collection-errors).
# ---------------------------------------------------------------------------

# These four already exist (P1, committed) -- imported directly, no fallback.
from writ.shared.logging import emit, log_root, stream_path, resolve_project

try:
    from writ.shared.logging import ROTATE_SIZE_BYTES, archive_dir, archive_path
except ImportError as _router_p2_import_error:
    ROTATE_SIZE_BYTES = None

    def archive_dir(*_a, **_kw):  # type: ignore[no-redef]
        raise ImportError(
            "writ.shared.logging.archive_dir does not exist yet (P2 not implemented)"
        ) from _router_p2_import_error

    def archive_path(*_a, **_kw):  # type: ignore[no-redef]
        raise ImportError(
            "writ.shared.logging.archive_path does not exist yet (P2 not implemented)"
        ) from _router_p2_import_error

try:
    from writ.session.log_rotation import (
        rotate_logs,
        RETENTION_DAYS,
        SCRATCH_MAX_AGE_DAYS,
    )
except ModuleNotFoundError as _log_rotation_import_error:

    def rotate_logs(*_a, **_kw):  # type: ignore[no-redef]
        raise ModuleNotFoundError(
            "writ.session.log_rotation does not exist yet (P2 sweep not implemented)"
        ) from _log_rotation_import_error

    RETENTION_DAYS = {}
    SCRATCH_MAX_AGE_DAYS = None


def _read_jsonl(path: Path) -> list[dict]:
    import json

    if not path.is_file():
        return []
    return [json.loads(ln) for ln in path.read_text().splitlines() if ln.strip()]


def _zero_summary() -> dict:
    return {"rotated": 0, "gzipped": 0, "pruned": 0, "scratch_cleaned": 0}


@pytest.fixture(autouse=True)
def _hermetic_log_env(tmp_path, monkeypatch):
    """Every test gets its own log root and a clean WRIT_* env slate."""
    monkeypatch.setenv("WRIT_LOG_ROOT", str(tmp_path / "logs"))
    monkeypatch.delenv("WRIT_FRICTION_LOG", raising=False)
    monkeypatch.delenv("WRIT_LOG_PROJECT", raising=False)
    return tmp_path


# ===========================================================================
# Named constants (## Capabilities: "size threshold is a single named
# constant ... shared by the router and the sweep, and retention windows are
# named constants")
# ===========================================================================


def test_rotate_size_bytes_is_approximately_50mb():
    assert isinstance(ROTATE_SIZE_BYTES, int)
    assert 40_000_000 <= ROTATE_SIZE_BYTES <= 60_000_000, (
        f"ROTATE_SIZE_BYTES should be ~50 MB per plan.md; got {ROTATE_SIZE_BYTES!r}"
    )


def test_retention_days_constant_values():
    assert RETENTION_DAYS == {
        "audit": 365,
        "friction": 365,
        # errors matches audit, not metrics: a silent failure that corrupted state
        # months ago is exactly what an investigation needs to reach back for.
        "errors": 365,
        "metrics": 90,
        "debug": 14,
    }


def test_scratch_max_age_days_constant_value():
    assert SCRATCH_MAX_AGE_DAYS == 7


def test_rotate_size_bytes_is_shared_single_source_between_router_and_sweep():
    """DRY-CONFIG-001: the sweep imports the SAME constant the router uses,
    rather than redefining its own copy that could drift out of sync."""
    from writ.session import log_rotation as _lr
    from writ.shared import logging as _logging_mod

    assert _lr.ROTATE_SIZE_BYTES == _logging_mod.ROTATE_SIZE_BYTES


# ===========================================================================
# Router source-side roll (writ/shared/logging.py emit())
# ===========================================================================


def test_router_rolls_oversize_stream_before_appending_new_event(tmp_path, monkeypatch):
    monkeypatch.setenv("WRIT_LOG_PROJECT", "proj-roll")
    monkeypatch.setattr("writ.shared.logging.ROTATE_SIZE_BYTES", 50)

    target = stream_path("proj-roll", "audit")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text('{"event": "old_event"}\n' * 5)
    assert target.stat().st_size >= 50

    emit(None, "mode_change", "sid-roll", "work", marker="fresh")

    fresh_rows = _read_jsonl(target)
    assert len(fresh_rows) == 1, (
        f"the live file must hold ONLY the new event after a roll; got {fresh_rows!r}"
    )
    assert fresh_rows[0]["marker"] == "fresh"

    archived_files = list(archive_dir("proj-roll").glob("audit-*"))
    assert len(archived_files) == 1, (
        f"exactly one archived generation must exist after the roll; got {archived_files!r}"
    )
    assert "old_event" in archived_files[0].read_text()


def test_router_source_side_roll_is_fail_open_when_archive_dir_uncreatable(
    tmp_path, monkeypatch,
):
    """ERR-GRACEFUL-001: when the roll itself fails (here: the project dir is
    read-only so `archive/` can't be created and the rename can't happen),
    the append must still proceed and emit must not raise."""
    import stat

    monkeypatch.setenv("WRIT_LOG_PROJECT", "proj-failopen")
    monkeypatch.setattr("writ.shared.logging.ROTATE_SIZE_BYTES", 50)

    project_dir = log_root() / "proj-failopen"
    project_dir.mkdir(parents=True)
    target = project_dir / "friction.jsonl"
    target.write_text("x" * 100)

    project_dir.chmod(stat.S_IREAD | stat.S_IEXEC)  # read+execute only: no mkdir/rename
    try:
        emit(None, "write_failure", "sid-fo", "work", note="still-appended")  # must not raise
    finally:
        project_dir.chmod(stat.S_IRWXU)

    assert "still-appended" in target.read_text(), (
        "the event must still be appended even when the source-side roll fails"
    )


def test_router_size_check_never_reads_file_body(tmp_path, monkeypatch):
    """PERF-IO-001: the size decision is a stat, never a read of the body."""
    monkeypatch.setenv("WRIT_LOG_PROJECT", "proj-cheap")
    target = stream_path("proj-cheap", "metrics")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("y" * 10)  # well under the real ROTATE_SIZE_BYTES default

    read_calls: list[str] = []
    real_read_text = Path.read_text
    real_read_bytes = Path.read_bytes

    def _spy_read_text(self, *a, **kw):
        read_calls.append(str(self))
        return real_read_text(self, *a, **kw)

    def _spy_read_bytes(self, *a, **kw):
        read_calls.append(str(self))
        return real_read_bytes(self, *a, **kw)

    monkeypatch.setattr(Path, "read_text", _spy_read_text)
    monkeypatch.setattr(Path, "read_bytes", _spy_read_bytes)

    stat_calls: list[str] = []
    real_stat = os.stat

    def _spy_stat(path, *a, **kw):
        stat_calls.append(str(path))
        return real_stat(path, *a, **kw)

    monkeypatch.setattr(os, "stat", _spy_stat)

    emit(None, "hook_execution", "sid-cheap", "work", duration_ms=1)

    assert str(target) not in read_calls, (
        f"the size check must never read the file body; read_calls={read_calls!r}"
    )
    assert any(str(target) in c for c in stat_calls), (
        "the size decision must be made via a stat() call on the target file"
    )


def test_router_same_day_second_roll_does_not_clobber_first(tmp_path, monkeypatch):
    monkeypatch.setenv("WRIT_LOG_PROJECT", "proj-collide")
    monkeypatch.setattr("writ.shared.logging.ROTATE_SIZE_BYTES", 20)

    target = stream_path("proj-collide", "audit")
    target.parent.mkdir(parents=True, exist_ok=True)

    target.write_text('{"marker": "pre-roll-generation-A"}' + "x" * 20 + "\n")
    emit(None, "mode_change", "sid-1", "work", gen="after-first-roll")

    # Grow the fresh live file back above threshold to force a SECOND same-day roll.
    target.write_text(
        target.read_text() + '{"marker": "pre-roll-generation-B"}' + "x" * 20 + "\n"
    )
    emit(None, "mode_change", "sid-2", "work", gen="after-second-roll")

    archived = sorted(archive_dir("proj-collide").glob("audit-*"))
    assert len(archived) == 2, (
        f"two same-day rolls must land in two distinct, non-clobbering archive "
        f"files; got {archived!r}"
    )
    joined = "\n".join(f.read_text() for f in archived)
    assert "pre-roll-generation-A" in joined
    assert "pre-roll-generation-B" in joined


# ===========================================================================
# Archive path safety (SEC-INJ-PATH-001)
# ===========================================================================


def test_archive_dir_is_nested_under_log_root_and_project():
    p = archive_dir("proj-x")
    assert p == log_root() / "proj-x" / "archive"


def test_archive_path_is_nested_under_archive_dir():
    p = archive_path("proj-x", "audit", date(2025, 6, 1))
    assert p.parent == archive_dir("proj-x")


def test_archive_path_cannot_escape_log_root_for_a_hostile_project_name(monkeypatch):
    """Reuses the router's existing project sanitization (`resolve_project` /
    `_sanitize_segment`) -- a hostile derived name must not let the archive
    path escape the log root."""
    from writ.session.git_identity import NotInRepoError

    monkeypatch.delenv("WRIT_LOG_PROJECT", raising=False)
    monkeypatch.setattr(
        "writ.shared.logging.derive_project_identity",
        lambda cwd: ("/repo", None, "../../etc/passwd"),
    )
    project = resolve_project(cwd="/repo")
    p = archive_path(project, "audit", date(2025, 6, 1))
    assert p.is_relative_to(log_root()), (
        f"archive_path must never escape log_root() even for a hostile source "
        f"identity; got {p!r}"
    )


# ===========================================================================
# rotate_logs(): rotating live files (size OR age trigger)
# ===========================================================================


def test_rotate_logs_rotates_live_file_at_or_over_size_threshold(tmp_path):
    project = "proj-size"
    live = stream_path(project, "metrics")
    live.parent.mkdir(parents=True, exist_ok=True)
    live.write_bytes(b'{"event": "big"}\n')
    os.truncate(live, ROTATE_SIZE_BYTES + 1024)  # sparse file: reaches size, no real I/O
    assert live.stat().st_size >= ROTATE_SIZE_BYTES

    now = datetime(2025, 6, 15, 12, 0, tzinfo=timezone.utc)
    os.utime(live, (now.timestamp(), now.timestamp()))  # today: only the SIZE trigger fires
    scratch = tmp_path / "scratch"
    scratch.mkdir()

    summary = rotate_logs(now=now, scratch_dir=scratch)

    assert not live.exists(), "an at/over-threshold live file must be rotated out"
    rotated = list(archive_dir(project).glob("metrics-*"))
    assert len(rotated) == 1
    assert summary["rotated"] == 1


def test_rotate_logs_rotates_live_file_whose_mtime_predates_today_even_if_small(
    tmp_path,
):
    project = "proj-age"
    live = stream_path(project, "audit")
    live.parent.mkdir(parents=True, exist_ok=True)
    live.write_text('{"event": "yesterday"}\n')  # tiny, well under ROTATE_SIZE_BYTES

    yesterday = datetime(2025, 6, 14, 23, 0, tzinfo=timezone.utc)
    os.utime(live, (yesterday.timestamp(), yesterday.timestamp()))

    now = datetime(2025, 6, 15, 0, 5, tzinfo=timezone.utc)  # a new UTC day
    scratch = tmp_path / "scratch"
    scratch.mkdir()

    summary = rotate_logs(now=now, scratch_dir=scratch)

    assert not live.exists(), (
        "a live file whose mtime predates the current UTC day must be rotated "
        "at the daily boundary, even under the size trigger"
    )
    assert summary["rotated"] == 1
    rotated = list(archive_dir(project).glob("audit-*"))
    assert len(rotated) == 1


def test_rotate_logs_does_not_rotate_small_same_day_live_file(tmp_path):
    project = "proj-fresh"
    live = stream_path(project, "audit")
    live.parent.mkdir(parents=True, exist_ok=True)
    live.write_text('{"event": "today"}\n')

    now = datetime(2025, 6, 15, 12, 0, tzinfo=timezone.utc)
    os.utime(live, (now.timestamp(), now.timestamp()))
    scratch = tmp_path / "scratch"
    scratch.mkdir()

    summary = rotate_logs(now=now, scratch_dir=scratch)

    assert live.exists(), "a small, same-day live file must be left alone"
    assert summary == _zero_summary()


# ===========================================================================
# rotate_logs(): gzip compression of archive generations
# ===========================================================================


def test_rotate_logs_gzips_uncompressed_archive_generation_and_removes_original(
    tmp_path,
):
    project = "proj-gzip"
    uncompressed = archive_path(project, "friction", date(2025, 6, 1))
    uncompressed.parent.mkdir(parents=True, exist_ok=True)
    uncompressed.write_text('{"event": "old"}\n')

    now = datetime(2025, 6, 15, tzinfo=timezone.utc)
    scratch = tmp_path / "scratch"
    scratch.mkdir()

    summary = rotate_logs(now=now, scratch_dir=scratch)

    assert not uncompressed.exists(), "the uncompressed original must be removed after gzip"
    gz = uncompressed.with_suffix(uncompressed.suffix + ".gz")
    assert gz.exists(), f"a .gz generation must be created at {gz!r}"
    with gzip.open(gz, "rt") as fh:
        assert '"event": "old"' in fh.read()
    assert summary["gzipped"] == 1
    assert summary["rotated"] == 0


# ===========================================================================
# rotate_logs(): per-stream retention pruning
# ===========================================================================


@pytest.mark.parametrize("stream", ["audit", "friction", "metrics", "debug", "errors"])
def test_rotate_logs_prunes_past_retention_and_keeps_inside_window(
    tmp_path, stream,
):
    project = "proj-retain"
    now = datetime(2025, 6, 15, tzinfo=timezone.utc)
    window_days = RETENTION_DAYS[stream]

    inside_date = (now - timedelta(days=window_days - 1)).date()
    past_date = (now - timedelta(days=window_days + 1)).date()

    kept = archive_path(project, stream, inside_date)
    pruned = archive_path(project, stream, past_date)
    kept.parent.mkdir(parents=True, exist_ok=True)
    pruned.parent.mkdir(parents=True, exist_ok=True)

    kept_gz = kept.with_suffix(kept.suffix + ".gz")
    pruned_gz = pruned.with_suffix(pruned.suffix + ".gz")
    with gzip.open(kept_gz, "wt") as fh:
        fh.write('{"event": "kept"}\n')
    with gzip.open(pruned_gz, "wt") as fh:
        fh.write('{"event": "pruned"}\n')

    scratch = tmp_path / "scratch"
    scratch.mkdir()
    summary = rotate_logs(now=now, scratch_dir=scratch)

    assert kept_gz.exists(), (
        f"{stream} generation {window_days - 1}d old must be KEPT (inside the "
        f"{window_days}d window)"
    )
    assert not pruned_gz.exists(), (
        f"{stream} generation {window_days + 1}d old must be PRUNED (past the "
        f"{window_days}d window)"
    )
    assert summary["pruned"] == 1
    assert summary["rotated"] == 0
    assert summary["gzipped"] == 0


# ===========================================================================
# rotate_logs(): stale scratch cleanup
# ===========================================================================


def test_rotate_logs_cleans_stale_session_keyed_scratch_files(tmp_path):
    scratch = tmp_path / "scratch"
    scratch.mkdir()
    now = datetime(2025, 6, 15, tzinfo=timezone.utc)

    stale = scratch / "writ-precompact-sid-old.log"
    stale.write_text("stale")
    stale_ts = (now - timedelta(days=SCRATCH_MAX_AGE_DAYS + 1)).timestamp()
    os.utime(stale, (stale_ts, stale_ts))

    fresh = scratch / "writ-postcompact-sid-new.log"
    fresh.write_text("fresh")
    fresh_ts = (now - timedelta(hours=1)).timestamp()
    os.utime(fresh, (fresh_ts, fresh_ts))

    summary = rotate_logs(now=now, scratch_dir=scratch)

    assert not stale.exists(), (
        f"a scratch file older than SCRATCH_MAX_AGE_DAYS ({SCRATCH_MAX_AGE_DAYS}d) "
        "must be removed"
    )
    assert fresh.exists(), "a scratch file within the retention window must be kept"
    assert summary["scratch_cleaned"] == 1


def test_rotate_logs_cleans_stale_subagent_payload_cap_files(tmp_path):
    scratch = tmp_path / "scratch"
    scratch.mkdir()
    now = datetime(2025, 6, 15, tzinfo=timezone.utc)

    stale_cap = scratch / "writ-subagent-payloads.jsonl"
    stale_cap.write_text('{"a": 1}\n')
    stale_ts = (now - timedelta(days=SCRATCH_MAX_AGE_DAYS + 1)).timestamp()
    os.utime(stale_cap, (stale_ts, stale_ts))

    fresh_cap = scratch / "writ-subagent-stop-payloads.jsonl"
    fresh_cap.write_text('{"b": 2}\n')
    os.utime(fresh_cap, (now.timestamp(), now.timestamp()))

    summary = rotate_logs(now=now, scratch_dir=scratch)

    assert not stale_cap.exists()
    assert fresh_cap.exists()
    assert summary["scratch_cleaned"] == 1


# ===========================================================================
# rotate_logs(): idempotence, fail-soft, missing root, signature
# ===========================================================================


def test_rotate_logs_is_idempotent_on_immediate_second_run(tmp_path):
    project = "proj-idem"
    live = stream_path(project, "friction")
    live.parent.mkdir(parents=True, exist_ok=True)
    live.write_bytes(b'{"event": "big"}\n')
    os.truncate(live, ROTATE_SIZE_BYTES + 1024)
    now = datetime(2025, 6, 15, tzinfo=timezone.utc)
    os.utime(live, (now.timestamp(), now.timestamp()))

    scratch = tmp_path / "scratch"
    scratch.mkdir()
    stale_scratch = scratch / "writ-feedback-sid-old.log"
    stale_scratch.write_text("x")
    old_ts = (now - timedelta(days=SCRATCH_MAX_AGE_DAYS + 1)).timestamp()
    os.utime(stale_scratch, (old_ts, old_ts))

    first = rotate_logs(now=now, scratch_dir=scratch)
    assert first["rotated"] == 1
    assert first["gzipped"] == 1
    assert first["scratch_cleaned"] == 1

    second = rotate_logs(now=now, scratch_dir=scratch)
    assert second == _zero_summary(), (
        f"a second immediate run must find nothing left to do; got {second!r}"
    )


def test_rotate_logs_skips_unprocessable_directory_and_continues(tmp_path):
    """ERR-HANDLE-003: a directory sitting where a stream FILE is expected
    must not crash the sweep -- other, well-formed work still completes."""
    bad_project = "proj-bad-type"
    bad_dir_as_file = stream_path(bad_project, "friction")
    bad_dir_as_file.mkdir(parents=True)  # a directory, not a file

    good_project = "proj-good"
    good_live = stream_path(good_project, "audit")
    good_live.parent.mkdir(parents=True, exist_ok=True)
    good_live.write_bytes(b'{"event": "big"}\n')
    os.truncate(good_live, ROTATE_SIZE_BYTES + 1024)
    now = datetime(2025, 6, 15, tzinfo=timezone.utc)
    os.utime(good_live, (now.timestamp(), now.timestamp()))

    scratch = tmp_path / "scratch"
    scratch.mkdir()

    summary = rotate_logs(now=now, scratch_dir=scratch)  # must not raise

    assert summary["rotated"] >= 1, "the good project's oversize file must still be rotated"
    assert bad_dir_as_file.is_dir(), "the bad entry is skipped, not deleted or crashed on"


def test_rotate_logs_skips_malformed_archive_filename_during_prune(tmp_path):
    """A garbage-named entry in archive/ that doesn't parse into
    <stream>-<date> must be skipped without aborting the prune of a
    legitimate, far-past generation sitting alongside it."""
    project = "proj-malformed"
    arc = archive_dir(project)
    arc.mkdir(parents=True)
    garbage = arc / "not-a-recognizable-name.jsonl.gz"
    garbage.write_bytes(b"\x1f\x8bnotreallygzip")

    legit_past = archive_path(project, "metrics", date(2020, 1, 1))
    legit_past_gz = legit_past.with_suffix(legit_past.suffix + ".gz")
    with gzip.open(legit_past_gz, "wt") as fh:
        fh.write('{"event": "very old"}\n')

    now = datetime(2025, 6, 15, tzinfo=timezone.utc)
    scratch = tmp_path / "scratch"
    scratch.mkdir()

    summary = rotate_logs(now=now, scratch_dir=scratch)  # must not raise

    assert garbage.exists(), "an unparseable archive filename is skipped, not deleted"
    assert not legit_past_gz.exists(), (
        "a legit far-past generation is still pruned despite the sibling garbage file"
    )
    assert summary["pruned"] == 1


def test_rotate_logs_returns_all_zero_when_log_root_missing(tmp_path, monkeypatch):
    monkeypatch.setenv("WRIT_LOG_ROOT", str(tmp_path / "does-not-exist"))
    scratch = tmp_path / "scratch"
    scratch.mkdir()

    summary = rotate_logs(now=datetime(2025, 6, 15, tzinfo=timezone.utc), scratch_dir=scratch)

    assert summary == _zero_summary()


def test_rotate_logs_returns_dict_with_exact_expected_keys(tmp_path):
    scratch = tmp_path / "scratch"
    scratch.mkdir()
    summary = rotate_logs(now=datetime(2025, 6, 15, tzinfo=timezone.utc), scratch_dir=scratch)
    assert set(summary.keys()) == {"rotated", "gzipped", "pruned", "scratch_cleaned"}
    assert all(isinstance(v, int) for v in summary.values())


def test_rotate_logs_signature_accepts_now_and_scratch_dir_as_optional_kwargs():
    """Confirms the injected-clock/scratch-dir contract WITHOUT ever invoking
    the real default `/tmp` scratch dir -- calling rotate_logs() with no args
    at all would touch the live filesystem outside this test's tmp_path, which
    would violate the hermetic requirement, so this is a signature-only check."""
    import inspect

    sig = inspect.signature(rotate_logs)
    params = sig.parameters
    assert "now" in params, "rotate_logs must accept an injected `now`"
    assert "scratch_dir" in params, "rotate_logs must accept an injected `scratch_dir`"
    assert params["now"].default is None
    assert params["scratch_dir"].default is None


# ===========================================================================
# EXACT boundary conditions (the comparison-operator edges the window+/-1
# tests above skip over: `>` for retention, `>=` for size)
# ===========================================================================


@pytest.mark.parametrize("stream", ["audit", "friction", "metrics", "debug", "errors"])
def test_rotate_logs_keeps_archive_exactly_at_retention_window_boundary(
    tmp_path, stream,
):
    """A generation whose age equals `window_days` EXACTLY must be KEPT: the
    prune uses a strict `>` (only strictly-older-than-window is deleted). This
    pins the boundary that the window-1 / window+1 cases straddle but never hit."""
    project = "proj-retain-exact"
    now = datetime(2025, 6, 15, tzinfo=timezone.utc)
    window_days = RETENTION_DAYS[stream]
    exact_date = (now - timedelta(days=window_days)).date()

    gen = archive_path(project, stream, exact_date)
    gen.parent.mkdir(parents=True, exist_ok=True)
    gz = gen.with_suffix(gen.suffix + ".gz")
    with gzip.open(gz, "wt") as fh:
        fh.write('{"event": "exactly-at-window"}\n')

    scratch = tmp_path / "scratch"
    scratch.mkdir()
    summary = rotate_logs(now=now, scratch_dir=scratch)

    assert gz.exists(), (
        f"a {stream} generation exactly {window_days}d old must be KEPT "
        f"(retention uses strict '>' so age == window is inside the window)"
    )
    assert summary["pruned"] == 0


def test_rotate_logs_rotates_live_file_exactly_at_size_threshold(tmp_path):
    """A live file whose size EXACTLY equals ROTATE_SIZE_BYTES must roll: the
    size trigger is `>=`. The existing test only exercises threshold+1024."""
    project = "proj-size-exact"
    live = stream_path(project, "metrics")
    live.parent.mkdir(parents=True, exist_ok=True)
    live.write_bytes(b'{"event": "at-threshold"}\n')
    os.truncate(live, ROTATE_SIZE_BYTES)  # sparse file at EXACTLY the threshold
    assert live.stat().st_size == ROTATE_SIZE_BYTES

    now = datetime(2025, 6, 15, 12, 0, tzinfo=timezone.utc)
    os.utime(live, (now.timestamp(), now.timestamp()))  # same UTC day: only size can fire
    scratch = tmp_path / "scratch"
    scratch.mkdir()

    summary = rotate_logs(now=now, scratch_dir=scratch)

    assert not live.exists(), (
        "a live file exactly at ROTATE_SIZE_BYTES must roll (size trigger is '>=')"
    )
    assert summary["rotated"] == 1
    rotated = list(archive_dir(project).glob("metrics-*"))
    assert len(rotated) == 1


def test_emit_does_not_roll_writ_friction_log_even_when_oversize(tmp_path, monkeypatch):
    """WRIT_FRICTION_LOG back-compat: with a single-file override set, emit()
    appends to that one file and returns BEFORE `_roll_if_oversize`, so a
    single-log operator's file is never rotated out from under them even when it
    is over the size threshold."""
    friction_file = tmp_path / "single-stream.jsonl"
    monkeypatch.setenv("WRIT_FRICTION_LOG", str(friction_file))
    monkeypatch.setattr("writ.shared.logging.ROTATE_SIZE_BYTES", 10)

    friction_file.write_text("x" * 100 + "\n")  # already well over the patched threshold
    assert friction_file.stat().st_size > 10

    emit(None, "mode_change", "sid-fl", "work", marker="appended-not-rolled")

    text = friction_file.read_text()
    assert "x" * 100 in text, (
        "the single WRIT_FRICTION_LOG file must NOT be rotated away by emit()"
    )
    assert "appended-not-rolled" in text, (
        "the new event must be appended to the same single-log file"
    )
    assert not (tmp_path / "archive").exists(), (
        "no archive generation is created for the single-log override path"
    )


# ===========================================================================
# CRITICAL regression: a project whose resolved scope is literally `archive`
# (or ends in `/archive`) must NOT have its LIVE stream files treated as an
# archive folder and gzipped/unlinked. Classification is by filename, not by
# the parent directory's basename.
# ===========================================================================


def test_rotate_logs_does_not_destroy_live_streams_for_project_named_archive(
    tmp_path, monkeypatch,
):
    monkeypatch.setenv("WRIT_LOG_PROJECT", "archive")
    now = datetime(2025, 6, 15, 12, 0, tzinfo=timezone.utc)
    scratch = tmp_path / "scratch"
    scratch.mkdir()

    # Two tiny same-day events land in the LIVE audit stream of a project whose
    # scope is literally `archive`: <root>/archive/audit.jsonl (NOT an archive folder).
    emit(None, "mode_change", "sid-a", "work", n=1)
    emit(None, "mode_change", "sid-b", "work", n=2)
    live = stream_path("archive", "audit")
    assert live.is_file(), "the emitted events must land in <root>/archive/audit.jsonl"
    os.utime(live, (now.timestamp(), now.timestamp()))  # small AND same-day

    summary = rotate_logs(now=now, scratch_dir=scratch)

    assert live.is_file(), (
        "the live stream of a project named 'archive' must SURVIVE rotate_logs() "
        "(the P2 data-loss regression gzipped+unlinked it)"
    )
    assert len(_read_jsonl(live)) == 2, "no events may be lost"
    assert not live.with_suffix(live.suffix + ".gz").exists(), (
        "the live file must not be gzipped in place"
    )
    assert summary["gzipped"] == 0
    assert summary["rotated"] == 0

    # A genuinely oversized live file in that SAME project is still rotated
    # correctly into its sibling archive/ dir and then gzipped.
    os.truncate(live, ROTATE_SIZE_BYTES + 1024)
    os.utime(live, (now.timestamp(), now.timestamp()))

    summary2 = rotate_logs(now=now, scratch_dir=scratch)

    assert not live.exists(), "an oversized live file must still be rotated"
    assert summary2["rotated"] == 1
    sibling_archive = log_root() / "archive" / "archive"
    gz = list(sibling_archive.glob("audit-*.jsonl.gz"))
    assert len(gz) == 1, (
        f"the oversized live file must land gzipped in the sibling archive/ dir; "
        f"got {list(sibling_archive.glob('*')) if sibling_archive.exists() else 'no archive dir'}"
    )
    assert summary2["gzipped"] == 1


def test_rotate_logs_does_not_destroy_live_streams_for_nested_org_archive_project(
    tmp_path, monkeypatch,
):
    monkeypatch.setenv("WRIT_LOG_PROJECT", "github.com/org/archive")
    project = "github.com/org/archive"
    now = datetime(2025, 6, 15, 12, 0, tzinfo=timezone.utc)
    scratch = tmp_path / "scratch"
    scratch.mkdir()

    emit(None, "mode_change", "sid-n1", "work", n=1)
    emit(None, "mode_change", "sid-n2", "work", n=2)
    live = stream_path(project, "audit")
    assert live.is_file(), (
        "the emitted events must land in <root>/github.com/org/archive/audit.jsonl"
    )
    os.utime(live, (now.timestamp(), now.timestamp()))

    summary = rotate_logs(now=now, scratch_dir=scratch)

    assert live.is_file(), (
        "a nested project ending in '/archive' must not have its live stream "
        "gzipped/unlinked by rotate_logs()"
    )
    assert len(_read_jsonl(live)) == 2
    assert not live.with_suffix(live.suffix + ".gz").exists()
    assert summary["gzipped"] == 0
    assert summary["rotated"] == 0

    # The genuinely-oversized case still rotates into the deepest sibling archive/.
    os.truncate(live, ROTATE_SIZE_BYTES + 1024)
    os.utime(live, (now.timestamp(), now.timestamp()))

    summary2 = rotate_logs(now=now, scratch_dir=scratch)

    assert not live.exists(), "an oversized nested live file must still be rotated"
    assert summary2["rotated"] == 1
    sibling_archive = log_root() / project / "archive"
    gz = list(sibling_archive.glob("audit-*.jsonl.gz"))
    assert len(gz) == 1
    assert summary2["gzipped"] == 1
