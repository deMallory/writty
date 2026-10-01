"""A `--noconftest` run must not write to the operator's log root.

conftest.py's autouse fixture redirects WRIT_LOG_ROOT per test, but `--noconftest`
skips it, and the operator's shell exports the real root. On 2026-09-29 one such run
of tests/test_session_identity_no_fallback.py wrote 14 critical_error rows into
~/.cache/writ/logs. The redirect now also lives in a plugin loaded from pyproject
addopts, which `--noconftest` does not skip.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

PROBE = '''
import os
from pathlib import Path

from writ.shared.logging import emit


def test_emit_lands_under_a_throwaway_root():
    root = Path(os.environ["WRIT_LOG_ROOT"])
    assert root != Path(os.environ["OPERATOR_LOG_ROOT"])
    emit(None, "critical_error", "probe-session", None, component="probe")
    assert list(root.rglob("errors.jsonl")), "emit wrote nothing under the redirected root"
'''


def _run_noconftest(tmp_path: Path) -> tuple[subprocess.CompletedProcess, Path]:
    operator_root = tmp_path / "operator-logs"
    probe = tmp_path / "test_probe.py"
    probe.write_text(PROBE)
    env = {**os.environ, "WRIT_LOG_ROOT": str(operator_root), "OPERATOR_LOG_ROOT": str(operator_root)}
    # The outer conftest set WRIT_FRICTION_LOG; left in, emit() would write that one
    # file and never consult the log root this test is about.
    env.pop("WRIT_FRICTION_LOG", None)
    # cwd outside the repo, so only pyproject's pythonpath can make `tests` importable.
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", str(probe), "-c", str(REPO_ROOT / "pyproject.toml"),
         "--noconftest", "-p", "no:cacheprovider", "-q"],
        cwd=tmp_path, env=env, capture_output=True, text=True, timeout=120, check=False,
    )
    return proc, operator_root


def test_noconftest_run_writes_nothing_to_the_operator_log_root(tmp_path: Path) -> None:
    proc, operator_root = _run_noconftest(tmp_path)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert not list(operator_root.rglob("*.jsonl")), "a --noconftest run wrote to the operator's log root"
