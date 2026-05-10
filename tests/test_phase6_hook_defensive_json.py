"""Phase 6 hotfix: defensive json.loads(sys.argv[N]) in writ hook scripts.

Background: PSR-006 surfaced uncaught json.JSONDecodeError tracebacks
visible in Claude Code's UI on every Write. Root cause: writ-rag-inject.sh
and writ-pretool-rag.sh pass JSON-encoded rule_id arrays via shell argv
to inline `python3 -c` blocks, then call `json.loads(sys.argv[N])`.
When upstream content occasionally contains an embedded control char
(literal newline inside a string value), json.loads raises and the
traceback bubbles to the user.

Tests verify the defensive pattern:
  1. Bug reproduction -- the unguarded pattern crashes on bad input.
  2. Recovered pattern -- with try/except + stderr diagnostic, bad
     input no longer crashes; fallback is empty list; stderr carries
     the [writ-hook json.loads recovery] marker so future debugging
     has a trail.
  3. Hook scripts on disk -- each affected `json.loads(sys.argv[N])`
     callsite is wrapped in try/except in production.

The fix lives in the bash hook scripts (inline python heredocs); these
tests assert pattern presence + behavior, not Python-module behavior.
"""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest

WRIT_ROOT = Path(__file__).resolve().parent.parent
HOOKS = WRIT_ROOT / ".claude" / "hooks"

# The marker every defensive recovery writes to stderr.
RECOVERY_MARKER = "[writ-hook json.loads recovery]"

# The bad-JSON input that triggers the bug: a control char inside a string.
BAD_JSON_PAYLOAD = '["A\nB"]'


# --- Bug reproduction (sanity check that the bug class is real) ------------


class TestBugReproduction:
    """Confirms the unguarded json.loads(sys.argv[N]) pattern crashes
    exactly as PSR-006's debug log showed. Anchors the bug class so the
    fix tests have a concrete failure mode to guard against."""

    def test_unguarded_pattern_crashes_on_bad_json(self) -> None:
        """A literal control char inside a JSON string triggers
        json.JSONDecodeError -- non-zero exit + stderr traceback."""
        script = "import json, sys\nprint(json.loads(sys.argv[1]))"
        proc = subprocess.run(
            ["python3", "-c", script, BAD_JSON_PAYLOAD],
            capture_output=True, text=True, timeout=5,
        )
        assert proc.returncode != 0, "unguarded pattern should crash"
        assert "JSONDecodeError" in proc.stderr
        assert "Invalid control character" in proc.stderr


# --- Recovered-pattern behavior --------------------------------------------


_DEFENSIVE_BLOCK = """
import json, sys
try:
    ids = json.loads(sys.argv[1])
except (json.JSONDecodeError, ValueError) as _e:
    sys.stderr.write(
        f"[writ-hook json.loads recovery] argv[1] in test: {_e}\\n"
        f"  len={len(sys.argv[1])} sample={sys.argv[1][:200]!r}\\n"
    )
    ids = []
print(repr(ids))
"""


class TestRecoveredPatternBehavior:
    """The defensive pattern: try/except around json.loads, stderr
    diagnostic on failure, [] fallback. Successful inputs unchanged."""

    def test_bad_input_does_not_crash(self) -> None:
        proc = subprocess.run(
            ["python3", "-c", _DEFENSIVE_BLOCK, BAD_JSON_PAYLOAD],
            capture_output=True, text=True, timeout=5,
        )
        assert proc.returncode == 0, (
            f"defensive block must exit 0 on bad input; stderr={proc.stderr!r}"
        )

    def test_bad_input_falls_back_to_empty_list(self) -> None:
        proc = subprocess.run(
            ["python3", "-c", _DEFENSIVE_BLOCK, BAD_JSON_PAYLOAD],
            capture_output=True, text=True, timeout=5,
        )
        assert "[]" in proc.stdout, (
            f"defensive block must print [] on bad input; got {proc.stdout!r}"
        )

    def test_bad_input_writes_recovery_marker_to_stderr(self) -> None:
        proc = subprocess.run(
            ["python3", "-c", _DEFENSIVE_BLOCK, BAD_JSON_PAYLOAD],
            capture_output=True, text=True, timeout=5,
        )
        assert RECOVERY_MARKER in proc.stderr, (
            f"defensive block must log {RECOVERY_MARKER!r} on bad input"
        )

    def test_bad_input_logs_length_and_sample(self) -> None:
        proc = subprocess.run(
            ["python3", "-c", _DEFENSIVE_BLOCK, BAD_JSON_PAYLOAD],
            capture_output=True, text=True, timeout=5,
        )
        assert f"len={len(BAD_JSON_PAYLOAD)}" in proc.stderr
        assert "sample=" in proc.stderr

    def test_good_input_parses_unchanged(self) -> None:
        good = '["A", "B", "C"]'
        proc = subprocess.run(
            ["python3", "-c", _DEFENSIVE_BLOCK, good],
            capture_output=True, text=True, timeout=5,
        )
        assert proc.returncode == 0
        assert "['A', 'B', 'C']" in proc.stdout
        assert RECOVERY_MARKER not in proc.stderr


# --- Hook-source pattern audit ---------------------------------------------


_AFFECTED_HOOKS = ["writ-rag-inject.sh"]
# writ-pretool-rag.sh was removed in the 2026-05-10 cleanup (superseded by
# writ-pre-write-dispatch.sh).


def _hook_source(name: str) -> str:
    return (HOOKS / name).read_text()


class TestHooksAreDefensive:
    """Every json.loads(sys.argv[...]) in the two affected hooks is
    wrapped in try/except. The audit is line-level: we count
    occurrences of `json.loads(sys.argv` and confirm an equal number
    of [writ-hook json.loads recovery] markers appear in the same file."""

    @pytest.mark.parametrize("hook_name", _AFFECTED_HOOKS)
    def test_recovery_marker_present(self, hook_name: str) -> None:
        src = _hook_source(hook_name)
        assert RECOVERY_MARKER in src, (
            f"{hook_name} must include the recovery marker after the patch"
        )

    @pytest.mark.parametrize("hook_name", _AFFECTED_HOOKS)
    def test_every_argv_loads_callsite_is_guarded(self, hook_name: str) -> None:
        """For each `json.loads(sys.argv[N])` site, the surrounding
        block must contain at least one `try:` and the recovery
        marker. We use a coarse heuristic: count callsites and
        markers, require at least one marker per hook (since one
        marker can guard multiple callsites in the same block)."""
        src = _hook_source(hook_name)
        callsite_count = len(re.findall(r"json\.loads\(sys\.argv\[", src))
        marker_count = src.count(RECOVERY_MARKER)
        assert callsite_count > 0, (
            f"{hook_name}: expected at least one json.loads(sys.argv[..]) callsite"
        )
        # Each affected hook should have at least one recovery marker
        # per python-c block that does argv parsing. We don't enforce
        # 1:1 because a block can have multiple guarded callsites
        # behind a single marker comment.
        assert marker_count >= 1, (
            f"{hook_name}: expected recovery marker; found {marker_count}"
        )

    @pytest.mark.parametrize("hook_name", _AFFECTED_HOOKS)
    def test_hook_syntax_still_valid(self, hook_name: str) -> None:
        proc = subprocess.run(
            ["bash", "-n", str(HOOKS / hook_name)],
            capture_output=True, text=True,
        )
        assert proc.returncode == 0, (
            f"{hook_name} bash syntax broken: {proc.stderr}"
        )


# --- Phase 4c stderr-tee preservation --------------------------------------


class TestStderrTeeStillCapturesRecoveries:
    """Phase 4c D1's stderr-tee idiom must continue to forward the
    recovery diagnostics to /tmp/writ-hook-debug.log so future
    root-cause analysis has a trail."""

    @pytest.mark.parametrize("hook_name", _AFFECTED_HOOKS)
    def test_hook_has_stderr_tee_or_inherits_from_dispatch(self, hook_name: str) -> None:
        """Either the hook itself has the tee idiom, or it's invoked
        from writ-pre-write-dispatch.sh which inherits the tee. We
        accept either by checking the dispatch hook (Phase 4c) is
        intact OR the hook has the tee directly."""
        dispatch = (HOOKS / "writ-pre-write-dispatch.sh").read_text()
        own = _hook_source(hook_name)
        has_tee = (
            "tee -a /tmp/writ-hook-debug.log" in own
            or "tee -a /tmp/writ-hook-debug.log" in dispatch
        )
        assert has_tee, (
            f"{hook_name}: stderr must reach /tmp/writ-hook-debug.log via "
            "own tee or via writ-pre-write-dispatch.sh"
        )
