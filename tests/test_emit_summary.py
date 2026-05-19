"""Tests for bin/lib/emit-summary.py.

Skeleton: assertions describe expected behavior. Implementation lands in
bin/lib/emit-summary.py per plan.md.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
HELPER = REPO / "bin" / "lib" / "emit-summary.py"


def run_helper(log_path: Path, fmt: str, rule: str = "ENF-POST-007",
               label: str = "findings") -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(HELPER),
         "--format", fmt, "--log", str(log_path),
         "--rule", rule, "--label", label],
        capture_output=True, text=True,
    )


def test_pytest_format_emits_count_and_first_failure(tmp_path):
    log = tmp_path / "pytest.log"
    log.write_text(
        "============================= test session starts =============================\n"
        "FAILED tests/test_foo.py::test_one - AssertionError: 1 != 2\n"
        "E   AssertionError: 1 != 2\n"
        "FAILED tests/test_foo.py::test_two - AssertionError: 3 != 4\n"
    )
    result = run_helper(log, "pytest", rule="ENF-TEST-001", label="test failure(s)")
    assert result.returncode == 0
    assert result.stdout == ""
    assert "[ENF-TEST-001] 2 test failure(s). First:" in result.stderr
    assert "FAILED tests/test_foo.py::test_one" in result.stderr
    assert "AssertionError: 1 != 2" in result.stderr
    assert str(log) in result.stderr


def test_pytest_format_zero_failures_emits_nothing(tmp_path):
    log = tmp_path / "pytest.log"
    log.write_text("============================= 5 passed in 0.04s ==============================\n")
    result = run_helper(log, "pytest")
    assert result.returncode == 0
    assert result.stdout == ""
    assert result.stderr == ""


def test_phpunit_format_emits_count_and_first_failure(tmp_path):
    log = tmp_path / "phpunit.log"
    log.write_text(
        "There were 2 failures:\n\n"
        "1) Tests\\FooTest::testOne\n"
        "Failed asserting that 1 matches expected 2.\n\n"
        "2) Tests\\FooTest::testTwo\n\n"
        "FAILURES!\n"
        "Tests: 2, Assertions: 2, Failures: 2.\n"
    )
    result = run_helper(log, "phpunit", rule="ENF-TEST-001", label="test failure(s)")
    assert result.returncode == 0
    assert "[ENF-TEST-001] 2 test failure(s). First:" in result.stderr
    assert "1) Tests\\FooTest::testOne" in result.stderr


def test_phpunit_warnings_only_no_failures_emits_nothing(tmp_path):
    """PHPUnit can emit numbered warning lists that look like failure lists.
    Without a `FAILURES!` or `ERRORS!` headline, the run is a pass with warnings
    (the Magento Allure / result-cache scenario)."""
    log = tmp_path / "phpunit.log"
    log.write_text(
        ".                                                                   1 / 1 (100%)\n\n"
        "Time: 00:00.005, Memory: 10.00 MB\n\n"
        "There were 2 PHPUnit test runner warnings:\n\n"
        "1) Bootstrapping of extension Allure failed\n"
        "2) Permission denied writing .phpunit.result.cache\n\n"
        "OK, but there were issues!\n"
        "Tests: 1, Assertions: 1, Warnings: 2.\n"
    )
    result = run_helper(log, "phpunit", rule="ENF-TEST-001", label="test failure(s)")
    assert result.returncode == 0
    assert result.stderr == "", \
        f"warnings-only log should produce no summary, got: {result.stderr!r}"


def test_phpunit_errors_headline_still_counts_as_failures(tmp_path):
    log = tmp_path / "phpunit.log"
    log.write_text(
        "There was 1 error:\n\n"
        "1) Tests\\FooTest::testBoom\n"
        "RuntimeException: boom\n\n"
        "ERRORS!\n"
        "Tests: 1, Errors: 1.\n"
    )
    result = run_helper(log, "phpunit", rule="ENF-TEST-001", label="test failure(s)")
    assert result.returncode == 0
    assert "[ENF-TEST-001] 1 test failure(s). First:" in result.stderr
    assert "1) Tests\\FooTest::testBoom" in result.stderr


def test_phpunit_warnings_AND_errors_only_counts_real_errors(tmp_path):
    """The Magento failure case: log has BOTH a warnings section (Allure config,
    result-cache permission) AND a real errors section (test calling a missing
    method). The summarizer must surface only the real errors, not the warnings."""
    log = tmp_path / "phpunit.log"
    log.write_text(
        "EEE                                                                 3 / 3 (100%)\n\n"
        "Time: 00:00.006, Memory: 10.00 MB\n\n"
        "There were 2 PHPUnit test runner warnings:\n\n"
        "1) Bootstrapping of extension Qameta\\Allure\\PHPUnit\\AllureExtension failed: missing config\n"
        "2) Permission denied writing .phpunit.result.cache\n\n"
        "There were 3 errors:\n\n"
        "1) Custom\\Foo\\Test\\Unit\\Block\\ReviewsWidgetTest::testIsVisible_configDisabled_returnsFalse\n"
        "Error: Call to undefined method Custom\\Foo\\Block\\ReviewsWidget::isVisible()\n\n"
        "2) Custom\\Foo\\Test\\Unit\\Block\\ReviewsWidgetTest::testIsVisible_configEnabledButReviewsEmpty_returnsFalse\n"
        "Error: Call to undefined method Custom\\Foo\\Block\\ReviewsWidget::isVisible()\n\n"
        "3) Custom\\Foo\\Test\\Unit\\Block\\ReviewsWidgetTest::testIsVisible_configEnabledAndReviewsPresent_returnsTrue\n"
        "Error: Call to undefined method Custom\\Foo\\Block\\ReviewsWidget::isVisible()\n\n"
        "ERRORS!\n"
        "Tests: 3, Assertions: 0, Errors: 3.\n"
    )
    result = run_helper(log, "phpunit", rule="ENF-TEST-001", label="test failure(s)")
    assert result.returncode == 0
    assert "[ENF-TEST-001] 3 test failure(s). First:" in result.stderr, \
        f"expected 3 errors (not 5: warnings should be excluded), got: {result.stderr!r}"
    # First-finding must be the real error, not the Allure warning.
    assert "ReviewsWidgetTest::testIsVisible_configDisabled_returnsFalse" in result.stderr
    assert "Bootstrapping" not in result.stderr
    assert "Allure" not in result.stderr


def test_gotest_format_emits_count_and_first_failure(tmp_path):
    log = tmp_path / "gotest.log"
    log.write_text(
        "--- FAIL: TestFoo (0.00s)\n"
        "    foo_test.go:12: expected 1, got 2\n"
        "--- FAIL: TestBar (0.00s)\n"
    )
    result = run_helper(log, "gotest", rule="ENF-TEST-001", label="test failure(s)")
    assert result.returncode == 0
    assert "[ENF-TEST-001] 2 test failure(s). First:" in result.stderr
    assert "--- FAIL: TestFoo" in result.stderr


def test_gotest_format_no_failures_emits_nothing(tmp_path):
    log = tmp_path / "gotest.log"
    log.write_text("ok  \tfoo/bar\t0.012s\n")
    result = run_helper(log, "gotest")
    assert result.returncode == 0
    assert result.stderr == ""


def test_json_format_emits_count_and_first_error(tmp_path):
    log = tmp_path / "lint.json"
    log.write_text(json.dumps([
        {"file": "src/foo.py", "line": 12, "severity": "error",
         "tool": "ruff/E501", "message": "line too long"},
        {"file": "src/foo.py", "line": 20, "severity": "error",
         "tool": "ruff/F401", "message": "unused import"},
        {"file": "src/foo.py", "line": 22, "severity": "warning",
         "tool": "ruff/W0612", "message": "advisory"},
    ]))
    result = run_helper(log, "json", rule="ENF-POST-007", label="static-analysis errors")
    assert result.returncode == 0
    assert "[ENF-POST-007] 2 static-analysis errors. First:" in result.stderr
    assert "src/foo.py:12 [ruff/E501] line too long" in result.stderr


def test_json_format_warning_only_emits_nothing(tmp_path):
    log = tmp_path / "lint.json"
    log.write_text(json.dumps([
        {"file": "src/foo.py", "line": 22, "severity": "warning",
         "tool": "ruff/W0612", "message": "advisory"},
    ]))
    result = run_helper(log, "json")
    assert result.returncode == 0
    assert result.stderr == ""


def test_json_format_empty_array_emits_nothing(tmp_path):
    log = tmp_path / "lint.json"
    log.write_text("[]")
    result = run_helper(log, "json")
    assert result.returncode == 0
    assert result.stderr == ""


def test_json_format_malformed_returns_zero_no_traceback(tmp_path):
    log = tmp_path / "lint.json"
    log.write_text("not valid json {{{")
    result = run_helper(log, "json")
    assert result.returncode == 0
    assert "Traceback" not in result.stderr
    assert result.stderr == ""


def test_missing_log_file_emits_nothing(tmp_path):
    log = tmp_path / "does-not-exist.log"
    result = run_helper(log, "pytest")
    assert result.returncode == 0
    assert result.stderr == ""
    assert result.stdout == ""


def test_unknown_format_rejected(tmp_path):
    log = tmp_path / "x.log"
    log.write_text("anything\n")
    result = subprocess.run(
        [sys.executable, str(HELPER),
         "--format", "nonsense", "--log", str(log)],
        capture_output=True, text=True,
    )
    assert result.returncode != 0


def test_format_argument_required(tmp_path):
    log = tmp_path / "x.log"
    log.write_text("anything\n")
    result = subprocess.run(
        [sys.executable, str(HELPER), "--log", str(log)],
        capture_output=True, text=True,
    )
    assert result.returncode != 0


def test_log_argument_required(tmp_path):
    result = subprocess.run(
        [sys.executable, str(HELPER), "--format", "pytest"],
        capture_output=True, text=True,
    )
    assert result.returncode != 0


def test_summary_references_log_path_for_followup_read(tmp_path):
    log = tmp_path / "pytest.log"
    log.write_text("FAILED tests/test_foo.py::test_one - boom\n")
    result = run_helper(log, "pytest")
    assert result.returncode == 0
    assert f"Full log: {log}" in result.stderr
    assert "Read the log only if the first finding does not pinpoint the cause." in result.stderr


def test_stdout_always_empty(tmp_path):
    """Hooks rely on stderr for context injection; stdout must stay clean."""
    log = tmp_path / "pytest.log"
    log.write_text("FAILED tests/test_foo.py::test_one - boom\n")
    result = run_helper(log, "pytest")
    assert result.stdout == ""


def test_exit_code_always_zero_even_on_findings(tmp_path):
    """Caller (hook) decides exit code based on the underlying tool, not the helper."""
    log = tmp_path / "pytest.log"
    log.write_text("FAILED tests/test_foo.py::test_one - boom\n")
    result = run_helper(log, "pytest")
    assert result.returncode == 0
