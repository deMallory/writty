"""Point WRIT_LOG_ROOT at a throwaway dir for the whole pytest run.

Loaded from pyproject addopts, not conftest.py, because `--noconftest` skips
conftest.py and its per-test redirect, and such runs wrote test rows into the
operator's ~/.cache/writ/logs. An assignment, not setdefault: the operator's shell
exports the real root. conftest's autouse fixture still narrows it per test.
"""

import os
import tempfile

os.environ["WRIT_LOG_ROOT"] = tempfile.mkdtemp(prefix="writ-test-logs-")
