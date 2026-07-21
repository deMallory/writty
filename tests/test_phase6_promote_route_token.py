"""Phase 6.3c (security): the /promote-candidate route must require the gate token.

The canon write -- graduating a self-proposed rule into the trusted bible/ source -- is the
one seam where Writ could write its own memory unsupervised. Like /advance-phase, the route
must REFUSE without the agent-unforgeable token that auto-approve-gate.sh writes only on a
genuine user approval prompt. A tokenless promotion is the self-approval hole.

Integration test against the live daemon (skips if unreachable). It targets a NONEXISTENT
candidate on the valid-token path so the gate clears but no real bible/ file is written.
"""
from __future__ import annotations

import json
import os
import tempfile
import urllib.error
import urllib.request
import uuid

import pytest

from tests._daemon import _port

SERVER = f"http://localhost:{_port()}"


def _server_up() -> bool:
    try:
        with urllib.request.urlopen(f"{SERVER}/health", timeout=2):
            return True
    except (urllib.error.URLError, OSError):
        return False


def _post_promote(session_id: str, body: dict) -> dict:
    req = urllib.request.Request(
        f"{SERVER}/session/{session_id}/promote-candidate",
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        return json.loads(resp.read())


def _token_path(session_id: str) -> str:
    return os.path.join(tempfile.gettempdir(), f"writ-gate-token-{session_id}")


class TestPromoteCandidateTokenGate:
    def test_tokenless_promote_is_refused(self) -> None:
        if not _server_up():
            pytest.skip("Writ server unreachable")
        sid = f"promo-noauth-{uuid.uuid4().hex[:8]}"
        try:
            os.remove(_token_path(sid))
        except OSError:
            pass
        result = _post_promote(sid, {"candidate_id": "ZZZ-NOEXIST-001"})
        assert result.get("promoted") is False
        assert "token" in json.dumps(result).lower(), (
            f"a tokenless promotion must be refused with a token error; got {result}"
        )

    def test_valid_token_clears_gate(self) -> None:
        if not _server_up():
            pytest.skip("Writ server unreachable")
        sid = f"promo-ok-{uuid.uuid4().hex[:8]}"
        token = uuid.uuid4().hex
        path = _token_path(sid)
        with open(path, "w") as f:
            f.write(token)
        try:
            # Nonexistent candidate: the request clears the token gate, then promote_candidate
            # returns a not-found error -- proving the refusal was NOT a token refusal and no
            # canon was written.
            result = _post_promote(sid, {"candidate_id": "ZZZ-NOEXIST-001", "token": token})
        finally:
            try:
                os.remove(path)
            except OSError:
                pass
        refused_for_token = "token" in json.dumps(result).lower()
        assert not refused_for_token, f"a valid token must clear the gate; got {result}"
        assert result.get("promoted") is False  # candidate does not exist
