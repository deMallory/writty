"""Wave 1 Cycle 4 S4: pre_write_check must log a friction event on a RAG failure
(fail-open, no longer silent), matching the four sibling branches
(server.py L1020/1077/1113/1161).

writ/server.py's pre_write_check._check RAG branch (~L1939-1940) ends with a
blanket `except Exception: pass` -- no log_friction_event call. RED today:
log_friction_event is never invoked when the RAG pipeline raises.

Per TEST-TDD-001: skeletons approved before implementation.
"""
from __future__ import annotations

import asyncio
from unittest.mock import MagicMock

import writ.server as server
from writ.server import PreWriteCheckRequest, pre_write_check


class TestPreWriteRagFailureLogsAndFailsOpen:
    def test_pre_write_rag_failure_logs_and_fails_open(self, monkeypatch) -> None:
        monkeypatch.setattr(
            server.writ_session, "_read_cache",
            lambda sid: {"mode": "work", "remaining_budget": 1500},
        )
        monkeypatch.setattr(
            server.writ_session, "_can_write_check",
            lambda sid, env, skill, cache=None: {"can_write": True, "reason": None},
        )
        fake_pipeline = MagicMock()
        fake_pipeline.query.side_effect = RuntimeError("pipeline boom")
        monkeypatch.setattr(server, "_pipeline", fake_pipeline)

        calls = []
        monkeypatch.setattr(server, "log_friction_event", lambda **kw: calls.append(kw))

        req = PreWriteCheckRequest(
            session_id="s-rag",
            tool_input={"file_path": "/x/user_login_handler.py"},
            file_path="/x/user_login_handler.py",
            skill_dir="/x",
        )
        result = asyncio.run(pre_write_check(req))

        assert result["decision"] == "allow"  # fail-open preserved
        assert any(c.get("event") == "pre_write_rag_failed" for c in calls), (
            f"RAG failure must emit a pre_write_rag_failed friction event, "
            f"got calls: {calls!r}"
        )
        assert any("pipeline boom" in str(c.get("error", "")) for c in calls), (
            f"the friction event should carry the RAG failure's error message, "
            f"got calls: {calls!r}"
        )

    def test_pre_write_rag_success_does_not_log_failure_event(self, monkeypatch) -> None:
        """Guard: a successful RAG query must not emit pre_write_rag_failed."""
        monkeypatch.setattr(
            server.writ_session, "_read_cache",
            lambda sid: {"mode": "work", "remaining_budget": 1500},
        )
        monkeypatch.setattr(
            server.writ_session, "_can_write_check",
            lambda sid, env, skill, cache=None: {"can_write": True, "reason": None},
        )
        # No pipeline configured -> the RAG branch is skipped entirely
        # (`if _pipeline is not None and file_path`), so no RAG failure is possible.
        monkeypatch.setattr(server, "_pipeline", None)

        calls = []
        monkeypatch.setattr(server, "log_friction_event", lambda **kw: calls.append(kw))

        req = PreWriteCheckRequest(
            session_id="s-rag-ok",
            tool_input={"file_path": "/x/user_login_handler.py"},
            file_path="/x/user_login_handler.py",
            skill_dir="/x",
        )
        result = asyncio.run(pre_write_check(req))

        assert result["decision"] == "allow"
        assert not any(c.get("event") == "pre_write_rag_failed" for c in calls)

    def test_gate_denial_short_circuits_before_rag(self, monkeypatch) -> None:
        """Guard: a gate denial returns before the RAG branch runs at all, so no
        pre_write_rag_failed event fires on that path."""
        monkeypatch.setattr(
            server.writ_session, "_read_cache",
            lambda sid: {"mode": "work", "remaining_budget": 1500, "denial_counts": {}},
        )
        monkeypatch.setattr(
            server.writ_session, "_can_write_check",
            lambda sid, env, skill, cache=None: {"can_write": False, "reason": "gate closed"},
        )
        fake_pipeline = MagicMock()
        fake_pipeline.query.side_effect = RuntimeError("should never be called")
        monkeypatch.setattr(server, "_pipeline", fake_pipeline)

        calls = []
        monkeypatch.setattr(server, "log_friction_event", lambda **kw: calls.append(kw))

        req = PreWriteCheckRequest(
            session_id="s-rag-deny",
            tool_input={"file_path": "/x/user_login_handler.py"},
            file_path="/x/user_login_handler.py",
            skill_dir="/x",
        )
        result = asyncio.run(pre_write_check(req))

        assert result["decision"] == "deny"
        assert not calls
        fake_pipeline.query.assert_not_called()
