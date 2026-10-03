"""Point WRIT_LOG_ROOT, WRIT_CACHE_DIR and WRIT_SOCKET at throwaway paths for the whole run.

Loaded from pyproject addopts, not conftest.py, because `--noconftest` skips
conftest.py and its per-test redirect, and such runs wrote test rows into the
operator's ~/.cache/writ/logs. Assignments, not setdefault: the operator's shell
exports the real roots (Claude Code pins WRIT_CACHE_DIR to ~/.cache/writ/session), and
setdefault kept them. conftest's autouse fixture still narrows the log root per test.

The cache dir is set once for the run because the test daemon reads it once at start
(tests/_daemon.py::expected_cache_dir). Subprocess tests that build their env from
os.environ inherit it. Tests that need their own dir use monkeypatch.setenv, which
restores this value afterwards. mkdtemp, not a fixed name, so parallel runs do not
share a dir.

WRIT_SOCKET names a socket no operator daemon holds. Unset, bin/lib/writ_daemon_client.py
falls back to ~/.cache/writ/run/writ.sock, the live daemon, which then writes test
sessions into the real store; common.sh skips that socket when WRIT_PORT is set, the
Python client does not. A daemon a test starts with the inherited env binds this path,
so hooks reach that daemon instead.
"""

import os
import tempfile

os.environ["WRIT_LOG_ROOT"] = tempfile.mkdtemp(prefix="writ-test-logs-")
os.environ["WRIT_CACHE_DIR"] = tempfile.mkdtemp(prefix="writ-test-cache-")
os.environ["WRIT_SOCKET"] = os.path.join(tempfile.mkdtemp(prefix="writ-test-run-"), "writ.sock")
