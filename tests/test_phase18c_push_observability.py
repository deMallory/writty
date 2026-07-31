"""1.8c: push-by-action observability.

Before 1.8c, a push fired but left NO observable trace: the companion logged no
friction event and the rag_query emit carried no `action`/`channel`. 1.8c closes
that: the writ_action_push helper logs a `methodology_push` friction event
(action + per-channel floor/push/pull counts + rule_ids + tokens), and
`audit-session` tallies a push/channel breakdown. The Exit criterion is that a
fresh-session log shows an event with `action` set, `channel=='push'`, rules>0 --
asserted here against the audit-session consumer (the producer is the bash helper,
verified by live smoke).
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

SKILL_DIR = str(Path(__file__).resolve().parent.parent)
SHIM = f"{SKILL_DIR}/bin/writ"


def _write_log(path: Path, events: list[dict]) -> None:
    with path.open("w") as f:
        for e in events:
            f.write(json.dumps(e) + "\n")


def _events(sid: str) -> list[dict]:
    return [
        {"ts": "2026-06-13T19:00:00Z", "session": sid, "mode": "work",
         "event": "rag_query", "query_source": "broad", "tokens_injected": 400,
         "rules_returned_count": 2, "rule_ids": ["ARCH-TYPE-001", "PY-PYDANTIC-001"]},
        # The push event under test: worktree action delivered 2 push nodes.
        {"ts": "2026-06-13T19:01:00Z", "session": sid, "mode": "work",
         "event": "methodology_push", "action": "worktree",
         "channels": {"floor": 0, "push": 2, "pull": 0},
         "rules_returned_count": 2, "tokens_injected": 80,
         "rule_ids": ["SKL-PROC-WORKTREE-001", "TEC-PROC-WORKTREE-001"]},
        # A second push (different action) -> distinct action tally.
        {"ts": "2026-06-13T19:02:00Z", "session": sid, "mode": "work",
         "event": "methodology_push", "action": "gate-denial",
         "channels": {"floor": 0, "push": 1, "pull": 0},
         "rules_returned_count": 1, "tokens_injected": 40,
         "rule_ids": ["SKL-PROC-WRIT-FAILURE-001"]},
        # Noise: a push from a different session must NOT be counted.
        {"ts": "2026-06-13T19:03:00Z", "session": "OTHER-SESSION", "mode": "work",
         "event": "methodology_push", "action": "finish",
         "channels": {"floor": 0, "push": 1, "pull": 0},
         "rules_returned_count": 1, "tokens_injected": 30, "rule_ids": ["PBK-PROC-FINISH-001"]},
    ]


def _run_json(sid: str, log: Path) -> dict:
    result = subprocess.run(
        [SHIM, "audit-session", sid, "--log", str(log), "--json"],
        capture_output=True, text=True, timeout=15,
    )
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


class TestPushObservability:
    def test_push_by_action_tallied(self, tmp_path: Path) -> None:
        sid = "PUSH-SID-1"
        log = tmp_path / "workflow-friction.log"
        _write_log(log, _events(sid))
        data = _run_json(sid, log)
        assert data["push_by_action"]["worktree"] == 1
        assert data["push_by_action"]["gate-denial"] == 1

    def test_push_channels_tallied(self, tmp_path: Path) -> None:
        # Exit criterion: channel=='push' with rules>0 is observable end to end.
        sid = "PUSH-SID-2"
        log = tmp_path / "workflow-friction.log"
        _write_log(log, _events(sid))
        data = _run_json(sid, log)
        # 2 (worktree) + 1 (gate-denial) push nodes for this session.
        assert data["push_channels"]["push"] == 3

    def test_push_filtered_to_session(self, tmp_path: Path) -> None:
        sid = "PUSH-SID-3"
        log = tmp_path / "workflow-friction.log"
        _write_log(log, _events(sid))
        data = _run_json(sid, log)
        # The OTHER-SESSION 'finish' push must not leak in.
        assert "finish" not in data["push_by_action"]

    def test_push_section_in_text_output(self, tmp_path: Path) -> None:
        sid = "PUSH-SID-4"
        log = tmp_path / "workflow-friction.log"
        _write_log(log, _events(sid))
        result = subprocess.run(
            [SHIM, "audit-session", sid, "--log", str(log)],
            capture_output=True, text=True, timeout=15,
        )
        assert result.returncode == 0
        assert "Push-by-action" in result.stdout
        assert "worktree" in result.stdout
