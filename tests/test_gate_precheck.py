"""A turn that asks for an approval the pending gate would refuse goes back to the model.

At approval a failed check SPENDS the user's token (by design, fbdcec0). Mistty's logs for
2026-10-03 to 10-06 hold at least 7 approvals rejected after the user typed them. The
costliest was a plan whose ## Files names no test file: phase-a passes, the test-skeletons
gate refuses one approval later, and recovery is `replan approved` plus two fresh approvals.

`_gate_precheck` is the pending gate's own validator plus, for phase-a, that one-gate
look-ahead. `writ-gate-precheck.sh` runs it at Stop, only when the reply just written asks
for an approval, so the refusal costs the model one edit instead of costing the user one
approval.

Unit tests call the function in-process; the hook tests run the REAL script as a subprocess
through `tests.firedrill._harness`, as tests/test_plan_draft_check.py does.
"""

from __future__ import annotations

import importlib.util
import json
import os
import sys
from pathlib import Path

import pytest

from tests.firedrill._harness import make_isolation, run_hook, write_cache
from tests.fixtures.session_state import (
    assistant_text_row,
    user_row,
    write_transcript_jsonl,
)
from writ.harness import vibe
from writ.session.locators import plan_md_hash

REPO = Path(__file__).resolve().parent.parent
HOOKS_JSON = REPO / "hooks" / "hooks.json"
BIN_LIB = REPO / "bin" / "lib"
if str(BIN_LIB) not in sys.path:
    sys.path.insert(0, str(BIN_LIB))

SCRIPT = "writ-gate-precheck.sh"
SID = "gate-precheck-1"
ASK = "Plan written: .claude/plans/gate-precheck-1/plan.md. Say approved to proceed."
NO_ASK = "I refactored the parser module."
HEADER = "[Writ: gate precheck]"
TEST_BODY = "def test_service():\n    assert True\n"

_TAIL = """
## Analysis
Implement the thing with care and verify behavior.

## Rules Applied
No matching rules.

## Capabilities
- [ ] the thing works
"""
PLAN_WITH_TEST = ("# Plan: the thing\n\n## Files\n"
                  "- `service.py` (modify) -- implement the thing\n"
                  "- `tests/test_service.py` (create) -- pins the thing\n" + _TAIL)
PLAN_NO_TEST = ("# Plan: the thing\n\n## Files\n"
                "- `service.py` (modify) -- implement the thing\n" + _TAIL)
BROKEN_PLAN = "# Plan: the thing\n\n## Files\n- `service.py` (modify) -- implement the thing\n"


def _write_plan(root: Path, text: str, sid: str = SID) -> Path:
    plan = root / ".claude" / "plans" / sid / "plan.md"
    plan.parent.mkdir(parents=True, exist_ok=True)
    plan.write_text(text)
    return plan.resolve()


def _precheck():
    """Imported per test, so a missing function fails each test instead of collection."""
    from writ.session import approval_workflow

    if not hasattr(approval_workflow, "_gate_precheck"):
        pytest.fail("writ.session.approval_workflow has no _gate_precheck yet")
    return approval_workflow


# --------------------------------------------------------------------------- #
# _gate_precheck, in-process
# --------------------------------------------------------------------------- #
@pytest.fixture
def repo(tmp_path, monkeypatch) -> Path:
    root = tmp_path / "proj"
    (root / ".git").mkdir(parents=True)
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir()
    monkeypatch.setenv("WRIT_CACHE_DIR", str(cache_dir))
    (cache_dir / f"writ-session-{SID}.json").write_text(json.dumps(
        {"mode": "work", "project_root": str(root), "gates_approved": []}))
    return root


class TestPhaseA:
    def test_a_failing_plan_returns_the_validators_error(self, repo):
        mod = _precheck()
        _write_plan(repo, BROKEN_PLAN)

        error = mod._gate_precheck(str(repo), SID, "phase-a")

        assert error is not None
        assert error.startswith("plan.md validation failed")
        assert error == mod._validate_phase_a(str(repo), SID)

    def test_a_valid_plan_with_no_test_file_gets_the_look_ahead_warning(self, repo):
        mod = _precheck()
        plan = _write_plan(repo, PLAN_NO_TEST)
        # The plan passes phase-a itself: the warning is the look-ahead, not the validator.
        assert mod._validate_phase_a(str(repo), SID) is None

        warning = mod._gate_precheck(str(repo), SID, "phase-a")

        assert warning is not None
        assert str(plan) in warning
        assert "names no test file" in warning
        assert "test-skeletons gate" in warning
        assert "manual test approved" in warning

    def test_a_valid_plan_that_names_a_test_file_passes(self, repo):
        # The test file need not exist yet: at phase-a the plan only has to name it.
        mod = _precheck()
        _write_plan(repo, PLAN_WITH_TEST)
        assert not (repo / "tests" / "test_service.py").exists()

        assert mod._gate_precheck(str(repo), SID, "phase-a") is None

    def test_a_live_manual_test_grant_passes_a_plan_with_no_test_file(self, repo):
        import manual_test_grant

        mod = _precheck()
        _write_plan(repo, PLAN_NO_TEST)
        assert manual_test_grant.mint(SID, manual_test_grant.GRANT_PHRASES[0]) is not None
        assert manual_test_grant.active(SID) is not None

        assert mod._gate_precheck(str(repo), SID, "phase-a") is None


class TestOtherGates:
    def test_test_skeletons_delegates_to_its_validator(self, repo):
        mod = _precheck()
        _write_plan(repo, PLAN_WITH_TEST)

        refused = mod._gate_precheck(str(repo), SID, "test-skeletons")

        assert refused is not None
        assert "not on disk" in refused
        assert refused == mod._validate_test_skeletons(str(repo), SID)

    def test_test_skeletons_passes_once_the_named_file_holds_a_test(self, repo):
        mod = _precheck()
        _write_plan(repo, PLAN_WITH_TEST)
        (repo / "tests").mkdir()
        (repo / "tests" / "test_service.py").write_text(TEST_BODY)

        assert mod._gate_precheck(str(repo), SID, "test-skeletons") is None

    def test_an_unknown_gate_returns_none(self, repo):
        mod = _precheck()
        _write_plan(repo, BROKEN_PLAN)

        assert mod._gate_precheck(str(repo), SID, "final-review") is None


def test_writ_session_re_exports_the_precheck_for_path_loaded_hooks():
    helper = BIN_LIB / "writ-session.py"
    spec = importlib.util.spec_from_file_location("writ_session_precheck", str(helper))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    assert mod._gate_precheck is _precheck()._gate_precheck


# --------------------------------------------------------------------------- #
# writ-gate-precheck.sh, as a subprocess
# --------------------------------------------------------------------------- #
def _iso(tmp_path, plan_text: str, *, mode: str = "work", approved: tuple[str, ...] = ()):
    iso = make_isolation(tmp_path, session_id=SID)
    _write_plan(iso.project_root, plan_text)
    current = plan_md_hash(str(iso.project_root), SID)
    write_cache(iso, {"mode": mode, "project_root": str(iso.project_root),
                      "loaded_rule_ids": [], "gates_approved": list(approved),
                      "gates_approved_plan": {gate: current for gate in approved}})
    return iso


def _stop(message: str | None = ASK, *, transcript: str = "", active: bool = False) -> dict:
    envelope = {"session_id": SID, "hook_event_name": "Stop", "transcript_path": transcript,
                "cwd": "", "stop_hook_active": active}
    if message is not None:
        envelope["last_assistant_message"] = message
    return envelope


def _sent_back(result) -> str:
    assert result.returncode == 2, (result.returncode, result.stderr)
    assert HEADER in result.stderr
    return result.stderr


def _let_through(result) -> None:
    assert result.returncode == 0, (result.returncode, result.stderr)
    assert HEADER not in result.stderr


class TestTheHookSendsTheTurnBack:
    def test_a_request_over_a_plan_phase_a_refuses(self, tmp_path):
        iso = _iso(tmp_path, BROKEN_PLAN)

        reason = _sent_back(run_hook(SCRIPT, _stop(), iso))

        assert "plan.md validation failed" in reason
        assert "## Analysis" in reason

    def test_a_request_over_a_plan_that_names_no_test_file(self, tmp_path):
        iso = _iso(tmp_path, PLAN_NO_TEST)

        reason = _sent_back(run_hook(SCRIPT, _stop(), iso))

        assert "names no test file" in reason

    def test_a_request_with_test_skeletons_pending_and_no_test_on_disk(self, tmp_path):
        iso = _iso(tmp_path, PLAN_WITH_TEST, approved=("phase-a",))

        reason = _sent_back(run_hook(SCRIPT, _stop(), iso))

        assert "not on disk" in reason

    def test_with_no_envelope_message_it_reads_the_transcript(self, tmp_path):
        # Claude Code's path: the request is in the transcript, not the envelope.
        iso = _iso(tmp_path, BROKEN_PLAN)
        transcript = write_transcript_jsonl(tmp_path, [assistant_text_row(ASK)])

        reason = _sent_back(run_hook(SCRIPT, _stop(None, transcript=transcript), iso))

        assert "plan.md validation failed" in reason


class TestTheHookLetsTheTurnEnd:
    def test_a_reply_that_asks_nothing(self, tmp_path):
        iso = _iso(tmp_path, BROKEN_PLAN)
        _let_through(run_hook(SCRIPT, _stop(NO_ASK), iso))

    def test_a_request_from_the_turn_before(self, tmp_path):
        # The reply being judged is not in the transcript yet; the request is last turn's.
        iso = _iso(tmp_path, BROKEN_PLAN)
        transcript = write_transcript_jsonl(
            tmp_path, [assistant_text_row(ASK), user_row("something else")])
        _let_through(run_hook(SCRIPT, _stop(None, transcript=transcript), iso))

    def test_a_request_the_gate_would_accept(self, tmp_path):
        iso = _iso(tmp_path, PLAN_WITH_TEST)
        _let_through(run_hook(SCRIPT, _stop(), iso))

    def test_no_gate_pending(self, tmp_path):
        # Both gates hold for this plan. The named test file is not on disk, so a hook
        # that checked test-skeletons anyway would send the turn back.
        iso = _iso(tmp_path, PLAN_WITH_TEST, approved=("phase-a", "test-skeletons"))
        _let_through(run_hook(SCRIPT, _stop(), iso))

    def test_outside_work_mode(self, tmp_path):
        iso = _iso(tmp_path, BROKEN_PLAN, mode="debug")
        _let_through(run_hook(SCRIPT, _stop(), iso))

    def test_a_continuation_stop(self, tmp_path):
        iso = _iso(tmp_path, BROKEN_PLAN)
        _let_through(run_hook(SCRIPT, _stop(active=True), iso))


class TestRegistration:
    def test_registered_on_stop_for_every_turn(self):
        groups = json.loads(HOOKS_JSON.read_text())["hooks"]["Stop"]
        matchers = [group.get("matcher", "") for group in groups
                    if any(SCRIPT in hook.get("command", "") for hook in group.get("hooks", []))]
        assert matchers == [""]

    def test_the_mistty_bridge_runs_it_on_stop(self):
        config = json.loads(HOOKS_JSON.read_text())
        commands = vibe.select_commands(config, "Stop", "",
                                        default_timeout=vibe.STOP_SCRIPT_TIMEOUT_S)
        assert any(SCRIPT in command for command, _timeout in commands)

    def test_the_script_is_executable_bash(self):
        path = REPO / "hooks" / "scripts" / SCRIPT
        assert path.read_text().startswith("#!/usr/bin/env bash")
        assert os.access(path, os.X_OK)
