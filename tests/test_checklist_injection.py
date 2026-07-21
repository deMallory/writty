"""Tests for backward context injection on re-planning.

C9: Backward context injection on re-planning
"""

import json
import os
import subprocess
import tempfile

import pytest

SKILL_DIR = os.path.join(os.path.dirname(__file__), "..")
HELPER = os.path.join(SKILL_DIR, "bin", "lib", "writ-session.py")


def run_session(cmd: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["python3", HELPER] + cmd,
        capture_output=True, text=True, timeout=5,
    )


@pytest.fixture
def session_id():
    import uuid
    sid = f"test-{uuid.uuid4().hex[:12]}"
    yield sid
    path = os.path.join(tempfile.gettempdir(), f"writ-session-{sid}.json")
    if os.path.exists(path):
        os.remove(path)


def read_cache(session_id: str) -> dict:
    result = run_session(["read", session_id])
    return json.loads(result.stdout)


# ── C9: Backward context injection ───────────────────────────────────────────


class TestBackwardContextInjection:

    def test_invalidation_record_contains_failure_evidence(self, session_id):
        run_session(["invalidate-gate", session_id, "phase-a",
                      "--rule", "SEC-UNI-003", "--file", "/tmp/a.php",
                      "--evidence", "toArray() at line 47"])
        cache = read_cache(session_id)
        records = cache["invalidation_history"]["phase-a"]
        assert len(records) == 1
        r = records[0]
        assert r["rule_id"] == "SEC-UNI-003"
        assert r["file"] == "/tmp/a.php"
        assert "toArray()" in r["evidence"]

    def test_includes_plan_hash_in_record(self, session_id):
        run_session(["invalidate-gate", session_id, "phase-a",
                      "--rule", "R1", "--file", "/f.php",
                      "--evidence", "test", "--plan-hash", "deadbeef"])
        cache = read_cache(session_id)
        assert cache["invalidation_history"]["phase-a"][0]["prior_plan_hash"] == "deadbeef"

    def test_includes_cycle_count(self, session_id):
        run_session(["invalidate-gate", session_id, "phase-a",
                      "--rule", "R1", "--file", "/f.php", "--evidence", "c1"])
        run_session(["invalidate-gate", session_id, "phase-a",
                      "--rule", "R2", "--file", "/f.php", "--evidence", "c2"])
        cache = read_cache(session_id)
        records = cache["invalidation_history"]["phase-a"]
        assert records[0]["cycle"] == 1
        assert records[1]["cycle"] == 2

    def test_no_escalation_without_invalidation_history(self, session_id):
        result = run_session(["check-escalation", session_id])
        data = json.loads(result.stdout)
        assert data["needed"] is False
        assert data["gate"] is None

    def test_escalation_blocks_with_diagnosis(self, session_id):
        for _ in range(3):
            run_session(["invalidate-gate", session_id, "phase-a",
                          "--rule", "SAME-001", "--file", "/f.php",
                          "--evidence", "repeated failure"])
        result = run_session(["check-escalation", session_id])
        data = json.loads(result.stdout)
        assert data["needed"] is True
        assert data["diagnosis"] == "same-rule"
        assert data["cycles"] == 3
