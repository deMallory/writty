"""The code-quality reviewer can run once the spec reviewer has finished.

Pins every checkbox in capabilities.md, item for item.

writ-sdd-review-order.sh refuses writ-code-quality-reviewer in Work mode until
review_ordering_state[<key>]["spec_reviewer_completed"] is set. Nothing wrote that
flag, so the refusal was permanent. writ-subagent-stop.sh now sets it when a
writ-spec-reviewer stops, and both hooks take the key from review_findings.py.

Imports of the new functions are LOCAL to each test so a missing function fails RED
rather than skipping the file.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import uuid
from pathlib import Path

import pytest

from tests.test_bash_write_gate import SKILL_ROOT, _run_hook, _seed, _session_rows

sys.path.insert(0, os.path.join(SKILL_ROOT, "bin", "lib"))

STOP_HOOK = os.path.join(SKILL_ROOT, "hooks", "scripts", "writ-subagent-stop.sh")
ORDER_GATE = os.path.join(SKILL_ROOT, "hooks", "scripts", "writ-sdd-review-order.sh")


def _sid() -> str:
    return f"review-order-{uuid.uuid4().hex[:8]}"


@pytest.fixture
def cache_dir(tmp_path: Path, monkeypatch) -> Path:
    """Hooks run as subprocesses and inherit os.environ, so one setenv covers the
    test's own cache reads and every hook it runs."""
    monkeypatch.setenv("WRIT_CACHE_DIR", str(tmp_path))
    return tmp_path


def _stop(sid: str, agent_type: str) -> subprocess.CompletedProcess:
    payload = {
        "hook_event_name": "SubagentStop",
        "session_id": sid,
        "agent_id": f"agent-{uuid.uuid4().hex[:6]}",
        "agent_type": agent_type,
        "last_assistant_message": "Spec review done.",
    }
    return subprocess.run(
        ["bash", STOP_HOOK],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        cwd=SKILL_ROOT,
    )


def _dispatch(sid: str, subagent_type: str) -> dict | None:
    """Run the order gate on a Task dispatch. The hookSpecificOutput on a deny, else None."""
    envelope = json.dumps(
        {
            "session_id": sid,
            "tool_name": "Task",
            "tool_input": {
                "subagent_type": subagent_type,
                "description": "Review",
                "prompt": "x",
            },
        }
    )
    p = subprocess.run(
        ["bash", ORDER_GATE],
        input=envelope,
        capture_output=True,
        text=True,
        cwd=SKILL_ROOT,
    )
    out = p.stdout.strip()
    return json.loads(out).get("hookSpecificOutput", {}) if out else None


def _order_state(sid: str) -> dict:
    from writ.session.cache import _read_cache

    return _read_cache(sid).get("review_ordering_state") or {}


# --------------------------------------------------------------------------- #
# 1. The shared key rule
# --------------------------------------------------------------------------- #
class TestReviewOrderKey:
    def test_task_id_wins(self) -> None:
        from review_findings import review_order_key

        assert review_order_key({"active_phase": "PH-1"}, "T-9") == "T-9"

    def test_active_phase_when_no_task_id(self) -> None:
        from review_findings import review_order_key

        assert review_order_key({"active_phase": "PH-1"}, None) == "PH-1"

    def test_default_when_neither(self) -> None:
        from review_findings import review_order_key

        assert review_order_key({"active_phase": None}, None) == "default"

    def test_spec_review_done_reads_the_flag_under_the_key(self) -> None:
        from review_findings import spec_review_done

        cache = {
            "active_phase": "PH-1",
            "review_ordering_state": {"PH-1": {"spec_reviewer_completed": True}},
        }
        assert spec_review_done(cache, None) is True
        assert spec_review_done({"review_ordering_state": {}}, None) is False


# --------------------------------------------------------------------------- #
# 2. Recording: the SubagentStop hook sets the flag
# --------------------------------------------------------------------------- #
class TestSpecReviewerStopSetsFlag:
    @pytest.mark.parametrize(
        "agent_type",
        ["writ-spec-reviewer", "writ:writ-spec-reviewer", "gritty:writ-spec-reviewer"],
    )
    def test_spec_reviewer_stop_sets_the_flag(
        self, agent_type: str, cache_dir: Path
    ) -> None:
        sid = _sid()
        _stop(sid, agent_type)
        assert _order_state(sid)["default"]["spec_reviewer_completed"] is True

    def test_flag_lands_under_active_phase(self, cache_dir: Path) -> None:
        sid = _sid()
        _seed(sid, active_phase="PH-7")
        _stop(sid, "writ-spec-reviewer")
        state = _order_state(sid)
        assert state["PH-7"]["spec_reviewer_completed"] is True
        assert "default" not in state

    @pytest.mark.parametrize(
        "agent_type",
        [
            "writ-implementer",
            "writ-reviewer",
            "writ-code-quality-reviewer",
            "writ-spec-reviewer-extra",
        ],
    )
    def test_other_agent_types_set_nothing(
        self, agent_type: str, cache_dir: Path
    ) -> None:
        sid = _sid()
        _stop(sid, agent_type)
        assert _order_state(sid) == {}

    def test_no_parent_session_sets_nothing(self, cache_dir: Path) -> None:
        payload = {
            "hook_event_name": "SubagentStop",
            "agent_id": "agent-orphan",
            "agent_type": "writ-spec-reviewer",
            "last_assistant_message": "done",
        }
        p = subprocess.run(
            ["bash", STOP_HOOK],
            input=json.dumps(payload),
            capture_output=True,
            text=True,
            cwd=SKILL_ROOT,
        )
        assert p.returncode == 0
        written = [
            f.name
            for f in cache_dir.glob("writ-session-*.json")
            if "review_ordering_state" in f.read_text()
            and '"spec_reviewer_completed"' in f.read_text()
        ]
        assert written == []

    def test_failed_record_is_logged_and_hook_still_exits_0(
        self, cache_dir: Path
    ) -> None:
        """A directory where the parent's cache file belongs makes the write fail."""
        sid = _sid()
        blocker = cache_dir / f"writ-session-{sid}.json"
        blocker.mkdir()
        (blocker / "keep").write_text("x")
        p = _stop(sid, "writ-spec-reviewer")
        assert p.returncode == 0
        assert "review_order_record_failed" in [
            e.get("event") for e in _session_rows(sid)
        ]


# --------------------------------------------------------------------------- #
# 3. The gate, end to end
# --------------------------------------------------------------------------- #
class TestOrderGate:
    @pytest.mark.parametrize(
        "reviewer",
        [
            "writ-code-quality-reviewer",
            "writ:writ-code-quality-reviewer",
            "gritty:writ-code-quality-reviewer",
        ],
    )
    def test_refused_before_spec_review(self, reviewer: str, cache_dir: Path) -> None:
        sid = _sid()
        _seed(sid, mode="work")
        out = _dispatch(sid, reviewer)
        assert out is not None and out.get("permissionDecision") == "deny"

    def test_allowed_after_spec_reviewer_stops(self, cache_dir: Path) -> None:
        sid = _sid()
        _seed(sid, mode="work")
        _stop(sid, "writ-spec-reviewer")
        assert _dispatch(sid, "writ-code-quality-reviewer") is None

    def test_allowed_after_spec_review_under_active_phase(
        self, cache_dir: Path
    ) -> None:
        sid = _sid()
        _seed(sid, mode="work", active_phase="PH-7")
        _stop(sid, "writ-spec-reviewer")
        assert _dispatch(sid, "writ-code-quality-reviewer") is None

    def test_deny_message_names_no_dead_route(self, cache_dir: Path) -> None:
        sid = _sid()
        _seed(sid, mode="work")
        reason = (_dispatch(sid, "writ-code-quality-reviewer") or {}).get(
            "permissionDecisionReason", ""
        )
        assert "writ-spec-reviewer" in reason
        assert "review-ordering" not in reason


# --------------------------------------------------------------------------- #
# 4. Provenance: an agent cannot mark its own spec review done
# --------------------------------------------------------------------------- #
class TestSpecDoneIsGuarded:
    def test_bash_gate_refuses_spec_done(self, cache_dir: Path) -> None:
        sid = _sid()
        _seed(sid, mode="work")
        out = _run_hook(
            f"python3 bin/lib/review_findings.py spec-done {sid}", sid, str(cache_dir)
        )
        assert out is not None and out.get("permissionDecision") == "deny"
