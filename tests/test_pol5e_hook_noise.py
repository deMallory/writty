"""POL-5e: silence benign workflow hook-noise in two unrelated hooks.

Issue 1 (validate-rules.sh, PostToolUse): emits "[Writ rule compliance] <summary>"
  + exit 1 even when 0 findings are status=="violated" (only "uncertain" findings).
  Fix: gate the banner + warning-exit on a confirmed-violation count; 0 -> silent exit 0.
Issue 2 (writ-run-pending-tests.sh, Stop): emits "[ENF-TEST-001] N test failure(s)"
  + exit 1 during the testing phase, where RED skeletons are expected. Fix: suppress
  the nag when current_phase == "testing"; keep it elsewhere.

RED until the two hooks are updated.
"""

from __future__ import annotations

import importlib.util
import json
import os
import shutil
import subprocess
import tempfile
import uuid
from pathlib import Path

import pytest

from tests._daemon import _port

SKILL_DIR = Path.home() / ".claude/skills/writ"
VALIDATE_RULES = SKILL_DIR / "hooks" / "scripts" / "validate-rules.sh"
RUN_PENDING = SKILL_DIR / "hooks" / "scripts" / "writ-run-pending-tests.sh"
WRIT_SESSION_PY = str(SKILL_DIR / "bin" / "lib" / "writ-session.py")
VENV_BIN = SKILL_DIR / ".venv" / "bin"

VALIDATE_SRC = VALIDATE_RULES.read_text()
RUNPENDING_SRC = RUN_PENDING.read_text()


def _load_writ_session():
    spec = importlib.util.spec_from_file_location("writ_session_5e", WRIT_SESSION_PY)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _server_up() -> bool:
    try:
        import urllib.request

        with urllib.request.urlopen(f"http://localhost:{_port()}/health", timeout=1) as r:
            return r.status == 200
    except Exception:
        return False


requires_server = pytest.mark.skipif(not _server_up(), reason="writ server not running")


# --------------------------------------------------------------------------- #
# Issue 1 -- validate-rules.sh: source-shape (the violation-count gate)
# --------------------------------------------------------------------------- #
class TestValidateRulesGate:
    def test_violated_count_gate_exists(self) -> None:
        assert "VIOLATED_COUNT" in VALIDATE_SRC, (
            "validate-rules.sh must count confirmed (status=='violated') findings"
        )
        assert "-gt 0" in VALIDATE_SRC, "the gate must compare the violation count"

    def test_banner_computed_after_gate(self) -> None:
        gate = VALIDATE_SRC.find("VIOLATED_COUNT")
        banner = VALIDATE_SRC.find("[Writ rule compliance]")
        assert gate != -1 and banner != -1, "both the gate and the banner must exist"
        assert gate < banner, "the violation-count gate must precede the compliance banner"

    def test_warning_exit_conditioned(self) -> None:
        assert "WARN_EXIT" in VALIDATE_SRC, (
            "the warning-mode exits must use a violation-count-conditioned code, "
            "not a bare `exit 1`"
        )
        assert ('exit "$WARN_EXIT"' in VALIDATE_SRC) or ("exit $WARN_EXIT" in VALIDATE_SRC)


# --------------------------------------------------------------------------- #
# Issue 1 -- behavioral parity: a benign edit stays silent + exit 0
# --------------------------------------------------------------------------- #
@requires_server
class TestValidateRulesParity:
    def test_benign_edit_no_banner(self, tmp_path) -> None:
        mod = _load_writ_session()
        sid = f"test-5e-vr-{uuid.uuid4().hex[:8]}"
        cache = mod._read_cache(sid)
        cache.update(mode="work")
        mod._write_cache(sid, cache)
        f = tmp_path / "benign.py"
        f.write_text("x = 1\n")
        try:
            r = subprocess.run(
                ["bash", str(VALIDATE_RULES)],
                input=json.dumps({
                    "session_id": sid, "hook_event_name": "PostToolUse",
                    "tool_name": "Edit", "tool_input": {"file_path": str(f)},
                }),
                capture_output=True, text=True, cwd=str(SKILL_DIR),
                env={**os.environ, "WRIT_HOST": "localhost"}, timeout=30,
            )
            assert r.returncode == 0, f"exit {r.returncode}; stderr={r.stderr[:300]!r}"
            assert "[Writ rule compliance]" not in r.stderr, (
                f"benign edit must not emit the compliance banner; stderr={r.stderr[:300]!r}"
            )
        finally:
            p = Path(tempfile.gettempdir()) / f"writ-session-{sid}.json"
            if p.exists():
                p.unlink()


# --------------------------------------------------------------------------- #
# Issue 2 -- writ-run-pending-tests.sh: phase gate (source-shape + behavioral)
# --------------------------------------------------------------------------- #
class TestRunPendingTestsPhaseGateShape:
    def test_reads_phase_and_gates_on_testing(self) -> None:
        assert "current-phase" in RUNPENDING_SRC, (
            "the Stop hook must read the session phase"
        )
        assert "testing" in RUNPENDING_SRC, (
            "the Stop hook must gate the failure nag on the testing phase"
        )


@requires_server
class TestRunPendingTestsBehavior:
    @pytest.fixture()
    def failing_env(self):
        mod = _load_writ_session()
        sid = f"test-5e-rpt-{uuid.uuid4().hex[:8]}"
        # Created at runtime (after pytest collection) so the current run does not
        # collect it; the hook's `pytest <file>` subprocess runs + fails it.
        test_file = SKILL_DIR / "tests" / f"test_pol5e_tmpfail_{uuid.uuid4().hex[:8]}.py"
        test_file.write_text("def test_pol5e_intentional_fail():\n    assert False\n")
        cache_dir = SKILL_DIR / "cache" / sid
        marker = cache_dir / "pending-tests.txt"

        def seed_phase(phase: str) -> None:
            cache = mod._read_cache(sid)
            cache.update(mode="work", current_phase=phase)
            mod._write_cache(sid, cache)

        def write_marker() -> None:
            cache_dir.mkdir(parents=True, exist_ok=True)
            marker.write_text(str(test_file) + "\n")

        yield sid, seed_phase, write_marker

        test_file.unlink(missing_ok=True)
        shutil.rmtree(cache_dir, ignore_errors=True)
        p = Path(tempfile.gettempdir()) / f"writ-session-{sid}.json"
        if p.exists():
            p.unlink()

    def _run(self, sid: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            ["bash", str(RUN_PENDING)],
            input=json.dumps({"session_id": sid}),
            capture_output=True, text=True, cwd=str(SKILL_DIR),
            env={
                **os.environ, "WRIT_HOST": "localhost",
                "PATH": f"{VENV_BIN}:{os.environ.get('PATH', '')}",
            },
            timeout=90,
        )

    def test_testing_phase_suppresses_nag(self, failing_env) -> None:
        sid, seed_phase, write_marker = failing_env
        seed_phase("testing")
        write_marker()
        r = self._run(sid)
        combined = r.stdout + r.stderr
        assert r.returncode == 0, f"exit {r.returncode}; out={combined[:400]!r}"
        assert "ENF-TEST-001" not in combined, (
            f"testing-phase RED tests must not surface as a Stop error; out={combined[:400]!r}"
        )
        assert "test failure" not in combined

    def test_implementation_phase_still_nags(self, failing_env) -> None:
        sid, seed_phase, write_marker = failing_env
        seed_phase("implementation")
        write_marker()
        r = self._run(sid)
        combined = (r.stdout + r.stderr).lower()
        assert "enf-test-001" in combined or "test failure" in combined, (
            f"failures outside the testing phase must still nag; out={combined[:400]!r}"
        )
        assert r.returncode == 1
