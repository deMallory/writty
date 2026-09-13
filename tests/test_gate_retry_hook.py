"""writ-gate-retry.sh: re-run a pending gate advance after the agent rewrites the artifact.

Flow it closes: the user types "approved", the plan.md validator rejects a format detail,
the token is KEPT (gate.py no longer spends it), the agent fixes plan.md, and this
PostToolUse hook posts the advance again with the same token. One approval, one advance,
no second "approved".

The hook is silent and exits 0 unless ALL hold: an artifact file was written (plan.md,
or a test-category file), mode is work, phase is planning or testing, and an unexpired
token exists. The daemon is a stub here so the test owns exactly what was posted.
"""
from __future__ import annotations

import json
import os
import subprocess
import threading
import uuid
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest

WRIT_ROOT = Path(__file__).resolve().parent.parent
HOOK = WRIT_ROOT / "hooks" / "scripts" / "writ-gate-retry.sh"


class _Stub(HTTPServer):
    def __init__(self, reply: dict):
        super().__init__(("127.0.0.1", 0), _Handler)
        self.reply = reply
        self.posts: list[tuple[str, dict]] = []


class _Handler(BaseHTTPRequestHandler):
    def do_POST(self):  # noqa: N802
        n = int(self.headers.get("Content-Length", "0"))
        body = json.loads(self.rfile.read(n) or b"{}")
        self.server.posts.append((self.path, body))
        out = json.dumps(self.server.reply).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(out)))
        self.end_headers()
        self.wfile.write(out)

    def log_message(self, *_):
        pass


@pytest.fixture
def stub():
    srv = _Stub({"advanced": True, "phase": "testing", "from": "planning"})
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    yield srv
    srv.shutdown()


def _seed(cache_dir: Path, sid: str, mode: str, phase: str) -> None:
    (cache_dir / f"writ-session-{sid}.json").write_text(
        json.dumps({"mode": mode, "current_phase": phase, "gates_approved": []})
    )


def _token(sid: str) -> Path:
    p = Path("/tmp") / f"writ-gate-token-{sid}"
    p.write_text("tok-" + sid)
    return p


def _run(cache_dir: Path, port: int, sid: str, file_path: str) -> subprocess.CompletedProcess:
    env = {
        **os.environ,
        "WRIT_CACHE_DIR": str(cache_dir),
        "WRIT_HOST": "127.0.0.1",
        "WRIT_PORT": str(port),
        "WRIT_NO_AUTOSTART": "1",
    }
    payload = json.dumps({
        "session_id": sid,
        "tool_name": "Write",
        "tool_input": {"file_path": file_path},
        "cwd": str(cache_dir),
    })
    return subprocess.run(["bash", str(HOOK)], input=payload, capture_output=True,
                          text=True, env=env, timeout=30, check=False)


class TestSilentCases:
    def test_no_token_posts_nothing(self, tmp_path, stub):
        sid = f"rt-{uuid.uuid4().hex[:8]}"
        _seed(tmp_path, sid, "work", "planning")
        r = _run(tmp_path, stub.server_port, sid, "/proj/plan.md")
        assert r.returncode == 0
        assert stub.posts == []
        assert r.stdout.strip() == ""

    def test_non_work_mode_posts_nothing(self, tmp_path, stub):
        sid = f"rt-{uuid.uuid4().hex[:8]}"
        _seed(tmp_path, sid, "conversation", "planning")
        tok = _token(sid)
        try:
            r = _run(tmp_path, stub.server_port, sid, "/proj/plan.md")
        finally:
            tok.unlink(missing_ok=True)
        assert r.returncode == 0
        assert stub.posts == []

    def test_non_artifact_file_posts_nothing(self, tmp_path, stub):
        sid = f"rt-{uuid.uuid4().hex[:8]}"
        _seed(tmp_path, sid, "work", "planning")
        tok = _token(sid)
        try:
            r = _run(tmp_path, stub.server_port, sid, "/proj/src/x.py")
        finally:
            tok.unlink(missing_ok=True)
        assert r.returncode == 0
        assert stub.posts == []

    def test_implementation_phase_posts_nothing(self, tmp_path, stub):
        sid = f"rt-{uuid.uuid4().hex[:8]}"
        _seed(tmp_path, sid, "work", "implementation")
        tok = _token(sid)
        try:
            r = _run(tmp_path, stub.server_port, sid, "/proj/plan.md")
        finally:
            tok.unlink(missing_ok=True)
        assert r.returncode == 0
        assert stub.posts == []


class TestRetryPosts:
    def test_plan_write_with_live_token_posts_once(self, tmp_path, stub):
        sid = f"rt-{uuid.uuid4().hex[:8]}"
        _seed(tmp_path, sid, "work", "planning")
        tok = _token(sid)
        try:
            r = _run(tmp_path, stub.server_port, sid, "/proj/plan.md")
        finally:
            tok.unlink(missing_ok=True)
        assert r.returncode == 0
        assert len(stub.posts) == 1, r.stderr
        path, body = stub.posts[0]
        assert path == f"/session/{sid}/advance-phase"
        assert body.get("token") == "tok-" + sid
        assert body.get("confirmation_source") == "pattern"
        assert body.get("cwd"), "the server resolves the project root from cwd"
        assert "advanced" in r.stdout.lower() or "approved" in r.stdout.lower()

    def test_test_file_write_in_testing_phase_posts(self, tmp_path, stub):
        sid = f"rt-{uuid.uuid4().hex[:8]}"
        _seed(tmp_path, sid, "work", "testing")
        tok = _token(sid)
        try:
            r = _run(tmp_path, stub.server_port, sid, "/proj/tests/test_x.py")
        finally:
            tok.unlink(missing_ok=True)
        assert r.returncode == 0
        assert len(stub.posts) == 1

    def test_rejection_is_reported_and_token_kept(self, tmp_path):
        srv = _Stub({"advanced": False, "error": "plan.md validation failed: ## Files",
                     "token_spent": False})
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        sid = f"rt-{uuid.uuid4().hex[:8]}"
        _seed(tmp_path, sid, "work", "planning")
        tok = _token(sid)
        try:
            r = _run(tmp_path, srv.server_port, sid, "/proj/plan.md")
            assert r.returncode == 0
            assert "REJECTED" in r.stdout
            assert "plan.md validation failed" in r.stdout
            assert tok.exists(), "the hook must not delete the token; only the server may"
        finally:
            srv.shutdown()
            tok.unlink(missing_ok=True)
