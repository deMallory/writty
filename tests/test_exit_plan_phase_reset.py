"""ExitPlanMode resets the task's phase to `planning`.

Context: at the start of a Phase 6j follow-on session, current_phase
carried over from the prior task's `implementation`. The agent's
/advance-phase on the user's "approved" then advanced to `complete`,
silently consuming the new task's first approval. The advance-phase
reject (commit 33e0adc) closes the from-`complete` half of the bug;
this commit closes the other half by treating successful ExitPlanMode
as the canonical "fresh plan = fresh task" signal.

Two contracts pinned:

1. `writ-session.py update <sid> --reset-task-phase` resets
   current_phase to "planning" and clears gates_approved, regardless
   of prior phase.

2. `.claude/hooks/validate-exit-plan.sh` invokes that reset on the
   success path (structural test on the hook source).
"""

from __future__ import annotations

import json
import os
import subprocess
import sys

import pytest

SKILL_DIR = "/home/lucio.saldivar/.claude/skills/writ"
WRIT_SESSION_PY = f"{SKILL_DIR}/bin/lib/writ-session.py"
EXIT_PLAN_HOOK = f"{SKILL_DIR}/.claude/hooks/validate-exit-plan.sh"


def _seed_cache(cache_dir: str, session_id: str, payload: dict) -> str:
    base = {
        "loaded_rule_ids": [],
        "loaded_rules": [],
        "remaining_budget": 8000,
        "context_percent": 0,
        "queries": 0,
        "mode": "work",
        "is_subagent": False,
        "files_written": [],
        "loaded_rule_ids_by_phase": {},
        "current_phase": "implementation",
        "gates_approved": ["phase-a", "phase-test-skeletons"],
        "phase_transitions": [],
    }
    base.update(payload)
    path = os.path.join(cache_dir, f"writ-session-{session_id}.json")
    with open(path, "w") as f:
        json.dump(base, f)
    return path


def _run_session(cache_dir: str, *args: str) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["WRIT_CACHE_DIR"] = cache_dir
    return subprocess.run(
        [sys.executable, WRIT_SESSION_PY, *args],
        capture_output=True,
        text=True,
        env=env,
    )


class TestResetTaskPhaseFlag:
    """`update --reset-task-phase` is the new primitive for the
    fresh-task transition. Mutates current_phase to planning and
    clears gates_approved, leaves everything else untouched."""

    @pytest.mark.parametrize(
        "prior_phase",
        ["implementation", "testing", "complete", "planning"],
    )
    def test_reset_from_any_phase_lands_on_planning(
        self, tmp_path, prior_phase
    ) -> None:
        sid = f"reset-{prior_phase}"
        _seed_cache(str(tmp_path), sid, {"current_phase": prior_phase})

        r = _run_session(str(tmp_path), "update", sid, "--reset-task-phase")
        assert r.returncode == 0, r.stderr

        read = _run_session(str(tmp_path), "read", sid)
        cache = json.loads(read.stdout)
        assert cache["current_phase"] == "planning"
        assert cache["gates_approved"] == []

    def test_reset_preserves_other_state(self, tmp_path) -> None:
        """The reset must not clobber loaded_rule_ids, queries,
        remaining_budget, etc. Only current_phase and gates_approved
        change."""
        sid = "reset-preserves"
        _seed_cache(
            str(tmp_path),
            sid,
            {
                "current_phase": "implementation",
                "loaded_rule_ids": ["A", "B", "C"],
                "queries": 42,
                "remaining_budget": 1234,
                "files_written": ["foo.py"],
            },
        )

        r = _run_session(str(tmp_path), "update", sid, "--reset-task-phase")
        assert r.returncode == 0, r.stderr

        read = _run_session(str(tmp_path), "read", sid)
        cache = json.loads(read.stdout)
        assert cache["current_phase"] == "planning"
        assert cache["gates_approved"] == []
        # Untouched:
        assert set(cache["loaded_rule_ids"]) == {"A", "B", "C"}
        assert cache["queries"] == 42
        assert cache["remaining_budget"] == 1234
        assert cache["files_written"] == ["foo.py"]

    def test_reset_emits_phase_transition_audit_entry(
        self, tmp_path
    ) -> None:
        """The reset is a phase change; phase_transitions must record
        it for audit. trigger='exit-plan-reset' (or similar) so Phase 5
        analyzers can distinguish from regular advances."""
        sid = "reset-audit"
        _seed_cache(
            str(tmp_path),
            sid,
            {"current_phase": "complete", "phase_transitions": []},
        )

        r = _run_session(str(tmp_path), "update", sid, "--reset-task-phase")
        assert r.returncode == 0, r.stderr

        read = _run_session(str(tmp_path), "read", sid)
        cache = json.loads(read.stdout)
        transitions = cache.get("phase_transitions", [])
        assert transitions, "expected at least one phase transition entry"
        last = transitions[-1]
        assert last.get("from") == "complete"
        assert last.get("to") == "planning"
        # Audit trigger field present (exact string flexible).
        assert "trigger" in last


class TestValidateExitPlanHookCallsReset:
    """Structural: the hook source must invoke --reset-task-phase on
    the success path. Catches regressions where the reset is
    accidentally removed."""

    def test_hook_invokes_reset_task_phase_on_success(self) -> None:
        with open(EXIT_PLAN_HOOK) as f:
            body = f.read()

        # The reset must appear in the hook AFTER the validation-success
        # branch. Easiest heuristic: --reset-task-phase appears in the
        # body, and the hook references _writ_session update or the
        # session helper for it.
        assert "--reset-task-phase" in body, (
            "validate-exit-plan.sh does not invoke --reset-task-phase; "
            "the ExitPlanMode -> phase reset wiring is missing"
        )
