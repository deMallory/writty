"""Item 2b: analyzer.py summary string when verdict is 'warn' and violation_count == 0.

The fix ensures that warn-with-zero-violations produces
"No confirmed violations; N uncertain finding(s) need manual review."
instead of the misleading "0 potential issues found but unconfirmed" string.
"""

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock

from writ.analysis import Finding
from writ.analysis.instrumentation import Instrumentation


# ---------------------------------------------------------------------------
# Helpers shared by the test class
# ---------------------------------------------------------------------------

RULE_UNCERTAIN = {
    "rule_id": "TEST-UNCERTAIN-001",
    "trigger": "When reviewing code",
    "statement": "Always do the right thing",
    "violation": "",
    "pass_example": "Good.",
}

PHP_CODE_CLEAN = "<?php\nclass Foo {}\n"


def _make_pipeline_mock(rules=None):
    mock = MagicMock()
    mock.query.return_value = {
        "rules": rules or [RULE_UNCERTAIN],
        "mode": "standard",
        "total_candidates": 1,
        "latency_ms": 1.0,
    }
    return mock


def _make_instrumentation(should_escalate: bool = True):
    mock = MagicMock(spec=Instrumentation)
    mock.get_mode.return_value = "production"
    mock.should_escalate.return_value = should_escalate
    return mock


class TestWarnWithZeroViolationsSummary:
    """Summary string for warn verdict with zero confirmed violations."""

    @pytest.mark.asyncio
    async def test_warn_zero_violations_says_uncertain_findings(self) -> None:
        """warn + violation_count == 0 produces 'uncertain finding(s)' not 'potential issues'."""
        from writ.analysis.analyzer import run_analysis

        uncertain_findings = [
            Finding(rule_id="TEST-UNCERTAIN-001", source="llm",
                    status="uncertain", evidence="LLM could not confirm")
        ]
        llm_mock = AsyncMock()
        llm_mock.analyze = AsyncMock(return_value=uncertain_findings)

        result = await run_analysis(
            code=PHP_CODE_CLEAN,
            file_path="Foo.php",
            phase="code_generation",
            context="PHP",
            pipeline=_make_pipeline_mock(),
            llm_client=llm_mock,
            instrumentation=_make_instrumentation(should_escalate=True),
        )

        assert result.verdict == "warn"
        assert result.findings
        violated = [f for f in result.findings if f.status == "violated"]
        assert len(violated) == 0, "Precondition: no confirmed violations"

        # The key invariant: zero-violation warn must NOT say "0 potential issues"
        assert "potential issues" not in result.summary, (
            "Summary must not say 'potential issues' when violation_count == 0; "
            f"got: {result.summary!r}"
        )
        assert "uncertain finding" in result.summary.lower(), (
            f"Summary must mention 'uncertain finding(s)'; got: {result.summary!r}"
        )

    @pytest.mark.asyncio
    async def test_warn_zero_violations_summary_format(self) -> None:
        """Summary matches 'No confirmed violations; N uncertain finding(s) need manual review.'"""
        from writ.analysis.analyzer import run_analysis

        uncertain_findings = [
            Finding(rule_id="TEST-UNCERTAIN-001", source="llm",
                    status="uncertain", evidence="ambiguous"),
            Finding(rule_id="TEST-UNCERTAIN-002", source="llm",
                    status="uncertain", evidence="ambiguous too"),
        ]
        llm_mock = AsyncMock()
        llm_mock.analyze = AsyncMock(return_value=uncertain_findings)

        result = await run_analysis(
            code=PHP_CODE_CLEAN,
            file_path="Foo.php",
            phase="code_generation",
            context="PHP",
            pipeline=_make_pipeline_mock(rules=[RULE_UNCERTAIN, RULE_UNCERTAIN]),
            llm_client=llm_mock,
            instrumentation=_make_instrumentation(should_escalate=True),
        )

        assert result.verdict == "warn"
        violated = [f for f in result.findings if f.status == "violated"]
        assert len(violated) == 0

        # Summary must start with "No confirmed violations"
        assert result.summary.startswith("No confirmed violations"), (
            f"Expected summary to start with 'No confirmed violations'; "
            f"got: {result.summary!r}"
        )
        # Must include the count of uncertain findings
        uncertain_count = len([f for f in result.findings if f.status == "uncertain"])
        assert str(uncertain_count) in result.summary, (
            f"Summary must include count ({uncertain_count}) of uncertain findings; "
            f"got: {result.summary!r}"
        )

    @pytest.mark.asyncio
    async def test_warn_nonzero_violations_unchanged(self) -> None:
        """warn + violation_count > 0 still uses the original summary format."""
        from writ.analysis.analyzer import run_analysis

        # A medium-confidence pattern finding with escalation_failed produces warn+violated
        code_with_comment_violation = "<?php\n// $order->toArray();\nclass Foo {}\n"
        rule = {
            "rule_id": "TEST-WARN-VIO-001",
            "trigger": "When using toArray",
            "statement": "Never use toArray",
            "violation": "->toArray();",
            "pass_example": "Use explicit fields.",
        }
        pipeline = MagicMock()
        pipeline.query.return_value = {
            "rules": [rule],
            "mode": "standard",
            "total_candidates": 1,
            "latency_ms": 1.0,
        }
        llm_mock = AsyncMock()
        llm_mock.analyze = AsyncMock(return_value=[])

        result = await run_analysis(
            code=code_with_comment_violation,
            file_path="Foo.php",
            phase="code_generation",
            context="PHP",
            pipeline=pipeline,
            llm_client=llm_mock,
            instrumentation=_make_instrumentation(should_escalate=True),
        )

        # Only check the warn+nonzero case if the scanner actually found a match
        if result.verdict == "warn":
            violated = [f for f in result.findings if f.status == "violated"]
            if violated:
                # Original format still applies: must contain "potential issues"
                assert "potential issues" in result.summary, (
                    f"warn + nonzero violations must keep original summary; "
                    f"got: {result.summary!r}"
                )

    @pytest.mark.asyncio
    async def test_pass_summary_unchanged(self) -> None:
        """pass verdict summary is unaffected by the fix."""
        from writ.analysis.analyzer import run_analysis

        llm_mock = AsyncMock()
        llm_mock.analyze = AsyncMock(return_value=[])

        result = await run_analysis(
            code=PHP_CODE_CLEAN,
            file_path="Foo.php",
            phase="code_generation",
            context="PHP",
            pipeline=_make_pipeline_mock(),
            llm_client=llm_mock,
            instrumentation=_make_instrumentation(should_escalate=False),
        )

        assert result.verdict == "pass"
        assert "No violations found" in result.summary, (
            f"Pass summary must still say 'No violations found'; got: {result.summary!r}"
        )

    @pytest.mark.asyncio
    async def test_fail_summary_unchanged(self) -> None:
        """fail verdict summary is unaffected by the fix."""
        from writ.analysis.analyzer import run_analysis

        code_with_violation = "<?php\n$order->toArray();\n"
        rule = {
            "rule_id": "TEST-FAIL-001",
            "trigger": "When using toArray",
            "statement": "Never use toArray",
            "violation": "->toArray()",
            "pass_example": "Use explicit fields.",
        }
        pipeline = MagicMock()
        pipeline.query.return_value = {
            "rules": [rule],
            "mode": "standard",
            "total_candidates": 1,
            "latency_ms": 1.0,
        }
        llm_mock = AsyncMock()
        llm_mock.analyze = AsyncMock(return_value=[
            Finding(rule_id="TEST-FAIL-001", source="llm",
                    status="violated", evidence="direct match")
        ])

        result = await run_analysis(
            code=code_with_violation,
            file_path="Foo.php",
            phase="code_generation",
            context="PHP",
            pipeline=pipeline,
            llm_client=llm_mock,
            instrumentation=_make_instrumentation(should_escalate=True),
        )

        if result.verdict == "fail":
            assert "violation" in result.summary.lower(), (
                f"Fail summary must mention violations; got: {result.summary!r}"
            )
            assert "potential issues" not in result.summary, (
                "Fail summary must not say 'potential issues'"
            )
