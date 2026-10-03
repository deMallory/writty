"""The Python daemon client picks its transport the way common.sh does.

With WRIT_SOCKET unset, bin/lib/writ_daemon_client.py used the default socket
(~/.cache/writ/run/writ.sock) whenever the file existed, whatever endpoint the caller
named. The suite names WRIT_PORT=8799, so hook calls reached the operator's live daemon,
which wrote test sessions into the real session store. common.sh already skips that
socket when WRIT_HOST or WRIT_PORT is set.

Every test runs the real client against two servers it owns: an HTTP server on a unix
socket standing in for the default socket (DEFAULT_SOCKET is monkeypatched to it), and
one on a free TCP port. Before the fix the stand-in socket answers, so no red run falls
through to the operator's daemon on 8765.
"""
from __future__ import annotations

import shutil
import socketserver
import sys
import tempfile
import threading
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
ENTRIES = ["get_json", "post_json", "post_json_outcome"]


def _client():
    lib = str(REPO / "bin" / "lib")
    if lib not in sys.path:
        sys.path.insert(0, lib)
    import writ_daemon_client

    return writ_daemon_client


class _Recorder(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        self._answer()

    def do_POST(self) -> None:
        self.rfile.read(int(self.headers.get("Content-Length") or 0))
        self._answer()

    def _answer(self) -> None:
        self.server.hits.append(self.path)
        self.send_response(200)
        self.send_header("Content-Length", "2")
        self.end_headers()
        self.wfile.write(b"{}")

    def log_message(self, *_args) -> None:
        pass


class _UnixHTTPServer(socketserver.ThreadingMixIn, socketserver.UnixStreamServer):
    daemon_threads = True


@pytest.fixture()
def servers(monkeypatch) -> Iterator[tuple]:
    client = _client()
    # A short dir: AF_UNIX caps a socket path near 104 bytes.
    sock_dir = tempfile.mkdtemp(dir="/tmp", prefix="writ-t-ep-")
    unix = _UnixHTTPServer(f"{sock_dir}/d.sock", _Recorder)
    tcp = ThreadingHTTPServer(("127.0.0.1", 0), _Recorder)
    unix.hits, tcp.hits = [], []
    # shutdown() waits for the next poll; the 0.5 s default cost 1 s per test.
    for server in (unix, tcp):
        threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.05},
                         daemon=True).start()
    monkeypatch.setattr(client, "DEFAULT_SOCKET", unix.server_address)
    for var in ("WRIT_SOCKET", "WRIT_HOST", "WRIT_PORT", "WRIT_SESSION_BASE"):
        monkeypatch.delenv(var, raising=False)
    try:
        yield client, unix, tcp
    finally:
        for server in (unix, tcp):
            server.shutdown()
            server.server_close()
        shutil.rmtree(sock_dir, ignore_errors=True)


def _call(client, entry: str) -> int:
    if entry == "get_json":
        return client.get_json("/health")[0]
    if entry == "post_json":
        return client.post_json("/probe", {"n": 1})[0]
    return client.post_json_outcome("/probe", {"n": 1})[0]


class TestAnotherEndpointSkipsTheDefaultSocket:
    @pytest.mark.parametrize("entry", ENTRIES)
    def test_a_named_port_is_reached_instead_of_the_default_socket(
        self, servers, monkeypatch, entry: str,
    ) -> None:
        client, unix, tcp = servers
        monkeypatch.setenv("WRIT_PORT", str(tcp.server_address[1]))
        assert _call(client, entry) == 200
        assert unix.hits == [], "the call went to the default daemon's socket"
        assert len(tcp.hits) == 1

    def test_a_named_session_base_is_reached_instead_of_the_default_socket(
        self, servers, monkeypatch,
    ) -> None:
        client, unix, tcp = servers
        monkeypatch.setenv("WRIT_SESSION_BASE", f"http://127.0.0.1:{tcp.server_address[1]}")
        assert client.post_json("/probe", {"n": 1})[0] == 200
        assert unix.hits == [], "the call went to the default daemon's socket"
        assert len(tcp.hits) == 1


class TestTheDefaultEndpointKeepsTheSocket:
    def test_no_endpoint_named_uses_the_socket(self, servers) -> None:
        client, unix, tcp = servers
        assert client.get_json("/health")[0] == 200
        assert len(unix.hits) == 1
        assert tcp.hits == []

    def test_a_defaulted_host_and_port_still_use_the_socket(self, servers, monkeypatch) -> None:
        """A daemon started by writ_ensure_server inherits WRIT_HOST=localhost and
        WRIT_PORT=8765, and posts its own auto-feedback through this client."""
        client, unix, tcp = servers
        monkeypatch.setenv("WRIT_HOST", "localhost")
        monkeypatch.setenv("WRIT_PORT", "8765")
        assert client.post_json_outcome("/probe", {"n": 1})[0] == 200
        assert len(unix.hits) == 1
        assert tcp.hits == []


class TestAnExplicitSocketStillWins:
    def test_a_set_socket_beats_a_named_port(self, servers, monkeypatch) -> None:
        """common.sh's first arm: both set means the socket, the port as the fallback."""
        client, unix, tcp = servers
        monkeypatch.setenv("WRIT_SOCKET", unix.server_address)
        monkeypatch.setenv("WRIT_PORT", str(tcp.server_address[1]))
        assert client.post_json("/probe", {"n": 1})[0] == 200
        assert len(unix.hits) == 1
        assert tcp.hits == []

    def test_an_empty_socket_still_means_tcp(self, servers, monkeypatch) -> None:
        """writ-subagent-start.sh passes WRIT_SOCKET="" when its own guard chose TCP."""
        client, unix, tcp = servers
        monkeypatch.setenv("WRIT_SOCKET", "")
        monkeypatch.setenv("WRIT_SESSION_BASE", f"http://127.0.0.1:{tcp.server_address[1]}")
        assert client.post_json("/probe", {"n": 1})[0] == 200
        assert unix.hits == []
        assert len(tcp.hits) == 1
