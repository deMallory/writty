"""Tests for bin/lib/writ_phase_scoped_rules.py (Wave-3 DRY dedup).

Three hooks currently inline the same "phase-scoped rule-id selection" body
as a `python3 -c` one-liner:

  - hooks/scripts/writ-read-rag.sh:153-162        (guarded: `2>/dev/null || echo '[]'`)
  - hooks/scripts/writ-rag-inject.sh:253-262       (byte-identical to read-rag; sets
                                                     ORCH_LOADED_RULE_IDS; same guard)
  - hooks/scripts/writ-posttool-rag.sh:168-183     (fused with budget/mode on 3 stdout
                                                     lines consumed via `sed -n 'Np'`;
                                                     has its OWN try/except; UNGUARDED)

The planned module extracts the pure selection logic into
`phase_scoped_ids(cache: dict) -> list` plus a stdlib `__main__` block that
reads a cache dict as JSON on stdin and prints the selected rule-id list as
JSON on stdout (no try/except -- malformed input must raise and exit non-zero,
which is what lets the *callers'* existing shell guards keep degrading to
`[]`).

Import style mirrors tests/test_approval_patterns.py (sys.path.insert into
bin/lib, then a plain `from <module> import <fn>`), except the import is
guarded here so a missing module fails each dependent test individually
(clear per-test RED signal) instead of erroring collection for the whole
file -- TestHooksAdoptHelper (source-only, no import needed) must still run
and report its own independent RED reason (hooks not yet adopted).
"""

import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
LIB_DIR = REPO_ROOT / "bin" / "lib"
MODULE_PATH = LIB_DIR / "writ_phase_scoped_rules.py"

HOOKS_DIR = REPO_ROOT / "hooks" / "scripts"
READ_RAG_HOOK = HOOKS_DIR / "writ-read-rag.sh"
RAG_INJECT_HOOK = HOOKS_DIR / "writ-rag-inject.sh"
POSTTOOL_RAG_HOOK = HOOKS_DIR / "writ-posttool-rag.sh"

sys.path.insert(0, str(LIB_DIR))

try:
    from writ_phase_scoped_rules import phase_scoped_ids  # noqa: E402  # RED until module exists
    _IMPORT_ERROR = None
except ImportError as exc:  # RED until module exists
    phase_scoped_ids = None
    _IMPORT_ERROR = exc


def _require_module():
    """Fail the calling test with a clear reason if the module isn't importable yet.

    Used as a setup_method guard so each test in a dependent class reports its
    own RED failure, rather than one opaque collection error for the file.
    """
    if _IMPORT_ERROR is not None:
        pytest.fail(
            f"bin/lib/writ_phase_scoped_rules.py is not importable: {_IMPORT_ERROR!r}"
        )


# The exact HEAD inline body shared (byte-for-byte) by writ-read-rag.sh:153-162
# and writ-rag-inject.sh:253-262, run as `python3 -c HEAD_BODY` with the cache
# JSON piped on stdin. Used as the differential reference in
# TestDifferentialVsHeadInline -- the new module's __main__ path must produce
# byte-identical stdout to this snippet for every well-formed cache shape.
HEAD_BODY = """import sys, json
cache = json.load(sys.stdin)
by_phase = cache.get('loaded_rule_ids_by_phase', {})
current_phase = cache.get('current_phase', '')
if by_phase and current_phase:
    print(json.dumps(by_phase.get(current_phase, [])))
else:
    print(json.dumps(cache.get('loaded_rule_ids', [])))
"""


# Well-formed cache variants shared across TestPhaseScopedIdsFunction (list-type
# check), TestMainStdinStdout, and TestDifferentialVsHeadInline. Excludes the
# malformed-stdin case, which is covered only in TestMainStdinStdout (both the
# new script and HEAD_BODY raise on malformed input, so there is nothing to
# differential-compare there).
CACHE_VARIANTS = [
    pytest.param({}, id="empty_cache"),
    pytest.param({"loaded_rule_ids": ["A", "B"]}, id="flat_list_no_by_phase"),
    pytest.param(
        {
            "loaded_rule_ids_by_phase": {"planning": ["P1", "P2"]},
            "current_phase": "planning",
            "loaded_rule_ids": ["A"],
        },
        id="phase_bucket_matches_current_phase",
    ),
    pytest.param(
        {
            "loaded_rule_ids_by_phase": {"planning": ["P1", "P2"]},
            "current_phase": "",
            "loaded_rule_ids": ["A", "B"],
        },
        id="empty_current_phase_falls_back_to_flat_list",
    ),
    pytest.param(
        {
            "loaded_rule_ids_by_phase": {"planning": ["P1", "P2"]},
            "current_phase": "testing",
        },
        id="current_phase_not_a_key_in_by_phase",
    ),
    pytest.param(
        {
            "loaded_rule_ids_by_phase": {},
            "current_phase": "planning",
            "loaded_rule_ids": ["A", "B"],
        },
        id="empty_by_phase_dict_falls_back_to_flat_list",
    ),
]


# -- 1. Unit tests for the pure function -------------------------------------

class TestPhaseScopedIdsFunction:
    def setup_method(self):
        _require_module()

    def test_empty_cache_returns_empty_list(self):
        assert phase_scoped_ids({}) == []

    def test_flat_loaded_rule_ids_returned_when_no_by_phase_key(self):
        cache = {"loaded_rule_ids": ["A", "B"]}
        assert phase_scoped_ids(cache) == ["A", "B"]

    def test_phase_bucket_wins_over_flat_list_when_current_phase_set(self):
        """THE branch the existing behavioral tests never hit: when both
        loaded_rule_ids_by_phase and current_phase are populated, the
        current phase's bucket is returned instead of the flat
        loaded_rule_ids list, even though the flat list is also present."""
        cache = {
            "loaded_rule_ids_by_phase": {"planning": ["P1", "P2"]},
            "current_phase": "planning",
            "loaded_rule_ids": ["A"],
        }
        assert phase_scoped_ids(cache) == ["P1", "P2"]

    def test_falls_back_to_flat_list_when_current_phase_is_empty_string(self):
        cache = {
            "loaded_rule_ids_by_phase": {"planning": ["P1", "P2"]},
            "current_phase": "",
            "loaded_rule_ids": ["A", "B"],
        }
        assert phase_scoped_ids(cache) == ["A", "B"]

    def test_returns_empty_list_when_current_phase_not_a_key_in_by_phase(self):
        cache = {
            "loaded_rule_ids_by_phase": {"planning": ["P1", "P2"]},
            "current_phase": "testing",
        }
        assert phase_scoped_ids(cache) == []

    def test_falls_back_to_flat_list_when_by_phase_dict_is_empty(self):
        """by_phase = {} is falsy, so the `by_phase and current_phase` guard
        takes the flat-list branch even though current_phase is set."""
        cache = {
            "loaded_rule_ids_by_phase": {},
            "current_phase": "planning",
            "loaded_rule_ids": ["A", "B"],
        }
        assert phase_scoped_ids(cache) == ["A", "B"]

    @pytest.mark.parametrize("cache", CACHE_VARIANTS)
    def test_return_value_is_always_a_list(self, cache):
        assert isinstance(phase_scoped_ids(cache), list)


# -- 2. The CLI path: stdin -> stdout ----------------------------------------

class TestMainStdinStdout:
    def setup_method(self):
        _require_module()

    @staticmethod
    def _run_main(stdin_text):
        return subprocess.run(
            [sys.executable, str(MODULE_PATH)],
            input=stdin_text,
            capture_output=True,
            text=True,
        )

    @pytest.mark.parametrize("cache", CACHE_VARIANTS)
    def test_main_stdout_matches_function_result_and_exits_zero(self, cache):
        result = self._run_main(json.dumps(cache))
        assert result.returncode == 0
        assert json.loads(result.stdout) == phase_scoped_ids(cache)

    def test_malformed_stdin_exits_non_zero(self):
        """No try/except in __main__: malformed JSON must raise and exit
        non-zero. This is the behavior read-rag.sh and rag-inject.sh rely on
        -- their shell guard (`2>/dev/null || echo '[]'`) only degrades to
        `[]` on a genuinely non-zero exit."""
        result = self._run_main("not json{")
        assert result.returncode != 0


# -- 3. Differential test: new module vs. the HEAD inline body --------------

class TestDifferentialVsHeadInline:
    """Proves the new __main__ path is byte-identical to the inline
    `python3 -c` body read-rag.sh and rag-inject.sh run at HEAD, for every
    well-formed cache shape. Does not need the phase_scoped_ids import --
    both sides are exercised purely as subprocesses."""

    @staticmethod
    def _run_new_module(stdin_text):
        return subprocess.run(
            [sys.executable, str(MODULE_PATH)],
            input=stdin_text,
            capture_output=True,
            text=True,
        )

    @staticmethod
    def _run_head_inline(stdin_text):
        return subprocess.run(
            [sys.executable, "-c", HEAD_BODY],
            input=stdin_text,
            capture_output=True,
            text=True,
        )

    @pytest.mark.parametrize("cache", CACHE_VARIANTS)
    def test_new_module_stdout_byte_identical_to_head_inline_body(self, cache):
        stdin_text = json.dumps(cache)
        new_result = self._run_new_module(stdin_text)
        head_result = self._run_head_inline(stdin_text)
        assert new_result.stdout == head_result.stdout


# -- 4. Source guard: hooks adopt the helper, inline body is gone -----------

class TestHooksAdoptHelper:
    """Reads hook source text directly (no subprocess, no import). This
    class does not depend on writ_phase_scoped_rules.py existing, so it
    reports its own independent RED reason: the hooks have not yet been
    repointed at the helper module."""

    def test_read_rag_hook_invokes_helper_script(self):
        content = READ_RAG_HOOK.read_text()
        assert "writ_phase_scoped_rules.py" in content, (
            "writ-read-rag.sh does not invoke writ_phase_scoped_rules.py; "
            "it may still be running the inline python3 -c selection body."
        )

    def test_rag_inject_hook_invokes_helper_script(self):
        content = RAG_INJECT_HOOK.read_text()
        assert "writ_phase_scoped_rules.py" in content, (
            "writ-rag-inject.sh does not invoke writ_phase_scoped_rules.py; "
            "it may still be running the inline python3 -c selection body."
        )

    def test_posttool_rag_hook_imports_phase_scoped_ids_function(self):
        content = POSTTOOL_RAG_HOOK.read_text()
        assert "from writ_phase_scoped_rules import phase_scoped_ids" in content, (
            "writ-posttool-rag.sh does not import phase_scoped_ids from "
            "writ_phase_scoped_rules; it may still be running its own fused "
            "inline python3 -c body."
        )

    def test_read_rag_hook_no_longer_inlines_phase_bucket_selection(self):
        content = READ_RAG_HOOK.read_text()
        assert content.count("by_phase.get(current_phase, [])") == 0, (
            "writ-read-rag.sh still contains the inline phase-bucket "
            "selection line; the logic must live only in the helper module."
        )

    def test_rag_inject_hook_no_longer_inlines_phase_bucket_selection(self):
        content = RAG_INJECT_HOOK.read_text()
        assert content.count("by_phase.get(current_phase, [])") == 0, (
            "writ-rag-inject.sh still contains the inline phase-bucket "
            "selection line; the logic must live only in the helper module."
        )

    def test_posttool_rag_hook_no_longer_inlines_phase_bucket_selection(self):
        content = POSTTOOL_RAG_HOOK.read_text()
        assert content.count("by_phase.get(current_phase, [])") == 0, (
            "writ-posttool-rag.sh still contains the inline phase-bucket "
            "selection line; the logic must live only in the helper module."
        )

    def test_read_rag_hook_preserves_guard_fallback_to_empty_list(self):
        """Guard asymmetry: read-rag.sh must keep degrading to '[]' on
        failure (unlike posttool-rag.sh, which is intentionally unguarded)."""
        content = READ_RAG_HOOK.read_text()
        assert "|| echo '[]'" in content

    def test_rag_inject_hook_preserves_guard_fallback_to_empty_list(self):
        content = RAG_INJECT_HOOK.read_text()
        assert "|| echo '[]'" in content

    def test_posttool_rag_hook_preserves_three_line_sed_consumption(self):
        """posttool-rag.sh's fused shape (rule_ids/budget/mode on 3 stdout
        lines) must remain intact after adoption -- only the selection body
        moves into the module, not the fused 3-line print/consume contract."""
        content = POSTTOOL_RAG_HOOK.read_text()
        assert "sed -n '1p'" in content
        assert "sed -n '2p'" in content
        assert "sed -n '3p'" in content

    def test_rag_inject_hook_preserves_orch_loaded_rule_ids_var_name(self):
        content = RAG_INJECT_HOOK.read_text()
        assert "ORCH_LOADED_RULE_IDS" in content
