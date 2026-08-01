"""Audit P0: the /advance-phase server route must require the gate token.

The CLI cmd_advance_phase validates a token written by auto-approve-gate.sh (which fires
only on a user approval-pattern prompt the agent cannot forge), logging
`agent_self_approval_blocked` on a missing/wrong token. But the SERVER route -- the
daemon-first path that _writ_session and /writ-approve actually use -- advanced on
`confirmation_source` alone with NO token check, so any caller could POST
{"confirmation_source":"tool"} and self-advance its own gate. That is the self-approval hole:
oversight replaced by an honor-system instruction ("Never fabricate approval").

This is an integration test against the live daemon (skips if unreachable). RED before the
route validates the token (a tokenless advance succeeds); GREEN after (tokenless is refused;
a valid token gets past the gate). The token is consumed on a successful advance.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
import uuid

import pytest

# This is a security-integration test of the DEPLOYED daemon's advance-phase route, so it
# targets the interactive daemon on :8765 directly (skips if unreachable). It only writes a
# throwaway token file (gettempdir) and advances a throwaway session id, so it does not
# mutate shared graph/cache state.
SERVER = "http://localhost:8765"


def _server_up() -> bool:
    try:
        with urllib.request.urlopen(f"{SERVER}/health", timeout=2):
            return True
    except (urllib.error.URLError, OSError):
        return False


def _post_advance(session_id: str, body: dict) -> dict:
    req = urllib.request.Request(
        f"{SERVER}/session/{session_id}/advance-phase",
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=5) as resp:
        return json.loads(resp.read())


def _token_path(session_id: str) -> str:
    # Fork policy: see feat/upstream-resync migration (option A). Must match
    # gate_token_path()'s literal "/tmp" (and auto-approve-gate.sh); on macOS
    # tempfile.gettempdir() is /var/folders/..., which the daemon never reads.
    return os.path.join("/tmp", f"writ-gate-token-{session_id}")


class TestAdvancePhaseTokenGate:
    def test_tokenless_advance_is_refused(self):
        """The core security property: no token => no advance, regardless of source."""
        if not _server_up():
            pytest.skip("Writ server unreachable")
        sid = f"selfapproval-{uuid.uuid4().hex[:8]}"
        # Ensure no stray token for this fresh session.
        try:
            os.remove(_token_path(sid))
        except OSError:
            pass
        result = _post_advance(sid, {"confirmation_source": "tool"})
        # Must NOT advance, and must say so via an error mentioning the token.
        assert result.get("advanced") is False or "error" in result, result
        assert "token" in json.dumps(result).lower(), (
            f"a tokenless advance must be refused with a token-related error; got {result}"
        )
        assert "phase" not in result or result.get("advanced") is False, result

    def test_valid_token_passes_the_gate(self):
        """With the gate token present and passed, the request clears the token check
        (it no longer returns the token-refusal error)."""
        if not _server_up():
            pytest.skip("Writ server unreachable")
        sid = f"selfapproval-ok-{uuid.uuid4().hex[:8]}"
        token = uuid.uuid4().hex
        path = _token_path(sid)
        with open(path, "w") as f:
            f.write(token)
        try:
            result = _post_advance(sid, {"confirmation_source": "tool", "token": token})
        finally:
            try:
                os.remove(path)
            except OSError:
                pass
        # Got past the token gate: the response is a normal advance result, not the
        # token-refusal error.
        refused = result.get("advanced") is False and "token" in json.dumps(result).lower()
        assert not refused, f"a valid token must clear the gate; got {result}"
