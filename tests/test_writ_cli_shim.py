"""PSR-008 Finding 3: writ CLI shim must work without `cd` to skill dir.

Context: PSR-008 transcript showed the agent tripping over
`python3 -m writ.cli ...` because the writ module is only importable
from the skill's .venv. Self-corrected by switching to the qualified
`.venv/bin/python -m writ.cli` after a `ModuleNotFoundError`.

Fix contract: a `bin/writ` executable that wraps the qualified call,
runnable from any cwd. Optional install via PATH symlink; the script
itself is the SSOT.
"""

from __future__ import annotations

import os
import stat
import subprocess

import pytest
from pathlib import Path

SKILL_DIR = str(Path.home() / ".claude/skills/writ")
SHIM = f"{SKILL_DIR}/bin/writ"


class TestWritCliShim:
    """The bin/writ shim forwards all args to `.venv/bin/python -m
    writ.cli` and works from any cwd."""

    def test_shim_exists_and_is_executable(self) -> None:
        assert os.path.exists(SHIM), (
            "bin/writ does not exist -- the CLI shim is missing"
        )
        st = os.stat(SHIM)
        assert st.st_mode & stat.S_IXUSR, (
            "bin/writ is not executable; chmod +x bin/writ required"
        )

    def test_shim_runs_help_from_unrelated_cwd(self, tmp_path) -> None:
        """Running `bin/writ analyze-friction --help` from /tmp must
        succeed (no ModuleNotFoundError). This is the PSR-008 footgun
        directly: the shim resolves writ.cli regardless of cwd."""
        result = subprocess.run(
            [SHIM, "analyze-friction", "--help"],
            cwd=str(tmp_path),  # unrelated cwd
            capture_output=True,
            text=True,
            timeout=15,
        )
        assert result.returncode == 0, (
            f"shim failed from unrelated cwd: rc={result.returncode}\n"
            f"stdout={result.stdout[:500]}\n"
            f"stderr={result.stderr[:500]}"
        )
        # Sanity: the help output names the CLI.
        assert "analyze-friction" in result.stdout or "Usage" in result.stdout, (
            f"shim output doesn't look like writ CLI help:\n{result.stdout[:500]}"
        )

    def test_shim_propagates_exit_code(self, tmp_path) -> None:
        """An unknown subcommand should exit non-zero, and the shim
        should propagate that. (Sanity check that the shim isn't
        swallowing exit codes.)"""
        result = subprocess.run(
            [SHIM, "this-subcommand-does-not-exist"],
            cwd=str(tmp_path),
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert result.returncode != 0, (
            "shim returned 0 for an unknown subcommand; exit code is being swallowed"
        )
