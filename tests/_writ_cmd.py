"""Shared resolver for invoking the `writ` CLI from tests.

`writ` is not on PATH inside subprocess.run on machines where the venv is
not activated -- callers get `PermissionError: [Errno 13] Permission
denied: 'writ'`. This helper prefers the venv binary, falling back to
`python -m writ.cli` when the binary is unavailable (CI, alternate venv
location).

Usage:
    from tests._writ_cmd import WRIT_CMD_PREFIX
    subprocess.run([*WRIT_CMD_PREFIX, "import-markdown", "bible/"], ...)
"""

from __future__ import annotations

import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent

_VENV_WRIT = _REPO_ROOT / ".venv" / "bin" / "writ"
if _VENV_WRIT.exists():
    WRIT_CLI = str(_VENV_WRIT)
    WRIT_CMD_PREFIX: list[str] = [WRIT_CLI]
else:
    WRIT_CLI = sys.executable
    WRIT_CMD_PREFIX = [WRIT_CLI, "-m", "writ.cli"]
