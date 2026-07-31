"""B2: parsed_field / parsed_bool are jq-first (with a python3 fallback) so the
hot per-prompt/per-write hooks pay ~1-2ms (jq) instead of ~10ms (python3 cold
start) per scalar JSON extraction.

This guards the EQUIVALENCE invariant: the jq path and the python3-fallback path
(forced via WRIT_NO_JQ=1) must produce byte-identical output across strings,
numbers, missing keys (-> default), null (-> default), and booleans. A divergence
here would silently change hook behavior, so it is the gate for the perf change.
"""
from __future__ import annotations

import shlex
import subprocess
from pathlib import Path

import pytest

COMMON_SH = str(Path(__file__).resolve().parent.parent / "bin/lib/common.sh")


def _field(json: str, field: str, default: str = "", *, no_jq: bool = False) -> str:
    # Wrap in $(...) exactly as real callers do (X=$(parsed_field ...)) so the
    # trailing newline both jq -r and python print() emit is stripped identically.
    env = "WRIT_NO_JQ=1 " if no_jq else ""
    script = (
        f'source {shlex.quote(COMMON_SH)}; '
        f'printf "%s" "$({env}parsed_field {shlex.quote(json)} {shlex.quote(field)} {shlex.quote(default)})"'
    )
    return subprocess.run(["bash", "-c", script], capture_output=True, text=True, timeout=10).stdout


def _is_true(json: str, field: str, *, no_jq: bool = False) -> bool:
    # parsed_bool's contract: exit 0 iff the field is JSON true; ANY non-zero
    # (false, missing, or invalid JSON) means not-true. Test the contract, not the
    # exact code (jq returns 5 on parse error, the python fallback returns 1).
    env = "WRIT_NO_JQ=1 " if no_jq else ""
    script = (
        f'source {shlex.quote(COMMON_SH)}; '
        f'{env}parsed_bool {shlex.quote(json)} {shlex.quote(field)}'
    )
    return subprocess.run(["bash", "-c", script], capture_output=True, text=True, timeout=10).returncode == 0


FIELD_CASES = [
    ('{"x":"hello"}', "x", "", "hello"),
    ('{"x":"hello world"}', "x", "", "hello world"),
    ('{}', "x", "dflt", "dflt"),
    ('{"x":null}', "x", "dflt", "dflt"),
    ('{"n":42}', "n", "", "42"),
    ('{"mode":"work"}', "mode", "", "work"),
    ('{"remaining_budget":8000}', "remaining_budget", "0", "8000"),
    ('not json at all', "x", "fb", "fb"),
]


class TestParsedFieldJqParity:
    @pytest.mark.parametrize("js,field,default,expected", FIELD_CASES)
    def test_jq_path_correct(self, js, field, default, expected):
        assert _field(js, field, default) == expected

    @pytest.mark.parametrize("js,field,default,expected", FIELD_CASES)
    def test_python_fallback_correct(self, js, field, default, expected):
        assert _field(js, field, default, no_jq=True) == expected

    @pytest.mark.parametrize("js,field,default,expected", FIELD_CASES)
    def test_jq_equals_python(self, js, field, default, expected):
        assert _field(js, field, default) == _field(js, field, default, no_jq=True)


BOOL_CASES = [
    ('{"b":true}', "b", True),
    ('{"b":false}', "b", False),
    ('{}', "b", False),
    ('{"b":null}', "b", False),
    ('{"is_orchestrator":true}', "is_orchestrator", True),
    ('not json', "b", False),
]


class TestParsedBoolJqParity:
    @pytest.mark.parametrize("js,field,expect_true", BOOL_CASES)
    def test_jq_path(self, js, field, expect_true):
        assert _is_true(js, field) == expect_true

    @pytest.mark.parametrize("js,field,expect_true", BOOL_CASES)
    def test_python_fallback(self, js, field, expect_true):
        assert _is_true(js, field, no_jq=True) == expect_true

    @pytest.mark.parametrize("js,field,expect_true", BOOL_CASES)
    def test_jq_equals_python(self, js, field, expect_true):
        assert _is_true(js, field) == _is_true(js, field, no_jq=True)
