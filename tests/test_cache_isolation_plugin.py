"""A pytest run must not use the operator's session cache folder or daemon socket.

conftest.py used `setdefault` for WRIT_CACHE_DIR, so a run launched with the variable
already set kept it. Claude Code pins it to ~/.cache/writ/session, and on 2026-10-03 that
folder held 516 files the suite had left there. The Python hook client also fell back to
~/.cache/writ/run/writ.sock, the live daemon, which wrote test sessions into the same
folder. Both redirects now live in the plugin loaded from pyproject addopts, which runs
before conftest and under `--noconftest` too.
"""

from __future__ import annotations

import os
import shutil
import socket
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

from tests.fixtures.net import free_port

REPO_ROOT = Path(__file__).resolve().parent.parent

PROBE = '''
import os
from pathlib import Path

from writ.session.cache import _cache_dir, _default_cache, _write_cache


def test_session_cache_lands_outside_the_operator_folder():
    operator = Path(os.environ["OPERATOR_CACHE_DIR"])
    assert Path(_cache_dir()) != operator
    _write_cache("probe-session", _default_cache())
    assert (Path(_cache_dir()) / "writ-session-probe-session.json").is_file()
'''


@pytest.mark.parametrize("extra", [[], ["--noconftest"]], ids=["plain", "noconftest"])
def test_run_writes_nothing_to_the_operator_cache_folder(tmp_path: Path, extra: list[str]) -> None:
    operator = tmp_path / "operator-cache"
    operator.mkdir()
    probe = tmp_path / "test_probe.py"
    probe.write_text(PROBE)
    env = {**os.environ, "WRIT_CACHE_DIR": str(operator), "OPERATOR_CACHE_DIR": str(operator)}
    # cwd outside the repo, so only pyproject's pythonpath can make `tests` importable.
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", str(probe), "-c", str(REPO_ROOT / "pyproject.toml"),
         *extra, "-p", "no:cacheprovider", "-q"],
        cwd=tmp_path, env=env, capture_output=True, text=True, timeout=120, check=False,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert not list(operator.iterdir()), "a pytest run wrote into the operator's cache folder"


SOCKET_PROBE = '''
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(os.environ["REPO_ROOT"]) / "bin" / "lib"))
import writ_daemon_client


def test_hook_client_reaches_no_daemon():
    status, _ = writ_daemon_client.post_json("/session/probe-session/context-percent", {"percent": 1})
    assert status == 0
'''


def test_hook_client_never_connects_to_the_operator_socket(tmp_path: Path) -> None:
    # A short home: AF_UNIX caps a socket path near 104 bytes, and tmp_path is longer.
    home = Path(tempfile.mkdtemp(prefix="writ-home-"))
    run_dir = home / ".cache" / "writ" / "run"
    run_dir.mkdir(parents=True)
    operator_socket = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        operator_socket.bind(str(run_dir / "writ.sock"))
        operator_socket.listen(8)
        probe = tmp_path / "test_probe.py"
        probe.write_text(SOCKET_PROBE)
        env = {**os.environ, "HOME": str(home), "REPO_ROOT": str(REPO_ROOT),
               "WRIT_SESSION_BASE": f"http://localhost:{free_port()}"}
        # The operator's shell exports no WRIT_SOCKET, so the client defaults to
        # ~/.cache/writ/run/writ.sock.
        env.pop("WRIT_SOCKET", None)
        proc = subprocess.run(
            [sys.executable, "-m", "pytest", str(probe), "-c", str(REPO_ROOT / "pyproject.toml"),
             "-p", "no:cacheprovider", "-q"],
            cwd=tmp_path, env=env, capture_output=True, text=True, timeout=120, check=False,
        )
        assert proc.returncode == 0, proc.stdout + proc.stderr
        # Never accepted, so every connection the client made is still queued.
        operator_socket.setblocking(False)
        connections = 0
        while True:
            try:
                conn, _ = operator_socket.accept()
            except BlockingIOError:
                break
            conn.close()
            connections += 1
        assert connections == 0, "the hook client connected to the operator's daemon socket"
    finally:
        operator_socket.close()
        shutil.rmtree(home, ignore_errors=True)
