"""One daemon client for python callers: unix socket when it answers, TCP otherwise.

WHY THIS EXISTS. E2a moved the daemon behind a unix socket and taught the bash side
about it via `WRIT_CURL_TRANSPORT`. The census it added then named its own dominant
source, and it was not a curl client at all: `hooks/scripts/writ-statusline.sh` POSTs
`context-percent` from an EMBEDDED python block using `urllib.request`, which is 65 of
the first 71 recorded TCP writes. Two more callers hardcode the URL outright
(`writ_send_escalation_feedback.py`, `writ/session/feedback.py`). No grep over curl
call sites could have found any of them, which is the argument for counting rather
than estimating.

STDLIB ONLY. Callers include a hook that runs under BARE system python3, so requests,
httpx and the unix-socket adapters built on them are unavailable. `http.client`
already speaks HTTP/1.1 over any socket; only `connect` changes.

FAIL-OPEN, ALWAYS. Every caller here is best-effort telemetry or a context refresh: a
status bar must not crash because the daemon is down, and a feedback POST must not
fail a hook. Errors resolve to a status of 0 rather than raising, which is what the
callers already did with their own bare `except`.
"""
from __future__ import annotations

import http.client
import json
import os
import socket
import stat
import urllib.parse

DEFAULT_BASE_URL = "http://localhost:8765"
DEFAULT_SOCKET = os.path.join(
    os.path.expanduser("~"), ".cache", "writ", "run", "writ.sock"
)


class UnixSocketHTTPConnection(http.client.HTTPConnection):
    """HTTP/1.1 over an AF_UNIX socket.

    The Host header stays "localhost": the daemon does not route on it, and a socket
    path is not a valid header value.
    """

    def __init__(self, socket_path: str, timeout: float | None = None) -> None:
        super().__init__("localhost", timeout=timeout)
        self._socket_path = socket_path

    def connect(self) -> None:
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        if self.timeout is not None:
            sock.settimeout(self.timeout)
        sock.connect(self._socket_path)
        self.sock = sock


def socket_available(socket_path: str) -> bool:
    """True when the path is a socket file. NOT whether anything is listening.

    Deliberately cheap: a connect probe on top of the request that follows would
    double the syscalls on the hot path. A socket file whose listener has gone is
    handled by falling back to TCP after the attempt fails, the same way the bash
    side retries on curl's exit 7, rather than by predicting it here.
    """
    if not socket_path:
        return False
    try:
        return stat.S_ISSOCK(os.stat(socket_path).st_mode)
    except OSError:
        return False


def _resolve(socket_path: str | None, base_url: str | None) -> tuple[str, str]:
    """(socket_path, base_url) for one call: the arguments when given, else the env.

    Matches common.sh. WRIT_SOCKET wins when set, even to "": writ-subagent-start.sh
    passes "" to mean "no socket". Otherwise the TCP base is WRIT_SESSION_BASE, else
    WRIT_HOST and WRIT_PORT, and an endpoint other than localhost:8765 turns the default
    socket off: that socket belongs to the default daemon, so a caller naming another one
    (the suite's WRIT_PORT=8799) would silently reach the operator's.

    UNLIKE common.sh, a value EQUAL to the default is not an override. A daemon started
    by writ_ensure_server inherits WRIT_HOST=localhost and WRIT_PORT=8765, and posts its
    own auto-feedback through this client; those calls belong on its socket.
    """
    if base_url is None:
        base_url = os.environ.get("WRIT_SESSION_BASE") or "http://{}:{}".format(
            os.environ.get("WRIT_HOST") or "localhost", os.environ.get("WRIT_PORT") or "8765")
    if socket_path is None:
        socket_path = os.environ.get("WRIT_SOCKET")
    if socket_path is None:
        parsed = urllib.parse.urlsplit(base_url)
        named = (parsed.hostname or "localhost", parsed.port or 8765)
        socket_path = DEFAULT_SOCKET if named == ("localhost", 8765) else ""
    return socket_path, base_url


def _request(
    method: str,
    path: str,
    body: bytes | None,
    socket_path: str,
    base_url: str,
    timeout: float,
) -> tuple[int, str]:
    """Try the socket, then TCP. Returns (status, text); status 0 means neither answered."""
    headers = {"Host": "localhost"}
    if body is not None:
        headers["Content-Type"] = "application/json"

    if socket_available(socket_path):
        conn = UnixSocketHTTPConnection(socket_path, timeout=timeout)
        try:
            conn.request(method, path, body=body, headers=headers)
            response = conn.getresponse()
            return response.status, response.read().decode("utf-8", "replace")
        except OSError:
            # A stale socket file is the ordinary aftermath of a replaced daemon.
            # Fall through to TCP rather than reporting the daemon as down.
            pass
        finally:
            conn.close()

    parsed = urllib.parse.urlsplit(base_url)
    conn = http.client.HTTPConnection(
        parsed.hostname or "localhost", parsed.port or 8765, timeout=timeout
    )
    try:
        conn.request(method, path, body=body, headers={k: v for k, v in headers.items()
                                                       if k != "Host"})
        response = conn.getresponse()
        return response.status, response.read().decode("utf-8", "replace")
    except OSError:
        return 0, ""
    finally:
        conn.close()


def post_json(
    path: str,
    payload: dict,
    socket_path: str | None = None,
    base_url: str | None = None,
    timeout: float = 0.5,
) -> tuple[int, str]:
    """POST `payload` as JSON to `path` (e.g. "/session/abc/context-percent")."""
    return _request(
        "POST", path, json.dumps(payload).encode(),
        *_resolve(socket_path, base_url),
        timeout,
    )


def get_json(
    path: str,
    socket_path: str | None = None,
    base_url: str | None = None,
    timeout: float = 0.5,
) -> tuple[int, str]:
    """GET `path` and return (status, body text)."""
    return _request(
        "GET", path, None,
        *_resolve(socket_path, base_url),
        timeout,
    )


def _attempt_outcome(
    conn: http.client.HTTPConnection, path: str, body: bytes, headers: dict
) -> tuple[int, str, bool]:
    """Connect, then send. A connect failure is (0, "", False); any failure after the
    connection opened is (0, "", True), because the bytes may have reached the peer."""
    try:
        conn.connect()
    except OSError:
        conn.close()
        return 0, "", False
    try:
        conn.request("POST", path, body=body, headers=headers)
        response = conn.getresponse()
        return response.status, response.read().decode("utf-8", "replace"), True
    except OSError:
        return 0, "", True
    finally:
        conn.close()


def post_json_outcome(
    path: str,
    payload: dict,
    socket_path: str | None = None,
    base_url: str | None = None,
    timeout: float = 0.5,
) -> tuple[int, str, bool]:
    """POST `payload` as JSON and return (status, text, delivered).

    Unlike post_json, this separates "could not connect" (delivered False: nothing
    happened server-side, a retry is safe) from "request sent, no answer" (status 0,
    delivered True: the server may have applied it). A connect failure on the socket
    may still try TCP, the stale-socket case; a request that reached the socket is
    never replayed over TCP, so a non-idempotent POST is not applied twice.
    """
    body = json.dumps(payload).encode()
    headers = {"Host": "localhost", "Content-Type": "application/json"}
    socket_path, base_url = _resolve(socket_path, base_url)

    if socket_available(socket_path):
        outcome = _attempt_outcome(
            UnixSocketHTTPConnection(socket_path, timeout=timeout), path, body, headers)
        if outcome[2]:
            return outcome

    parsed = urllib.parse.urlsplit(base_url)
    conn = http.client.HTTPConnection(
        parsed.hostname or "localhost", parsed.port or 8765, timeout=timeout
    )
    return _attempt_outcome(
        conn, path, body, {k: v for k, v in headers.items() if k != "Host"})
