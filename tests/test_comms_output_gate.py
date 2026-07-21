"""Comms output gate hook tests.

Exercises hooks/scripts/writ-comms-output-gate.sh (does NOT exist yet -- all
subprocess calls will fail to find the script -> RED for the right reason).

This is a Stop hook. The hook receives a Stop event JSON on stdin:
  { "transcript_path": "<path>", "stop_hook_active": false, "session_id": "..." }

The hook reads the LAST assistant message from the transcript file at
transcript_path, strips code spans (fenced and inline), and exits 1 with a
stderr message if the prose contains an em dash (—), en dash (–), or " -- "
(space hyphen hyphen space). Exits 0 otherwise.

Contract summary:
- exit 1 + "em dash" in stderr  when em dash found in prose
- exit 1                         when en dash found in prose
- exit 1                         when " -- " found in prose
- exit 0                         when prose is clean
- exit 0                         when the violation is ONLY inside a code span
- exit 0                         when stop_hook_active=true (loop guard)
- exit 0                         when transcript_path is missing or empty (fail-open)
- exit 0                         when only a prior assistant message has a violation
                                 and the LAST assistant message is clean
"""
from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest

SKILL_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
HOOK = os.path.join(SKILL_ROOT, "hooks", "scripts", "writ-comms-output-gate.sh")

_SESSION_ID = "test-comms-output-gate"


def _make_assistant_line(text: str) -> str:
    """Return a JSONL line representing a CC assistant message with the given text."""
    entry = {
        "type": "assistant",
        "message": {
            "content": [
                {"type": "text", "text": text},
            ]
        },
    }
    return json.dumps(entry)


def _write_transcript(
    tmp_path: Path,
    response_text: str,
    prior_assistant: str | None = None,
    name: str = "transcript.jsonl",
) -> Path:
    """Write a minimal transcript JSONL file.

    Optionally prepend a prior assistant line before the final response_text
    line, so tests can verify only the LAST assistant line is scanned.
    """
    lines: list[str] = []
    # A harmless non-assistant line so the file is not trivially empty.
    lines.append(json.dumps({"type": "human", "message": "hello"}))
    if prior_assistant is not None:
        lines.append(_make_assistant_line(prior_assistant))
    lines.append(_make_assistant_line(response_text))
    transcript = tmp_path / name
    transcript.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return transcript


def _run(
    response_text: str,
    *,
    stop_hook_active: bool = False,
    transcript_path: str | None = None,
    prior_assistant: str | None = None,
    tmp_path: Path | None = None,
) -> subprocess.CompletedProcess:
    """Invoke the hook with a Stop event JSON on stdin.

    If transcript_path is None (the default), a temporary transcript is written
    using response_text (and optionally prior_assistant) and its path is used.
    Pass transcript_path="" to simulate a missing/empty transcript_path field.
    Pass transcript_path="<nonexistent>" to simulate a nonexistent file.
    tmp_path is required when transcript_path is None.
    """
    if transcript_path is None:
        assert tmp_path is not None, "tmp_path required when transcript_path is None"
        tp = _write_transcript(tmp_path, response_text, prior_assistant=prior_assistant)
        transcript_path = str(tp)

    payload = json.dumps(
        {
            "session_id": _SESSION_ID,
            "stop_hook_active": stop_hook_active,
            "transcript_path": transcript_path,
        }
    )
    env = {
        **os.environ,
        "WRIT_NO_AUTOSTART": "1",
    }
    return subprocess.run(
        ["bash", HOOK],
        input=payload,
        capture_output=True,
        text=True,
        env=env,
        timeout=30,
    )


# ---------------------------------------------------------------------------
# TestEmDashBlocks -- em dash character in prose triggers exit 1
# ---------------------------------------------------------------------------

class TestEmDashBlocks:
    def test_em_dash_in_prose_exits_1(self, tmp_path):
        result = _run(
            "This is the answer—the one you need.",
            tmp_path=tmp_path,
        )
        assert result.returncode == 1, (
            f"Expected exit 1 for em dash in prose; got {result.returncode}. "
            f"stderr={result.stderr!r}"
        )

    def test_em_dash_in_prose_stderr_contains_em_dash_label(self, tmp_path):
        result = _run(
            "Here—is the violation.",
            tmp_path=tmp_path,
        )
        assert result.returncode == 1
        assert "em dash" in result.stderr.lower(), (
            f"Expected 'em dash' in stderr; got: {result.stderr!r}"
        )

    def test_em_dash_in_prose_stderr_is_not_empty(self, tmp_path):
        result = _run(
            "Problem—here.",
            tmp_path=tmp_path,
        )
        assert result.returncode == 1
        assert result.stderr.strip() != "", (
            "Expected non-empty stderr on em dash violation"
        )


# ---------------------------------------------------------------------------
# TestEnDashBlocks -- en dash character in prose triggers exit 1
# ---------------------------------------------------------------------------

class TestEnDashBlocks:
    def test_en_dash_in_prose_exits_1(self, tmp_path):
        result = _run(
            "Pages 10–20 cover this topic.",
            tmp_path=tmp_path,
        )
        assert result.returncode == 1, (
            f"Expected exit 1 for en dash in prose; got {result.returncode}. "
            f"stderr={result.stderr!r}"
        )

    def test_en_dash_in_prose_stderr_is_not_empty(self, tmp_path):
        result = _run(
            "The range 5–8 is affected.",
            tmp_path=tmp_path,
        )
        assert result.returncode == 1
        assert result.stderr.strip() != "", (
            "Expected non-empty stderr on en dash violation"
        )


# ---------------------------------------------------------------------------
# TestDoubleHyphenBlocks -- " -- " in prose triggers exit 1
# ---------------------------------------------------------------------------

class TestDoubleHyphenBlocks:
    def test_double_hyphen_in_prose_exits_1(self, tmp_path):
        result = _run(
            "Use this approach -- it is the best one.",
            tmp_path=tmp_path,
        )
        assert result.returncode == 1, (
            f"Expected exit 1 for ' -- ' in prose; got {result.returncode}. "
            f"stderr={result.stderr!r}"
        )

    def test_double_hyphen_in_prose_stderr_is_not_empty(self, tmp_path):
        result = _run(
            "Do this -- not that.",
            tmp_path=tmp_path,
        )
        assert result.returncode == 1
        assert result.stderr.strip() != "", (
            "Expected non-empty stderr on double-hyphen violation"
        )

    def test_word_joined_hyphens_do_not_trigger(self, tmp_path):
        # A plain hyphen joining words (e.g. "well-known") must NOT trigger.
        result = _run(
            "This is a well-known, oft-cited technique.",
            tmp_path=tmp_path,
        )
        assert result.returncode == 0, (
            f"Word-joining hyphens must not trigger; got {result.returncode}. "
            f"stderr={result.stderr!r}"
        )


# ---------------------------------------------------------------------------
# TestCleanPasses -- well-formed prose exits 0 with empty stderr
# ---------------------------------------------------------------------------

class TestCleanPasses:
    def test_clean_prose_exits_0(self, tmp_path):
        result = _run(
            "Clean reply, no slop: commas, colons; parentheses (like this).",
            tmp_path=tmp_path,
        )
        assert result.returncode == 0, (
            f"Expected exit 0 for clean prose; got {result.returncode}. "
            f"stderr={result.stderr!r}"
        )

    def test_clean_prose_stderr_is_empty(self, tmp_path):
        result = _run(
            "Clean reply, no slop: commas, colons; parentheses (like this).",
            tmp_path=tmp_path,
        )
        assert result.returncode == 0
        assert result.stderr.strip() == "", (
            f"Expected empty stderr for clean prose; got: {result.stderr!r}"
        )

    def test_multiline_clean_prose_exits_0(self, tmp_path):
        text = (
            "First paragraph covers the approach.\n"
            "Second paragraph covers the rationale.\n"
            "No forbidden characters here."
        )
        result = _run(text, tmp_path=tmp_path)
        assert result.returncode == 0, (
            f"Expected exit 0 for multiline clean prose; got {result.returncode}. "
            f"stderr={result.stderr!r}"
        )


# ---------------------------------------------------------------------------
# TestCodeSpansExcluded -- violations inside code spans do NOT trigger
# ---------------------------------------------------------------------------

class TestCodeSpansExcluded:
    def test_em_dash_only_inside_fenced_block_exits_0(self, tmp_path):
        # The em dash is entirely within a fenced code block and must be stripped
        # before scanning. Exit 0.
        text = (
            "Here is an example:\n"
            "```\n"
            "comment — this is inside a code fence\n"
            "```\n"
            "No em dash in prose."
        )
        result = _run(text, tmp_path=tmp_path)
        assert result.returncode == 0, (
            f"Expected exit 0: em dash only inside fenced block; "
            f"got {result.returncode}. stderr={result.stderr!r}"
        )

    def test_double_hyphen_only_inside_inline_code_exits_0(self, tmp_path):
        # " -- " is entirely within an inline code span. Exit 0.
        text = "Run `git checkout -- file` to restore the file."
        result = _run(text, tmp_path=tmp_path)
        assert result.returncode == 0, (
            f"Expected exit 0: ' -- ' only inside inline code span; "
            f"got {result.returncode}. stderr={result.stderr!r}"
        )

    def test_em_dash_in_prose_plus_code_fence_triggers(self, tmp_path):
        # Em dash in prose AND in code: the prose one must still trigger.
        text = (
            "The result—see below:\n"
            "```\n"
            "also — here\n"
            "```"
        )
        result = _run(text, tmp_path=tmp_path)
        assert result.returncode == 1, (
            f"Expected exit 1: em dash present in prose outside code fence; "
            f"got {result.returncode}. stderr={result.stderr!r}"
        )


# ---------------------------------------------------------------------------
# TestStopHookActiveGuard -- stop_hook_active=true short-circuits to exit 0
# ---------------------------------------------------------------------------

class TestStopHookActiveGuard:
    def test_stop_hook_active_true_with_em_dash_exits_0(self, tmp_path):
        # Even with an em dash in prose, stop_hook_active=true must produce exit 0
        # (loop guard: the hook already fired once, block at most once).
        result = _run(
            "This response—has an em dash.",
            stop_hook_active=True,
            tmp_path=tmp_path,
        )
        assert result.returncode == 0, (
            f"Expected exit 0 when stop_hook_active=true; "
            f"got {result.returncode}. stderr={result.stderr!r}"
        )

    def test_stop_hook_active_false_with_em_dash_still_exits_1(self, tmp_path):
        # Confirm the guard does NOT suppress the check when stop_hook_active=false.
        result = _run(
            "This response—has an em dash.",
            stop_hook_active=False,
            tmp_path=tmp_path,
        )
        assert result.returncode == 1, (
            f"Expected exit 1 when stop_hook_active=false with em dash; "
            f"got {result.returncode}. stderr={result.stderr!r}"
        )


# ---------------------------------------------------------------------------
# TestFailOpen -- missing / empty transcript_path produces exit 0
# ---------------------------------------------------------------------------

class TestFailOpen:
    def test_empty_transcript_path_exits_0(self, tmp_path):
        # transcript_path="" in the payload: hook must fail-open (exit 0).
        result = _run(
            "irrelevant text",
            transcript_path="",
            tmp_path=tmp_path,
        )
        assert result.returncode == 0, (
            f"Expected exit 0 for empty transcript_path; got {result.returncode}. "
            f"stderr={result.stderr!r}"
        )

    def test_nonexistent_transcript_path_exits_0(self, tmp_path):
        # transcript_path pointing to a file that does not exist: fail-open.
        nonexistent = str(tmp_path / "does_not_exist.jsonl")
        result = _run(
            "irrelevant text",
            transcript_path=nonexistent,
            tmp_path=tmp_path,
        )
        assert result.returncode == 0, (
            f"Expected exit 0 for nonexistent transcript_path; "
            f"got {result.returncode}. stderr={result.stderr!r}"
        )


# ---------------------------------------------------------------------------
# TestOnlyLastAssistantScanned -- only the LAST assistant line matters
# ---------------------------------------------------------------------------

class TestOnlyLastAssistantScanned:
    def test_em_dash_in_prior_line_clean_last_exits_0(self, tmp_path):
        # A prior assistant line contains an em dash; the LAST assistant line is
        # clean. The hook must exit 0 (only the last line is scanned).
        result = _run(
            "This final response is clean, no slop here.",
            prior_assistant="This earlier message—had an em dash.",
            tmp_path=tmp_path,
        )
        assert result.returncode == 0, (
            f"Expected exit 0: em dash only in a prior assistant line, last is clean; "
            f"got {result.returncode}. stderr={result.stderr!r}"
        )

    def test_em_dash_in_both_prior_and_last_exits_1(self, tmp_path):
        # Both a prior and the last assistant line have em dashes; must still exit 1.
        result = _run(
            "This final message—also bad.",
            prior_assistant="Earlier—also bad.",
            tmp_path=tmp_path,
        )
        assert result.returncode == 1, (
            f"Expected exit 1: em dash in last assistant line; "
            f"got {result.returncode}. stderr={result.stderr!r}"
        )
