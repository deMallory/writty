"""Fix C (Phase 3): sub-agent mode inheritance reads the AUTHORITATIVE file cache.

The SubagentStart hook (.claude/hooks/writ-subagent-start.sh) reads the parent's mode to
seed each spawned sub-agent's session. It previously read that via `_writ_session read`
(common.sh), which is DAEMON-FIRST: it curls the live daemon and only falls back to the
file cache when the daemon is unreachable. When the daemon's in-memory / cache-dir view
diverged from the file cache where `writ-session.py mode set` actually writes, the hook
read a stale parent state (the observed mode=None production symptom) and the sub-agent
inherited the wrong mode -- running gate-less.

The fix reads the parent mode FILE-DIRECT (`python3 writ-session.py read <parent>`), which
is authoritative. These tests reproduce the desync with a stub daemon that returns a
divergent parent state (mode=None, no gates) and assert the spawned sub-agent inherits the
FILE cache's mode/phase/gates instead.

Per TEST-REGRESSION-001: RED before the file-direct read, GREEN after.
"""

from __future__ import annotations

import json
import os
import subprocess
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from tests.fixtures.net import free_port as _free_port

HOOK = os.path.abspath(
    os.path.join(
        os.path.dirname(__file__), os.pardir, "hooks", "scripts", "writ-subagent-start.sh"
    )
)


class _DivergentDaemonHandler(BaseHTTPRequestHandler):
    """Stub of a live daemon whose session view diverges from the file cache: every
    session reads back mode=None with no gates -- the production desync that made
    sub-agents inherit a gate-less session. /health 404s so the hook skips its rules
    query (irrelevant to mode inheritance)."""

    def log_message(self, *args):  # silence stderr noise during tests
        pass

    def do_GET(self):  # noqa: N802 (http.server API)
        if self.path.startswith("/session/") and self.path.endswith("/mode"):
            body = json.dumps({"mode": None}).encode()
        elif self.path.startswith("/session/"):
            body = json.dumps(
                {"mode": None, "current_phase": "planning", "gates_approved": []}
            ).encode()
        else:
            self.send_error(404)
            return
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


@pytest.fixture()
def divergent_daemon():
    """A stub daemon on a free port that returns a divergent (mode=None) parent state."""
    port = _free_port()
    srv = HTTPServer(("localhost", port), _DivergentDaemonHandler)
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    try:
        yield port
    finally:
        srv.shutdown()


def _seed_parent(cache_dir, parent_id, *, mode, phase, gates):
    """Write a parent session file cache directly (the hook reads only these fields)."""
    path = os.path.join(str(cache_dir), f"writ-session-{parent_id}.json")
    with open(path, "w") as f:
        json.dump(
            {"mode": mode, "current_phase": phase, "gates_approved": gates}, f
        )


def _run_start_hook(*, cache_dir, stub_port, agent_id, agent_type, parent_id):
    env = os.environ.copy()
    env["WRIT_CACHE_DIR"] = str(cache_dir)
    env["WRIT_PORT"] = str(stub_port)  # point _writ_session read at the divergent stub
    env["WRIT_HOST"] = "localhost"
    env["WRIT_FRICTION_LOG"] = os.path.join(str(cache_dir), "friction.log")
    envelope = {
        "agent_id": agent_id,
        "agent_type": agent_type,
        "session_id": parent_id,
        "hook_event_name": "SubagentStart",
        "prompt": "implement the approved plan",
    }
    return subprocess.run(
        ["bash", HOOK],
        input=json.dumps(envelope),
        capture_output=True,
        text=True,
        env=env,
        timeout=20,
    )


def _read_agent_cache(cache_dir, agent_id):
    path = os.path.join(str(cache_dir), f"writ-session-{agent_id}.json")
    assert os.path.exists(path), f"sub-agent cache not created at {path}"
    with open(path) as f:
        return json.load(f)


class TestSubagentModeInheritance:
    """The spawned sub-agent inherits the parent's FILE-cache mode, not the daemon's."""

    def test_inherits_work_mode_from_file_cache_despite_divergent_daemon(
        self, tmp_path, divergent_daemon
    ):
        """Parent file cache says work; the stub daemon says mode=None. The sub-agent
        must inherit work (file is authoritative)."""
        parent = "parent-mi-1"
        _seed_parent(
            tmp_path, parent, mode="work", phase="implementation", gates=["design"]
        )
        result = _run_start_hook(
            cache_dir=tmp_path,
            stub_port=divergent_daemon,
            agent_id="agent-mi-1",
            agent_type="writ-implementer",
            parent_id=parent,
        )
        assert result.returncode == 0, result.stderr
        cache = _read_agent_cache(tmp_path, "agent-mi-1")
        assert cache["mode"] == "work"

    def test_inherits_phase_and_gates_from_file_cache(self, tmp_path, divergent_daemon):
        """Structural state (phase + approved gates) comes from the file cache too."""
        parent = "parent-mi-2"
        _seed_parent(
            tmp_path, parent, mode="work", phase="implementation", gates=["design"]
        )
        result = _run_start_hook(
            cache_dir=tmp_path,
            stub_port=divergent_daemon,
            agent_id="agent-mi-2",
            agent_type="writ-implementer",
            parent_id=parent,
        )
        assert result.returncode == 0, result.stderr
        cache = _read_agent_cache(tmp_path, "agent-mi-2")
        assert cache["current_phase"] == "implementation"
        assert cache["gates_approved"] == ["design"]

    def test_null_parent_mode_coalesces_to_work(self, tmp_path, divergent_daemon):
        """Audit P1: a parent cache with mode=null (key present, value None) must NOT
        propagate None to the child -- it coalesces to the 'work' default."""
        parent = "parent-mi-null"
        _seed_parent(tmp_path, parent, mode=None, phase=None, gates=None)
        result = _run_start_hook(
            cache_dir=tmp_path,
            stub_port=divergent_daemon,
            agent_id="agent-mi-null",
            agent_type="writ-implementer",
            parent_id=parent,
        )
        assert result.returncode == 0, result.stderr
        cache = _read_agent_cache(tmp_path, "agent-mi-null")
        assert cache["mode"] == "work"
        assert cache["current_phase"] == "planning"
        assert cache["gates_approved"] == []

    def test_subagent_flagged_and_budget_fresh(self, tmp_path, divergent_daemon):
        """Inheritance preserves the existing isolation contract: fresh budget,
        is_subagent flag set, empty loaded rules."""
        parent = "parent-mi-3"
        _seed_parent(tmp_path, parent, mode="work", phase="planning", gates=[])
        result = _run_start_hook(
            cache_dir=tmp_path,
            stub_port=divergent_daemon,
            agent_id="agent-mi-3",
            agent_type="writ-explorer",
            parent_id=parent,
        )
        assert result.returncode == 0, result.stderr
        cache = _read_agent_cache(tmp_path, "agent-mi-3")
        assert cache["is_subagent"] is True
        assert cache["loaded_rule_ids"] == []
