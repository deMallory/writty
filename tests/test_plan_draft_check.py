"""The phase-a plan check runs when plan.md is written, not only at approval (MTY-20).

At approval a failed check spends the user's token. In mistty session 2709fed0 every
structural slip in plan.md cost one `!mistty approve` round. `writ-validate-plan-draft.sh`
runs the same validator on the write and hands the verdict back as PostToolUse context,
so a slip costs the model one edit instead.

Runs the REAL script as a subprocess through `tests.firedrill._harness`, as
`tests/test_exit_plan_root_resolution.py` does for validate-exit-plan.sh.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from tests.firedrill._harness import make_isolation, run_hook, write_cache
from writ.harness import vibe

REPO = Path(__file__).resolve().parent.parent
HOOKS_JSON = REPO / "hooks" / "hooks.json"
SCRIPT = "writ-validate-plan-draft.sh"
SID = "plan-draft-1"

VALID_PLAN = """\
# Plan: the thing

## Files
- `service.py` (modify) -- implement the thing

## Analysis
Implement the thing with care and verify behavior.

## Rules Applied
- TEST-CI-001: all tests pass before merge.

## Capabilities
- [ ] the thing works
"""

MISSING_SECTIONS = """\
# Plan: the thing

## Files
- `service.py` (modify) -- implement the thing
"""

INVENTED_CITATION = VALID_PLAN.replace("TEST-CI-001", "MADE-UP-999")
PASS_LINE = "[Writ: plan check] plan.md passes the phase-a structure check."


def _iso(tmp_path, *, mode: str = "work"):
    iso = make_isolation(tmp_path, session_id=SID)
    write_cache(iso, {"mode": mode, "loaded_rule_ids": ["TEST-CI-001"], "gates_approved": []})
    return iso


def _scoped_plan(iso) -> Path:
    return (iso.project_root / ".claude" / "plans" / SID / "plan.md").resolve()


def _write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    return path.resolve()


def _envelope(path: Path, *, tool: str = "Write", session_id: str = SID) -> dict:
    tool_input = ({"file_path": str(path), "content": path.read_text()} if tool == "Write"
                  else {"file_path": str(path), "old_string": "a", "new_string": "b"})
    return {"session_id": session_id, "hook_event_name": "PostToolUse", "tool_name": tool,
            "tool_input": tool_input, "tool_response": {"success": True}}


def _context(result) -> str:
    assert result.returncode == 0, result.stderr
    doc = result.stdout_json()
    assert doc is not None, f"no JSON on stdout: {result.stdout!r}"
    hso = doc["hookSpecificOutput"]
    assert hso["hookEventName"] == "PostToolUse"
    return hso["additionalContext"]


def _snapshot(directory: Path) -> dict[str, bytes]:
    # Every instrumented hook appends a timing row to writ-events-<sid>.buf: telemetry,
    # not gate state.
    return {str(p.relative_to(directory)): p.read_bytes()
            for p in sorted(directory.rglob("*"))
            if p.is_file() and not p.name.startswith("writ-events-")}


class TestFailingPlan:
    def test_missing_sections_are_named_in_the_context(self, tmp_path):
        iso = _iso(tmp_path)
        plan = _write(_scoped_plan(iso), MISSING_SECTIONS)

        context = _context(run_hook(SCRIPT, _envelope(plan), iso))

        assert context.startswith("[Writ: plan check] plan.md validation failed")
        for section in ("## Analysis", "## Rules Applied", "## Capabilities"):
            assert section in context, section
        assert "fix it before presenting" in context

    def test_an_invented_rule_id_is_named(self, tmp_path):
        iso = _iso(tmp_path)
        plan = _write(_scoped_plan(iso), INVENTED_CITATION)

        context = _context(run_hook(SCRIPT, _envelope(plan), iso))

        assert "hallucinated rule IDs" in context
        assert "MADE-UP-999" in context

    def test_the_hook_never_decides(self, tmp_path):
        iso = _iso(tmp_path)
        plan = _write(_scoped_plan(iso), MISSING_SECTIONS)

        doc = run_hook(SCRIPT, _envelope(plan), iso).stdout_json()

        assert doc is not None
        assert "decision" not in doc
        assert "permissionDecision" not in doc["hookSpecificOutput"]


class TestPassingPlan:
    def test_a_valid_plan_gets_the_pass_line(self, tmp_path):
        iso = _iso(tmp_path)
        plan = _write(_scoped_plan(iso), VALID_PLAN)

        assert _context(run_hook(SCRIPT, _envelope(plan), iso)) == PASS_LINE


class TestEditRerunsTheCheck:
    def test_an_edit_envelope_runs_the_check(self, tmp_path):
        iso = _iso(tmp_path)
        plan = _write(_scoped_plan(iso), MISSING_SECTIONS)

        context = _context(run_hook(SCRIPT, _envelope(plan, tool="Edit"), iso))

        assert "plan.md validation failed" in context


class TestTheWrongPlanFile:
    def test_a_root_plan_beside_a_session_plan_names_the_one_the_approval_reads(self, tmp_path):
        iso = _iso(tmp_path)
        scoped = _write(_scoped_plan(iso), VALID_PLAN)
        root_plan = _write(iso.project_root / "plan.md", MISSING_SECTIONS)

        context = _context(run_hook(SCRIPT, _envelope(root_plan), iso))

        assert context == (f"[Writ: plan check] The approval reads {scoped}, "
                           f"not {root_plan}. Write the plan there.")


class TestSilentCases:
    def test_outside_work_mode_it_prints_nothing(self, tmp_path):
        iso = _iso(tmp_path, mode="debug")
        plan = _write(_scoped_plan(iso), MISSING_SECTIONS)

        result = run_hook(SCRIPT, _envelope(plan), iso)

        assert result.returncode == 0, result.stderr
        assert result.stdout.strip() == ""

    def test_a_file_not_named_plan_md_prints_nothing(self, tmp_path):
        iso = _iso(tmp_path)
        _write(_scoped_plan(iso), MISSING_SECTIONS)
        other = _write(iso.project_root / "notes.md", "# notes\n")

        result = run_hook(SCRIPT, _envelope(other), iso)

        assert result.returncode == 0, result.stderr
        assert result.stdout.strip() == ""

    def test_no_session_id_prints_nothing(self, tmp_path):
        iso = _iso(tmp_path)
        plan = _write(_scoped_plan(iso), MISSING_SECTIONS)

        result = run_hook(SCRIPT, _envelope(plan, session_id=""), iso)

        assert result.returncode == 0, result.stderr
        assert result.stdout.strip() == ""


class TestNoGateStateChanges:
    def test_a_failing_check_leaves_the_cache_and_gates_untouched(self, tmp_path):
        iso = _iso(tmp_path)
        plan = _write(_scoped_plan(iso), MISSING_SECTIONS)
        before = _snapshot(iso.cache_dir)

        _context(run_hook(SCRIPT, _envelope(plan), iso))

        assert _snapshot(iso.cache_dir) == before
        assert not (iso.project_root / ".claude" / "gates").exists()


class TestRegistration:
    @staticmethod
    def _post_tool_groups() -> list[dict]:
        return json.loads(HOOKS_JSON.read_text())["hooks"]["PostToolUse"]

    @staticmethod
    def _index_of(groups: list[dict], script: str) -> int:
        for i, group in enumerate(groups):
            if any(script in hook.get("command", "") for hook in group.get("hooks", [])):
                return i
        raise AssertionError(f"{script} is not registered on PostToolUse")

    def test_registered_for_every_write_and_edit_tool_name(self):
        groups = self._post_tool_groups()
        matcher = groups[self._index_of(groups, SCRIPT)]["matcher"]
        for tool in ("Write", "Edit", "write", "search_replace"):
            assert re.fullmatch(matcher, tool), tool

    def test_it_runs_before_the_quality_judge(self):
        groups = self._post_tool_groups()
        assert self._index_of(groups, SCRIPT) < self._index_of(groups, "writ-quality-judge.sh")

    def test_the_mistty_bridge_selects_it_for_write_file(self):
        config = json.loads(HOOKS_JSON.read_text())
        commands = vibe.select_commands(config, "PostToolUse", vibe._TOOLS["write_file"])
        assert any(SCRIPT in command for command, _timeout in commands)
