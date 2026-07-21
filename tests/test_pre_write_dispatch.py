"""Tests for the /pre-write-check endpoint and hook consolidation (Cycle B, Item 8).

Per TEST-TDD-001: skeletons approved before implementation.
Covers: POST /pre-write-check endpoint decisions (allow/deny/ask), RAG metadata
in the allow response, _can_write_check reusable function, fallback path in
common.sh, and settings.json hook consolidation.

C1 (Wave 1 Cycle 1, plan.md): TestCanWriteFallbackForwardsEnvelope pins the
daemon-degraded can-write fallback -- bin/lib/common.sh:450-454 hardcodes
body="{}" and never reads the piped tool envelope from stdin, so the gate
check runs on an empty file_path and silently allows. It also proves the
server's {"can_write": bool} response gets normalized to the {"decision": ...}
shape the fallback's consumer (writ-pre-write-dispatch.sh:112) actually reads.
RED before the common.sh fix lands.
"""

from __future__ import annotations

import importlib.util
import json
import os
import shlex
import subprocess
import threading
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio

try:
    from httpx import AsyncClient, ASGITransport
except ImportError:
    pytestmark = pytest.mark.skip(reason="httpx not installed")

from tests.fixtures.net import free_port as _free_port
from writ.server import app  # type: ignore[import]
from pathlib import Path

try:
    from writ.server import PreWriteCheckRequest  # type: ignore[import]
except ImportError:
    PreWriteCheckRequest = None  # type: ignore[assignment,misc]

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SESSION_ID = "test-pre-write-dispatch"
SKILL_DIR = str(Path.home() / ".claude/skills/writ")
WRIT_SESSION_PY = f"{SKILL_DIR}/bin/lib/writ-session.py"
COMMON_SH = f"{SKILL_DIR}/bin/lib/common.sh"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _load_writ_session():
    """Load writ-session.py as a module without installing it."""
    spec = importlib.util.spec_from_file_location("writ_session_dispatch", WRIT_SESSION_PY)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _make_allow_session_cache(**overrides: Any) -> dict[str, Any]:
    """Cache representing a session where writes are permitted."""
    base: dict[str, Any] = {
        "session_id": SESSION_ID,
        "mode": "work",
        "current_phase": "implementation",
        "remaining_budget": 5000,
        "context_percent": 40,
        "loaded_rule_ids": [],
        "loaded_rules": [],
        "loaded_rule_ids_by_phase": {},
        "queries": 3,
        "pending_violations": [],
        "escalation": {"needed": False},
        "invalidation_history": {},
        "failed_writes": [],
        "gates_approved": ["phase-a", "test-skeletons"],
        "denial_counts": {},
    }
    base.update(overrides)
    return base


def _make_deny_session_cache(**overrides: Any) -> dict[str, Any]:
    """Cache representing a session where writes are blocked (gate not approved)."""
    base = _make_allow_session_cache(
        gates_approved=[],
        current_phase="planning",
    )
    base.update(overrides)
    return base


@pytest.fixture()
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture()
def mock_writ_session_allow():
    """Mock writ_session where the gate check passes."""
    mock = MagicMock()
    mock._read_cache = MagicMock(return_value=_make_allow_session_cache())
    mock._write_cache = MagicMock(return_value=None)
    mock.DEFAULT_SESSION_BUDGET = 8000

    def _fake_can_write_check(session_id: str, envelope: dict, skill_dir: str, cache=None) -> dict:
        return {"can_write": True, "reason": None}

    mock._can_write_check = MagicMock(side_effect=_fake_can_write_check)
    return mock


@pytest.fixture()
def mock_writ_session_deny():
    """Mock writ_session where the gate check fails."""
    mock = MagicMock()
    mock._read_cache = MagicMock(return_value=_make_deny_session_cache())
    mock._write_cache = MagicMock(return_value=None)
    mock.DEFAULT_SESSION_BUDGET = 8000

    def _fake_can_write_check(session_id: str, envelope: dict, skill_dir: str, cache=None) -> dict:
        return {"can_write": False, "reason": "[ENF-GATE-PLAN] Gate not approved"}

    mock._can_write_check = MagicMock(side_effect=_fake_can_write_check)
    return mock


@pytest_asyncio.fixture()
async def client_allow(mock_writ_session_allow):
    transport = ASGITransport(app=app)
    with patch("writ.server.writ_session", mock_writ_session_allow):
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            yield ac


@pytest_asyncio.fixture()
async def client_deny(mock_writ_session_deny):
    transport = ASGITransport(app=app)
    with patch("writ.server.writ_session", mock_writ_session_deny):
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            yield ac


def _pre_write_payload(file_path: str = "writ/server.py") -> dict[str, Any]:
    return {
        "session_id": SESSION_ID,
        "tool_input": {"file_path": file_path, "content": "# stub"},
        "skill_dir": SKILL_DIR,
        "file_path": file_path,
    }


# ---------------------------------------------------------------------------
# TestPreWriteCheckEndpoint -- response shape
# ---------------------------------------------------------------------------


class TestPreWriteCheckEndpoint:
    """POST /pre-write-check returns allow/deny/ask decisions with correct structure."""

    @pytest.mark.asyncio
    async def test_allow_decision_returns_200(self, client_allow: AsyncClient) -> None:
        """POST /pre-write-check returns HTTP 200 when gate passes."""
        resp = await client_allow.post("/pre-write-check", json=_pre_write_payload())
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_allow_decision_field_is_allow(self, client_allow: AsyncClient) -> None:
        """Response decision is 'allow' when gate check passes."""
        resp = await client_allow.post("/pre-write-check", json=_pre_write_payload())
        body = resp.json()
        assert body["decision"] == "allow"

    @pytest.mark.asyncio
    async def test_deny_decision_field_is_deny(self, client_deny: AsyncClient) -> None:
        """Response decision is 'deny' when gate check fails."""
        resp = await client_deny.post("/pre-write-check", json=_pre_write_payload())
        body = resp.json()
        assert body["decision"] in ("deny", "ask")

    @pytest.mark.asyncio
    async def test_deny_response_includes_reason(self, client_deny: AsyncClient) -> None:
        """Deny response includes a non-empty reason string."""
        resp = await client_deny.post("/pre-write-check", json=_pre_write_payload())
        body = resp.json()
        assert body.get("reason") is not None
        assert len(body["reason"]) > 0

    @pytest.mark.asyncio
    async def test_deny_reason_matches_gate_denial_format(
        self, client_deny: AsyncClient
    ) -> None:
        """Deny reason includes the ENF- prefix pattern matching check-gate-approval.sh output."""
        resp = await client_deny.post("/pre-write-check", json=_pre_write_payload())
        body = resp.json()
        assert "ENF-" in body.get("reason", "")

    @pytest.mark.asyncio
    async def test_allow_response_includes_rag_rules_field(
        self, client_allow: AsyncClient
    ) -> None:
        """Allow response includes rag_rules text field (may be empty string if no rules)."""
        resp = await client_allow.post("/pre-write-check", json=_pre_write_payload())
        assert resp.status_code == 200
        body = resp.json()
        assert "rag_rules" in body, "allow response must include rag_rules field"
        assert isinstance(body["rag_rules"], str)

    @pytest.mark.asyncio
    async def test_allow_response_includes_rag_meta_field(
        self, client_allow: AsyncClient
    ) -> None:
        """Allow response includes rag_meta with rule_ids list and tokens integer."""
        resp = await client_allow.post("/pre-write-check", json=_pre_write_payload())
        assert resp.status_code == 200
        body = resp.json()
        assert "rag_meta" in body, "allow response must include rag_meta field"
        rag_meta = body["rag_meta"]
        assert "rule_ids" in rag_meta, "rag_meta must include rule_ids"
        assert "tokens" in rag_meta, "rag_meta must include tokens"
        assert isinstance(rag_meta["rule_ids"], list)
        assert isinstance(rag_meta["tokens"], int)

    @pytest.mark.asyncio
    async def test_repeated_denials_escalate_to_ask(
        self, client_deny: AsyncClient, mock_writ_session_deny
    ) -> None:
        """After repeated deny decisions for the same session, decision escalates to 'ask'."""
        # Set denial_counts >= 2 to trigger escalation
        deny_cache = _make_deny_session_cache(denial_counts={"phase-a": 3})
        mock_writ_session_deny._read_cache.return_value = deny_cache
        resp = await client_deny.post("/pre-write-check", json=_pre_write_payload())
        body = resp.json()
        assert body["decision"] == "ask"

    @pytest.mark.asyncio
    async def test_endpoint_rejects_missing_session_id(
        self, client_allow: AsyncClient
    ) -> None:
        """POST /pre-write-check without session_id returns HTTP 422."""
        payload = {k: v for k, v in _pre_write_payload().items() if k != "session_id"}
        resp = await client_allow.post("/pre-write-check", json=payload)
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_endpoint_handler_is_async(self) -> None:
        """POST /pre-write-check route endpoint is declared with async def."""
        import inspect
        routes = [
            r for r in app.routes
            if hasattr(r, "path") and "pre-write-check" in getattr(r, "path", "")
        ]
        assert len(routes) > 0, "/pre-write-check route not registered"
        for route in routes:
            endpoint = getattr(route, "endpoint", None)
            if endpoint is not None:
                assert inspect.iscoroutinefunction(endpoint)


# ---------------------------------------------------------------------------
# TestCanWriteCheckReusable -- _can_write_check extraction
# ---------------------------------------------------------------------------


class TestCanWriteCheckReusable:
    """_can_write_check must be extractable from cmd_can_write as a standalone function."""

    def test_can_write_check_function_exists_in_writ_session(self) -> None:
        """writ-session.py defines _can_write_check as a callable function."""
        mod = _load_writ_session()
        assert hasattr(mod, "_can_write_check"), (
            "_can_write_check must be defined as a standalone function in writ-session.py"
        )
        assert callable(mod._can_write_check), (
            "_can_write_check must be callable"
        )

    def test_can_write_check_returns_dict(self) -> None:
        """_can_write_check returns a dict (not None or bool)."""
        mod = _load_writ_session()
        import tempfile
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.dict(os.environ, {"WRIT_CACHE_DIR": tmpdir}):
                # Create a cache with work mode + gates approved
                cache = _make_allow_session_cache()
                path = mod._cache_path(SESSION_ID)
                import json
                with open(path, "w") as f:
                    json.dump(cache, f)
                result = mod._can_write_check(SESSION_ID, {"tool_input": {"file_path": "test.py"}})
                assert isinstance(result, dict)

    def test_can_write_check_result_has_can_write_field(self) -> None:
        """_can_write_check result contains can_write bool field."""
        mod = _load_writ_session()
        import tempfile
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.dict(os.environ, {"WRIT_CACHE_DIR": tmpdir}):
                cache = _make_allow_session_cache()
                path = mod._cache_path(SESSION_ID)
                import json
                with open(path, "w") as f:
                    json.dump(cache, f)
                result = mod._can_write_check(SESSION_ID, {"tool_input": {"file_path": "test.py"}})
                assert "can_write" in result
                assert isinstance(result["can_write"], bool)

    def test_can_write_check_returns_reason_on_deny(self) -> None:
        """_can_write_check result contains a non-empty reason string when can_write is False."""
        mod = _load_writ_session()
        import tempfile
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.dict(os.environ, {"WRIT_CACHE_DIR": tmpdir}):
                # Cache with no mode = deny
                cache = _make_deny_session_cache(mode=None, gates_approved=[])
                path = mod._cache_path(SESSION_ID)
                import json
                with open(path, "w") as f:
                    json.dump(cache, f)
                result = mod._can_write_check(SESSION_ID, {"tool_input": {"file_path": "src/main.py"}})
                assert result["can_write"] is False
                assert result["reason"] is not None
            assert len(result["reason"]) > 0

    def test_cmd_can_write_calls_can_write_check(self) -> None:
        """cmd_can_write delegates to _can_write_check internally (source inspection)."""
        mod = _load_writ_session()
        import inspect
        src = inspect.getsource(mod.cmd_can_write)
        assert "_can_write_check" in src, (
            "cmd_can_write must delegate to _can_write_check"
        )


# ---------------------------------------------------------------------------
# TestPreWriteCheckRequestModel -- Pydantic model
# ---------------------------------------------------------------------------


class TestPreWriteCheckRequestModel:
    """PreWriteCheckRequest Pydantic model has required fields."""

    def test_pre_write_check_request_importable(self) -> None:
        """PreWriteCheckRequest can be imported from writ.server."""
        assert PreWriteCheckRequest is not None

    def test_pre_write_check_request_has_session_id_field(self) -> None:
        """PreWriteCheckRequest has session_id: str field."""
        model = PreWriteCheckRequest(session_id="test", tool_input={}, skill_dir="", file_path="")
        assert model.session_id == "test"

    def test_pre_write_check_request_has_file_path_field(self) -> None:
        """PreWriteCheckRequest has file_path: str field."""
        model = PreWriteCheckRequest(session_id="test", file_path="/tmp/foo.py")
        assert model.file_path == "/tmp/foo.py"

    def test_pre_write_check_request_has_skill_dir_field(self) -> None:
        """PreWriteCheckRequest has skill_dir: str field."""
        model = PreWriteCheckRequest(session_id="test", skill_dir="/skill")
        assert model.skill_dir == "/skill"

    def test_pre_write_check_request_has_tool_input_field(self) -> None:
        """PreWriteCheckRequest has tool_input: dict field for the full envelope."""
        model = PreWriteCheckRequest(session_id="test", tool_input={"file_path": "foo.py"})
        assert model.tool_input == {"file_path": "foo.py"}


# ---------------------------------------------------------------------------
# TestFallbackPath -- dispatcher falls back when server unreachable
# ---------------------------------------------------------------------------


class TestFallbackPath:
    """Fallback: dispatcher uses individual _writ_session calls when server is unreachable."""

    def test_common_sh_has_pre_write_check_case(self) -> None:
        """common.sh contains a pre-write-check case in _writ_session()."""
        with open(COMMON_SH) as f:
            source = f.read()
        assert "pre-write-check" in source, (
            "common.sh must have a pre-write-check case in _writ_session()"
        )

    def test_common_sh_pre_write_check_posts_to_endpoint(self) -> None:
        """common.sh pre-write-check case POSTs to /pre-write-check via curl."""
        with open(COMMON_SH) as f:
            source = f.read()
        assert "/pre-write-check" in source, (
            "common.sh pre-write-check case must POST to /pre-write-check"
        )

    def test_common_sh_pre_write_check_has_fallback(self) -> None:
        """common.sh pre-write-check has a fallback to individual subcommand calls."""
        with open(COMMON_SH) as f:
            source = f.read()
        # The fallback path must invoke can-write at minimum when server is down
        assert "can-write" in source, (
            "common.sh fallback for pre-write-check must include can-write call"
        )


class TestGateBypassRegression:
    """Guards the gate-enforcement bypass found 2026-06-18: the dispatch hook
    sent an empty `{}` body to /pre-write-check, so the server saw no file_path
    and always returned "allow" -- silently disabling the Write/Edit gate AND
    suppressing every real write_attempt event. Two coupled defects, both guarded:
      1. common.sh read the body from $2 but the hook passed it as the only arg.
      2. the default `${2:-{}}` appended a stray `}` (malformed JSON -> server
         reject -> fallback) even once the arg position was right.
    """

    DISPATCH = f"{SKILL_DIR}/hooks/scripts/writ-pre-write-dispatch.sh"

    def test_dispatch_passes_body_as_second_arg(self) -> None:
        with open(self.DISPATCH) as f:
            src = f.read()
        # SESSION_ID must precede CHECK_BODY so the body lands in the helper's $2.
        assert '_writ_session pre-write-check "$SESSION_ID" "$CHECK_BODY"' in src, (
            "dispatch hook must call `_writ_session pre-write-check \"$SESSION_ID\" "
            "\"$CHECK_BODY\"` -- a single CHECK_BODY arg lands in $1 and the helper "
            "reads the body from $2, sending an empty {} body (gate bypass)"
        )

    def test_common_sh_pre_write_check_default_is_quoted(self) -> None:
        with open(COMMON_SH) as f:
            src = f.read()
        # The quoted default; the bare ${2:-{}} appends a stray } when $2 is set.
        assert 'check_body="${2:-"{}"}"' in src, (
            "common.sh pre-write-check must use the quoted default "
            "`${2:-\"{}\"}` -- the bare `${2:-{}}` appends a stray `}` to a set "
            "body, producing malformed JSON the server rejects"
        )
        assert 'check_body="${2:-{}}"' not in src, (
            "the buggy unquoted `${2:-{}}` default must not reappear"
        )


# ---------------------------------------------------------------------------
# TestCanWriteFallbackForwardsEnvelope -- C1 (Wave 1 Cycle 1, plan.md)
# ---------------------------------------------------------------------------
#
# bin/lib/common.sh's `_writ_session can-write` arm (lines 450-454) hardcodes
# `body="{}"` and never reads stdin, so the piped `{"tool_input": {...}}`
# envelope built by the pre-write-check fallback (common.sh:567-577) is
# discarded before it ever reaches the daemon. The server's can-write route
# (server.py:835-848) then sees an empty file_path and returns can_write=True
# -- a silent full allow on the daemon-degraded path.
#
# A second, coupled defect: the server route's response shape is
# {"can_write": bool, "reason": ...}, but the fallback's consumer
# (writ-pre-write-dispatch.sh:112) reads `result.get('decision', 'allow')`.
# So even a corrected envelope forward would still read as "allow" unless the
# response is normalized to {"decision": "allow"|"deny", ...}.
#
# These tests run a real `bash -c 'source common.sh; ...'` subprocess against a
# stub HTTPServer on a free port (never the real daemon), per plan.md
# ## Verification: "the C1 test therefore uses a stub HTTPServer ... it does
# not require (and must not depend on) the daemon being up or down."


class _CanWriteStubHandler(BaseHTTPRequestHandler):
    """Stub `/session/<sid>/can-write` route.

    Records every POST body received (proves whether the piped tool envelope
    was forwarded, or discarded as today's hardcoded body="{}") and returns a
    canned {"can_write": bool, "reason": ...} response -- the REAL server
    route's response shape (server.py:835-848), not the {"decision": ...}
    shape the fallback consumer expects.
    """

    canned_response: bytes = b'{"can_write": false, "reason": "gated"}'
    received_bodies: list[bytes] = []

    def log_message(self, *args) -> None:  # silence stderr noise
        pass

    def do_POST(self) -> None:  # noqa: N802 (http.server API)
        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length) if length else b"{}"
        if self.path.endswith("/can-write"):
            _CanWriteStubHandler.received_bodies.append(raw)
            self._ok(_CanWriteStubHandler.canned_response)
        else:
            self.send_error(404)

    def _ok(self, body: bytes) -> None:
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


@contextmanager
def _can_write_stub(response: dict):
    """Start the stub can-write daemon on a free port; yield (port, get_bodies)."""
    _CanWriteStubHandler.received_bodies = []
    _CanWriteStubHandler.canned_response = json.dumps(response).encode()
    port = _free_port()
    srv = HTTPServer(("localhost", port), _CanWriteStubHandler)
    thread = threading.Thread(target=srv.serve_forever, daemon=True)
    thread.start()
    try:
        yield port, (lambda: list(_CanWriteStubHandler.received_bodies))
    finally:
        srv.shutdown()
        thread.join(timeout=2)


class TestCanWriteFallbackForwardsEnvelope:
    """C1: the can-write fallback arm of _writ_session must forward the piped
    tool envelope as the POST body (not today's hardcoded `body="{}"`), and
    normalize the daemon's `{"can_write": bool}` response into the
    `{"decision": "allow"|"deny"}` shape the pre-write-check fallback consumer
    reads. RED before the common.sh fix lands (plan.md ## Analysis, C1).
    """

    @staticmethod
    def _run_can_write(
        *, piped: dict, port: int, sid: str = "cw-fallback-test-sid", skill_dir: str = "/tmp/writ-cw-test-skill"
    ) -> subprocess.CompletedProcess:
        # WRIT_HOST / WRIT_PORT must be set BEFORE `source common.sh` -- the
        # module-level WRIT_SESSION_BASE (common.sh:390-392) is computed once,
        # at source time, from these env vars.
        env = os.environ.copy()
        env["WRIT_HOST"] = "localhost"
        env["WRIT_PORT"] = str(port)
        cmd = (
            f"source {shlex.quote(COMMON_SH)}; "
            f"printf %s {shlex.quote(json.dumps(piped))} | "
            f"_writ_session can-write {shlex.quote(sid)} --skill-dir {shlex.quote(skill_dir)}"
        )
        return subprocess.run(
            ["bash", "-c", cmd],
            env=env,
            capture_output=True,
            text=True,
            timeout=10,
        )

    def test_fallback_posts_tool_input_in_body(self) -> None:
        """The stub's recorded POST body must carry the piped tool_input.file_path.

        RED today: the can-write arm hardcodes body="{}", so tool_input never
        crosses to the daemon -- the recorded body is `{}`, not the envelope.
        """
        piped = {"tool_input": {"file_path": "src/gated_file.py"}}
        with _can_write_stub({"can_write": False, "reason": "gated"}) as (port, get_bodies):
            result = self._run_can_write(piped=piped, port=port)
            bodies = get_bodies()
        assert bodies, (
            f"stub can-write route received no POST at all "
            f"(stdout={result.stdout!r} stderr={result.stderr!r})"
        )
        received = json.loads(bodies[-1])
        assert isinstance(received, dict)
        assert received.get("tool_input", {}).get("file_path") == "src/gated_file.py", (
            f"expected the forwarded body's tool_input.file_path == 'src/gated_file.py', "
            f"got body={received!r} -- the can-write arm hardcodes body=\"{{}}\" today, "
            f"discarding the piped envelope entirely"
        )

    def test_fallback_deny_yields_decision_deny(self) -> None:
        """A can_write:false stub response must surface as {"decision": "deny", ...}.

        RED today: the arm returns the server's raw {"can_write": false, ...}
        shape untouched; the fallback consumer reads .get('decision', 'allow'),
        which silently defaults to allow on this shape.
        """
        piped = {"tool_input": {"file_path": "src/gated_file.py"}}
        with _can_write_stub({"can_write": False, "reason": "gated"}) as (port, _get_bodies):
            result = self._run_can_write(piped=piped, port=port)
        stdout = result.stdout.strip()
        assert stdout, (
            f"_writ_session can-write produced no stdout "
            f"(returncode={result.returncode} stderr={result.stderr!r})"
        )
        parsed = json.loads(stdout)
        assert parsed.get("decision") == "deny", (
            f"expected {{'decision': 'deny', ...}}, got {parsed!r} -- the can-write "
            f"route emits {{'can_write': bool, 'reason': ...}}; without shape "
            f"normalization the fallback consumer's .get('decision', 'allow') silently "
            f"allows a gated write"
        )

    def test_fallback_allow_yields_decision_allow(self) -> None:
        """A can_write:true stub response must surface as {"decision": "allow", ...}."""
        piped = {"tool_input": {"file_path": "src/allowed_file.py"}}
        with _can_write_stub({"can_write": True, "reason": None}) as (port, _get_bodies):
            result = self._run_can_write(piped=piped, port=port)
        stdout = result.stdout.strip()
        assert stdout, (
            f"_writ_session can-write produced no stdout "
            f"(returncode={result.returncode} stderr={result.stderr!r})"
        )
        parsed = json.loads(stdout)
        assert parsed.get("decision") == "allow", (
            f"expected {{'decision': 'allow', ...}}, got {parsed!r}"
        )
