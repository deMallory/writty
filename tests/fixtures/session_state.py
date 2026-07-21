"""Shared session-state pytest fixtures and can-write caller (Wave-5 Cycle 5.3c).

Consolidates the `session_id` and `project_root` fixtures plus the can-write
envelope/stdin/parse dance formerly duplicated in `test_mode_infrastructure.py`
and `test_phase3_centralization.py`. These are imported EXPLICITLY into each
consuming test module (`from tests.fixtures.session_state import session_id,
project_root`), never registered in a root conftest, so they cannot shadow the
many other files that define their own divergent `session_id`/`project_root`
fixtures.

`call_can_write` takes `writ_session` and `skill_dir` as arguments rather than
recomputing them, because each consumer loads `writ-session.py` via its own
`importlib` spec and computes `SKILL_DIR` relative to its own `__file__`.
"""

from __future__ import annotations

import io
import json

import pytest


@pytest.fixture()
def session_id(tmp_path, monkeypatch, request):
    """Provide a session ID and redirect cache to tmp_path.

    The returned name is cosmetic (never asserted; it is only used as a
    cache-file key), so it defaults to a shared literal. A consuming file may
    override it via indirect parametrization (`request.param`) if needed.
    """
    monkeypatch.setenv("WRIT_CACHE_DIR", str(tmp_path))
    return getattr(request, "param", "test-session")


@pytest.fixture()
def project_root(tmp_path):
    """Create a minimal project root with .git marker and gates dir."""
    root = tmp_path / "project"
    root.mkdir()
    (root / ".git").mkdir()
    (root / ".claude" / "gates").mkdir(parents=True)
    return root


def call_can_write(writ_session, session_id, file_path, monkeypatch, capsys, skill_dir=None):
    """Call cmd_can_write with a synthetic tool envelope and return the JSON result."""
    capsys.readouterr()  # clear any prior output
    envelope = json.dumps({"tool_input": {"file_path": file_path}})
    monkeypatch.setattr("sys.stdin", io.StringIO(envelope))
    writ_session.cmd_can_write(session_id, skill_dir)
    out = capsys.readouterr().out.strip()
    return json.loads(out)
