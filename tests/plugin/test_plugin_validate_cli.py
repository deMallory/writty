"""Tests for `claude plugin validate` CLI validation (Phase A + D).

Runs the official claude CLI validator against the repo and asserts a clean
exit with no warnings or errors. Both tests are skipped when the claude CLI
is not installed (CI environments without claude code installed).
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from tests.plugin.conftest import REPO_ROOT


@pytest.mark.skipif(
    shutil.which("claude") is None,
    reason="claude CLI not installed; cannot run plugin validate",
)
class TestPluginValidateCli:
    def test_plugin_validate_exit_code_zero(self) -> None:
        """claude plugin validate must exit 0 for the Writ repo."""
        result = subprocess.run(
            ["claude", "plugin", "validate", str(REPO_ROOT)],
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert result.returncode == 0, (
            f"claude plugin validate exited {result.returncode}.\n"
            f"stdout: {result.stdout}\nstderr: {result.stderr}"
        )

    def test_plugin_validate_no_warnings(self) -> None:
        """claude plugin validate stdout and stderr must not contain WARNING or ERROR."""
        result = subprocess.run(
            ["claude", "plugin", "validate", str(REPO_ROOT)],
            capture_output=True,
            text=True,
            timeout=30,
        )
        combined = result.stdout + result.stderr
        assert "WARNING" not in combined, (
            f"claude plugin validate produced warnings:\n{combined}"
        )
        assert "ERROR" not in combined, (
            f"claude plugin validate produced errors:\n{combined}"
        )
