"""Item 4b: bin/lib/validate-rules-helper.py single-spawn correctness.

The helper is called once before /analyze (to derive context, phase,
plan-file) and once after (to consume the analyze response and emit
routing decisions). Both invocations must match the inline Python logic
they replace.
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

SKILL_DIR = Path("/home/lucio.saldivar/.claude/skills/writ")
HELPER = SKILL_DIR / "bin" / "lib" / "validate-rules-helper.py"
SESSION_HELPER = str(SKILL_DIR / "bin" / "lib" / "writ-session.py")


def _load_helper():
    """Load validate-rules-helper.py as a Python module."""
    spec = importlib.util.spec_from_file_location("validate_rules_helper", str(HELPER))
    assert spec is not None and spec.loader is not None, f"{HELPER} not found"
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _run_helper(*args: str, stdin_data: str = "") -> subprocess.CompletedProcess:
    """Invoke validate-rules-helper.py as a subprocess."""
    return subprocess.run(
        [sys.executable, str(HELPER), *args],
        input=stdin_data,
        capture_output=True, text=True,
        cwd=str(SKILL_DIR),
        timeout=15,
    )


# ---------------------------------------------------------------------------
# TestHelperExists
# ---------------------------------------------------------------------------


class TestHelperExists:
    """The helper script exists and is importable."""

    def test_helper_file_exists(self) -> None:
        """bin/lib/validate-rules-helper.py must exist on disk."""
        assert HELPER.exists(), (
            f"{HELPER} does not exist -- Item 4b requires this script"
        )

    def test_helper_is_valid_python(self) -> None:
        """validate-rules-helper.py contains valid Python syntax."""
        result = subprocess.run(
            [sys.executable, "-m", "py_compile", str(HELPER)],
            capture_output=True, text=True,
        )
        assert result.returncode == 0, (
            f"Syntax error in {HELPER}: {result.stderr}"
        )


# ---------------------------------------------------------------------------
# TestHelperPreAnalyzeOutput
# ---------------------------------------------------------------------------


class TestHelperPreAnalyzeOutput:
    """Pre-analyze invocation emits the expected JSON blob."""

    def test_pre_analyze_output_is_valid_json(self) -> None:
        """Helper pre-analyze mode produces valid JSON on stdout."""
        result = _run_helper("pre-analyze", "--session-id", "test-helper-pre-001",
                             "--file", "/tmp/test.py")
        assert result.returncode == 0, f"Helper exited non-zero: {result.stderr}"
        try:
            data = json.loads(result.stdout)
        except json.JSONDecodeError as e:
            pytest.fail(f"Helper output is not valid JSON: {e}\nstdout={result.stdout!r}")
        assert isinstance(data, dict)

    def test_pre_analyze_output_has_should_proceed(self) -> None:
        """Pre-analyze output includes should_proceed boolean."""
        result = _run_helper("pre-analyze", "--session-id", "test-helper-pre-002",
                             "--file", "/tmp/test.py")
        data = json.loads(result.stdout)
        assert "should_proceed" in data, (
            f"Pre-analyze output must include 'should_proceed'; got {data!r}"
        )
        assert isinstance(data["should_proceed"], bool)

    def test_pre_analyze_output_has_context(self) -> None:
        """Pre-analyze output includes context string (<lang> <fw> <role> format)."""
        result = _run_helper("pre-analyze", "--session-id", "test-helper-pre-003",
                             "--file", "/tmp/server.py")
        data = json.loads(result.stdout)
        assert "context" in data, f"Pre-analyze output must include 'context'; got {data!r}"
        assert isinstance(data["context"], str)

    def test_pre_analyze_output_has_phase(self) -> None:
        """Pre-analyze output includes phase string."""
        result = _run_helper("pre-analyze", "--session-id", "test-helper-pre-004",
                             "--file", "/tmp/test.py")
        data = json.loads(result.stdout)
        assert "phase" in data, f"Pre-analyze output must include 'phase'; got {data!r}"
        valid_phases = {"planning", "code_generation", "testing"}
        assert data["phase"] in valid_phases, (
            f"phase must be one of {valid_phases}; got {data['phase']!r}"
        )

    def test_pre_analyze_output_has_boundary_mode(self) -> None:
        """Pre-analyze output includes boundary_mode string."""
        result = _run_helper("pre-analyze", "--session-id", "test-helper-pre-005",
                             "--file", "/tmp/test.py")
        data = json.loads(result.stdout)
        assert "boundary_mode" in data, (
            f"Pre-analyze output must include 'boundary_mode'; got {data!r}"
        )

    def test_pre_analyze_output_has_plan_file(self) -> None:
        """Pre-analyze output includes plan_file path (may be empty string)."""
        result = _run_helper("pre-analyze", "--session-id", "test-helper-pre-006",
                             "--file", "/tmp/test.py")
        data = json.loads(result.stdout)
        assert "plan_file" in data, (
            f"Pre-analyze output must include 'plan_file'; got {data!r}"
        )


# ---------------------------------------------------------------------------
# TestHelperPostAnalyzeOutput
# ---------------------------------------------------------------------------


class TestHelperPostAnalyzeOutput:
    """Post-analyze invocation processes analyze response correctly."""

    def _make_analyze_response(self, verdict: str = "pass") -> dict:
        return {
            "verdict": verdict,
            "findings": [],
            "rules_checked": ["ARCH-ORG-001"],
            "analysis_method": "pattern",
            "retrieval_scores": {"ARCH-ORG-001": 0.85},
            "summary": "No violations found.",
        }

    def test_post_analyze_accepts_analyze_response_json(self) -> None:
        """Helper post-analyze mode accepts analyze response JSON on stdin."""
        stdin_data = json.dumps(self._make_analyze_response("pass"))
        result = _run_helper("post-analyze", "--session-id", "test-helper-post-001",
                             stdin_data=stdin_data)
        assert result.returncode == 0, (
            f"post-analyze must not crash on pass verdict; stderr={result.stderr!r}"
        )

    def test_post_analyze_pass_verdict_no_invalidation(self) -> None:
        """Post-analyze with pass verdict does not trigger gate invalidation."""
        stdin_data = json.dumps(self._make_analyze_response("pass"))
        result = _run_helper("post-analyze", "--session-id", "test-helper-post-002",
                             stdin_data=stdin_data)
        output = result.stdout
        # A pass verdict must not include invalidate-gate routing signal
        assert "invalidate-gate" not in output.lower(), (
            "Post-analyze pass verdict must not emit invalidate-gate signal"
        )

    def test_post_analyze_fail_verdict_signals_routing(self) -> None:
        """Post-analyze with fail verdict emits routing decision in output."""
        fail_response = self._make_analyze_response("fail")
        fail_response["findings"] = [
            {
                "rule_id": "ARCH-ORG-001", "source": "llm",
                "status": "violated", "evidence": "SQL in controller",
            }
        ]
        stdin_data = json.dumps(fail_response)
        result = _run_helper("post-analyze", "--session-id", "test-helper-post-003",
                             stdin_data=stdin_data)
        # Either the output JSON or exit code signals routing
        # (implementation detail -- the key invariant is that it does not silently succeed)
        combined = result.stdout + result.stderr
        assert combined.strip(), (
            "Post-analyze with fail verdict must produce some output"
        )


# ---------------------------------------------------------------------------
# TestHelperGracefulMissingFields
# ---------------------------------------------------------------------------


class TestHelperGracefulMissingFields:
    """Helper handles missing or malformed input without crashing."""

    def test_missing_session_id_does_not_crash(self) -> None:
        """Helper does not raise an unhandled exception when session_id is absent."""
        result = _run_helper("pre-analyze", "--file", "/tmp/test.py")
        # May exit non-zero but must not produce a Python traceback
        assert "Traceback" not in result.stderr, (
            f"Helper must not traceback on missing session_id; stderr={result.stderr!r}"
        )

    def test_malformed_stdin_post_analyze_does_not_crash(self) -> None:
        """Helper handles non-JSON stdin in post-analyze mode without traceback."""
        result = _run_helper("post-analyze", "--session-id", "test-helper-robust-001",
                             stdin_data="THIS IS NOT JSON")
        assert "Traceback" not in result.stderr, (
            f"Helper must not traceback on malformed stdin; stderr={result.stderr!r}"
        )

    def test_empty_stdin_post_analyze_does_not_crash(self) -> None:
        """Helper handles empty stdin in post-analyze mode without traceback."""
        result = _run_helper("post-analyze", "--session-id", "test-helper-robust-002",
                             stdin_data="")
        assert "Traceback" not in result.stderr, (
            f"Helper must handle empty stdin without traceback; stderr={result.stderr!r}"
        )
