"""The gate token expires (writ/session/gate_token.py).

A rejected artifact no longer spends the token (see test_advance_gate_validation_parity),
so an unspent token could otherwise sit in /tmp indefinitely and authorize a later,
unrelated advance. `read_gate_token` treats a file older than WRIT_GATE_TOKEN_TTL
seconds (default 900) as absent and removes it. Single source: the route and the CLI
both read through it.
"""
from __future__ import annotations

import importlib
import os
import sys
import time
import uuid

SKILL_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))


def _imp(name):
    if SKILL_ROOT not in sys.path:
        sys.path.insert(0, SKILL_ROOT)
    return importlib.import_module(name)


def _mint(sid: str, age_seconds: float = 0.0) -> str:
    gt = _imp("writ.session.gate_token")
    path = gt.gate_token_path(sid)
    with open(path, "w") as f:
        f.write("tok-" + sid)
    if age_seconds:
        past = time.time() - age_seconds
        os.utime(path, (past, past))
    return path


class TestGateTokenTtl:
    def test_fresh_token_is_returned(self):
        gt = _imp("writ.session.gate_token")
        sid = f"ttl-{uuid.uuid4().hex[:8]}"
        _mint(sid)
        try:
            assert gt.read_gate_token(sid) == "tok-" + sid
        finally:
            gt.consume_gate_token(sid)

    def test_expired_token_reads_as_absent_and_is_removed(self):
        gt = _imp("writ.session.gate_token")
        sid = f"ttl-{uuid.uuid4().hex[:8]}"
        path = _mint(sid, age_seconds=gt.DEFAULT_TOKEN_TTL_SECONDS + 60)
        assert gt.read_gate_token(sid) == ""
        assert not os.path.exists(path), "an expired token must be removed, not left claimable"

    def test_ttl_env_override(self, monkeypatch):
        gt = _imp("writ.session.gate_token")
        sid = f"ttl-{uuid.uuid4().hex[:8]}"
        monkeypatch.setenv("WRIT_GATE_TOKEN_TTL", "5")
        _mint(sid, age_seconds=10)
        assert gt.read_gate_token(sid) == ""

    def test_default_ttl_is_fifteen_minutes(self):
        gt = _imp("writ.session.gate_token")
        assert gt.DEFAULT_TOKEN_TTL_SECONDS == 900
