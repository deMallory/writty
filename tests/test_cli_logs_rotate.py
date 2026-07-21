"""RED-phase test skeleton for `writ logs rotate` (writ/cli.py).

Pins the ## Capabilities line: "`writ logs rotate` invokes `rotate_logs()`,
prints a one-line rotated/gzipped/pruned/scratch_cleaned summary, and exits
0", plus the `logs` Typer sub-app registration itself (mirrors the existing
`git-hooks` / `pr` sub-app pattern in writ/cli.py).

RED PHASE: neither the `logs` Typer sub-app nor `writ.session.log_rotation`
exist yet. `runner.invoke(app, ["logs", "rotate"])` is expected to fail with
a Click "No such command" usage error (non-zero exit) until both land.

Per plan.md's ## Analysis, the `rotate` command imports `rotate_logs` LAZILY
inside the command body (the file's existing deferred-import convention --
see e.g. `git_hooks_install`, `harvest_cmd`). That means the name looked up
at call time lives in `writ.session.log_rotation`'s own namespace, not a copy
re-bound into `writ.cli` at import time -- so the mock-based tests below
patch `writ.session.log_rotation.rotate_logs`, not `writ.cli.rotate_logs`.

Run ONLY this file (never bare pytest -- that wipes the shared graph):
  .venv/bin/python -m pytest tests/test_cli_logs_rotate.py -v
"""
from __future__ import annotations

import re
from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from writ.cli import app

runner = CliRunner()

_SUMMARY_RE = re.compile(r"rotated=\d+\s+gzipped=\d+\s+pruned=\d+\s+scratch_cleaned=\d+")


def _registered_subapp_names() -> list[str]:
    return [grp.name for grp in getattr(app, "registered_groups", [])]


# ===========================================================================
# `logs` sub-app registration
# ===========================================================================


class TestLogsSubAppRegistered:
    def test_logs_subapp_is_registered_on_the_typer_app(self) -> None:
        names = _registered_subapp_names()
        assert "logs" in names, f"'logs' sub-app not registered: {names}"

    def test_writ_help_lists_logs_subcommand(self) -> None:
        result = runner.invoke(app, ["--help"])
        assert result.exit_code == 0
        assert "logs" in result.output, (
            f"'logs' must be listed in top-level --help output; got: {result.output!r}"
        )

    def test_logs_rotate_help_exits_zero_and_mentions_rotate(self) -> None:
        result = runner.invoke(app, ["logs", "rotate", "--help"])
        assert result.exit_code == 0, (
            f"'writ logs rotate --help' must exit 0; got {result.exit_code}. "
            f"Output: {result.output!r}"
        )
        assert "rotate" in result.output.lower()


# ===========================================================================
# `writ logs rotate` invokes rotate_logs() and formats its return value
# (mocked at the deferred-import source per plan.md's stated convention)
# ===========================================================================


class TestLogsRotateInvokesSweepAndFormatsSummary:
    def test_rotate_command_calls_rotate_logs_exactly_once(self) -> None:
        fake_summary = {"rotated": 3, "gzipped": 2, "pruned": 1, "scratch_cleaned": 4}
        with patch(
            "writ.session.log_rotation.rotate_logs", return_value=fake_summary
        ) as mock_rotate:
            result = runner.invoke(app, ["logs", "rotate"])

        assert mock_rotate.call_count == 1, (
            f"'writ logs rotate' must call rotate_logs() exactly once; "
            f"got {mock_rotate.call_count} calls. Output: {result.output!r}"
        )

    def test_rotate_command_exits_zero_on_a_successful_sweep(self) -> None:
        fake_summary = {"rotated": 0, "gzipped": 0, "pruned": 0, "scratch_cleaned": 0}
        with patch("writ.session.log_rotation.rotate_logs", return_value=fake_summary):
            result = runner.invoke(app, ["logs", "rotate"])

        assert result.exit_code == 0, (
            f"exit code must be 0 on a successful sweep; got {result.exit_code}. "
            f"Output: {result.output!r}"
        )

    def test_rotate_command_prints_exact_counts_from_rotate_logs_return_value(
        self,
    ) -> None:
        fake_summary = {"rotated": 3, "gzipped": 2, "pruned": 1, "scratch_cleaned": 4}
        with patch("writ.session.log_rotation.rotate_logs", return_value=fake_summary):
            result = runner.invoke(app, ["logs", "rotate"])

        assert "rotated=3" in result.output, result.output
        assert "gzipped=2" in result.output, result.output
        assert "pruned=1" in result.output, result.output
        assert "scratch_cleaned=4" in result.output, result.output

    def test_rotate_command_summary_matches_expected_one_line_format(self) -> None:
        fake_summary = {"rotated": 0, "gzipped": 0, "pruned": 0, "scratch_cleaned": 0}
        with patch("writ.session.log_rotation.rotate_logs", return_value=fake_summary):
            result = runner.invoke(app, ["logs", "rotate"])

        assert _SUMMARY_RE.search(result.output), (
            f"expected a 'rotated=N gzipped=N pruned=N scratch_cleaned=N' "
            f"summary line; got: {result.output!r}"
        )

    def test_rotate_command_takes_no_positional_arguments(self) -> None:
        """The command per plan.md is a bare `writ logs rotate` -- an
        unexpected positional argument must be rejected by Click/Typer, not
        silently ignored."""
        fake_summary = {"rotated": 0, "gzipped": 0, "pruned": 0, "scratch_cleaned": 0}
        with patch("writ.session.log_rotation.rotate_logs", return_value=fake_summary):
            result = runner.invoke(app, ["logs", "rotate", "unexpected-arg"])

        assert result.exit_code != 0, (
            f"an unexpected positional argument must be rejected; "
            f"got exit_code=0, output={result.output!r}"
        )


# ===========================================================================
# End-to-end smoke test against a real (empty) hermetic log root -- no
# mocking of rotate_logs itself, so this also exercises the CLI-to-sweep
# wiring for the trivial all-zero case (avoids any assumption about how
# ROTATE_SIZE_BYTES is threaded between writ.shared.logging and
# writ.session.log_rotation, which is pinned precisely in
# tests/test_log_rotation.py instead).
# ===========================================================================


class TestLogsRotateEndToEndSmoke:
    def test_rotate_against_empty_log_root_exits_zero_with_all_zero_summary(
        self, tmp_path, monkeypatch,
    ) -> None:
        monkeypatch.setenv("WRIT_LOG_ROOT", str(tmp_path / "logs"))
        result = runner.invoke(app, ["logs", "rotate"])

        assert result.exit_code == 0, (
            f"'writ logs rotate' must exit 0 against an empty/missing log root; "
            f"got {result.exit_code}. Output: {result.output!r}"
        )
        assert "rotated=0" in result.output, result.output
        assert "gzipped=0" in result.output, result.output
        assert "pruned=0" in result.output, result.output
        assert "scratch_cleaned=0" in result.output, result.output
