"""RED tests: writ.session.pr_comments.render_commit_notes / write_commit_notes
(Wave 2 Cycle 2, branch refactor/w2-cli-split).

plan.md moves the pr-sync commit-notes helpers out of writ/cli.py's private
`_render_commit_notes` (cli.py:1953-2001) and `_write_commit_notes`
(cli.py:2004-2038) into public functions of the same shape at
writ/session/pr_comments.py:

    async def render_commit_notes(db, host, workspace, repo_slug, project, pr_id) -> dict[str, str]
    def write_commit_notes(repo_root, notes_by_commit) -> int

CRITICAL contract (plan.md "Extraction 2"): `write_commit_notes`'s FIRST
PARAMETER must stay literally named `repo_root` (mirrors the existing
tests/test_cli_pr_sync.py:472-477 inspect.signature check, at the new
location). cli.py keeps top-level re-export aliases
(`_write_commit_notes`, `_render_commit_notes`) and `test_cli_pr_sync.py`
stays UNTOUCHED as the behavior-preserving guardrail at the OLD location.

The move is VERBATIM, so the render_commit_notes test is a parity guard:
its expected {commit_hash: joined_body} dict was captured by IMPORTING AND
RUNNING the CURRENT writ.cli._render_commit_notes (which exists today,
pre-extraction) against the same mocked db/host in this file. Repro
(already run once while authoring this file, .venv/bin/python):

    import asyncio
    from unittest.mock import AsyncMock
    from writ.cli import _render_commit_notes
    result = asyncio.run(_render_commit_notes(db, host, "ws", "slug", "writ", 42))

RED now: `writ.session.pr_comments` has no `render_commit_notes` or
`write_commit_notes` yet (they only exist as the private `_render_commit_notes`
/ `_write_commit_notes` names inside writ/cli.py), so every import below
raises ImportError. Each test performs its own local import (as
tests/test_cli_pr_sync.py does for `_write_commit_notes`) so pytest reports a
distinct, per-test ImportError instead of one whole-module collection error.
GREEN once the implementer moves the two functions to
writ/session/pr_comments.py and extends its `__all__`.

Run: .venv/bin/python -m pytest tests/test_pr_comments_notes.py -v
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

_GIT_AVAILABLE = shutil.which("git") is not None


def _init_repo_with_two_commits(repo_root: Path) -> tuple[str, str]:
    """Create a minimal real git repo with two commits; return (sha1, sha2).

    Used by test_write_commit_notes_writes_notes_in_real_git_repo and
    test_write_commit_notes_skips_bad_commit_continues_others.
    write_commit_notes shells out to real `git notes` / `git push`
    subprocesses with per-commit try/except; a real repo is the most direct
    way to prove that batching contract (ENF-SYS-005: a subprocess.run mock
    can be told to raise/succeed on command, but only a real git object
    database can independently confirm "note attached to a real commit,
    absent on a fake one" without the test just re-asserting its own mock
    setup).
    """
    subprocess.run(["git", "init", "-q", str(repo_root)], check=True)
    subprocess.run(["git", "-C", str(repo_root), "config", "user.email", "test@example.com"], check=True)
    subprocess.run(["git", "-C", str(repo_root), "config", "user.name", "Test"], check=True)

    (repo_root / "a.txt").write_text("one\n")
    subprocess.run(["git", "-C", str(repo_root), "add", "a.txt"], check=True)
    subprocess.run(["git", "-C", str(repo_root), "commit", "-q", "-m", "first commit"], check=True)
    sha1 = subprocess.run(
        ["git", "-C", str(repo_root), "rev-parse", "HEAD"],
        check=True, capture_output=True, text=True,
    ).stdout.strip()

    (repo_root / "b.txt").write_text("two\n")
    subprocess.run(["git", "-C", str(repo_root), "add", "b.txt"], check=True)
    subprocess.run(["git", "-C", str(repo_root), "commit", "-q", "-m", "second commit"], check=True)
    sha2 = subprocess.run(
        ["git", "-C", str(repo_root), "rev-parse", "HEAD"],
        check=True, capture_output=True, text=True,
    ).stdout.strip()

    return sha1, sha2


def _git_note(repo_root: Path, commit_hash: str) -> str | None:
    """Read back the writ-decisions note on `commit_hash`, or None if absent."""
    result = subprocess.run(
        ["git", "-C", str(repo_root), "notes", "--ref=writ-decisions", "show", commit_hash],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        return None
    return result.stdout.rstrip("\n")


# ===========================================================================
# write_commit_notes -- signature contract
# ===========================================================================

class TestWriteCommitNotesSignature:
    def test_write_commit_notes_first_param_is_repo_root(self) -> None:
        # CRITICAL test contract (plan.md): mirrors
        # tests/test_cli_pr_sync.py:472-477's check on writ.cli._write_commit_notes,
        # asserted here at the NEW home so the parameter name survives the move.
        # RED: ImportError -- writ.session.pr_comments has no write_commit_notes yet.
        import inspect

        from writ.session.pr_comments import write_commit_notes

        params = list(inspect.signature(write_commit_notes).parameters)
        assert params[0] == "repo_root", (
            f"write_commit_notes first parameter must be 'repo_root'; got {params[0]!r}"
        )


# ===========================================================================
# write_commit_notes -- real git repo integration (batching + per-commit
# try/except contract)
# ===========================================================================

@pytest.mark.skipif(not _GIT_AVAILABLE, reason="git executable not available")
class TestWriteCommitNotesRealGitRepo:
    """Exercises write_commit_notes against a REAL temporary git repo rather
    than a mocked subprocess.run, per ENF-SYS-005: the claim under test is
    "notes actually land on the right commit object and a bad commit does not
    abort the batch" -- a mocked subprocess.run only proves the function calls
    subprocess.run with the arguments the test told it to expect, not that
    git accepts them. tests/test_cli_pr_sync.py already covers the
    argument-shape contract (exact flags, cwd, refspec) with a mocked
    subprocess.run at the OLD (writ.cli) location; this file complements that
    with real-git behavioral proof at the NEW (pr_comments) location.
    """

    def test_write_commit_notes_writes_notes_in_real_git_repo(self, tmp_path: Path) -> None:
        # RED: ImportError -- writ.session.pr_comments has no write_commit_notes yet.
        from writ.session.pr_comments import write_commit_notes

        repo_root = tmp_path / "repo"
        sha1, sha2 = _init_repo_with_two_commits(repo_root)

        notes = {sha1: "note body one", sha2: "note body two"}
        count = write_commit_notes(str(repo_root), notes)

        assert count == 2, f"expected both notes written; got count={count}"
        assert _git_note(repo_root, sha1) == "note body one"
        assert _git_note(repo_root, sha2) == "note body two"

    def test_write_commit_notes_returns_zero_for_empty_dict(self, tmp_path: Path) -> None:
        # RED: ImportError -- writ.session.pr_comments has no write_commit_notes yet.
        from writ.session.pr_comments import write_commit_notes

        repo_root = tmp_path / "repo"
        _init_repo_with_two_commits(repo_root)

        count = write_commit_notes(str(repo_root), {})

        assert count == 0, f"empty notes_by_commit must write nothing; got count={count}"

    def test_write_commit_notes_skips_bad_commit_continues_others(self, tmp_path: Path) -> None:
        # Per-commit try/except: a nonexistent commit hash makes `git notes add`
        # fail for THAT commit only; the good commit's note is still written and
        # the function returns the count of successful writes, not an exception.
        # RED: ImportError -- writ.session.pr_comments has no write_commit_notes yet.
        from writ.session.pr_comments import write_commit_notes

        repo_root = tmp_path / "repo"
        sha1, _sha2 = _init_repo_with_two_commits(repo_root)
        bad_hash = "deadbeefnotarealcommit000000000000"

        notes = {sha1: "note for the real commit", bad_hash: "note for the bad hash"}
        count = write_commit_notes(str(repo_root), notes)

        assert count == 1, (
            f"one bad commit hash must not abort the batch; the good commit's "
            f"note must still be counted. got count={count}"
        )
        assert _git_note(repo_root, sha1) == "note for the real commit"

    def test_write_commit_notes_rerun_is_idempotent(self, tmp_path: Path) -> None:
        # add -f semantics: a second call with an updated body overwrites the
        # note rather than raising or appending duplicate notes.
        # RED: ImportError -- writ.session.pr_comments has no write_commit_notes yet.
        from writ.session.pr_comments import write_commit_notes

        repo_root = tmp_path / "repo"
        sha1, _sha2 = _init_repo_with_two_commits(repo_root)

        write_commit_notes(str(repo_root), {sha1: "first body"})
        count = write_commit_notes(str(repo_root), {sha1: "second body (updated)"})

        assert count == 1
        assert _git_note(repo_root, sha1) == "second body (updated)"


# ===========================================================================
# render_commit_notes -- parity with the current writ.cli._render_commit_notes
# ===========================================================================

def _diffstat_fixture() -> list[dict]:
    """Diffstat entries covering both accepted shapes: the resolved {path,
    status} form and the raw Bitbucket {new, old, status} form, plus one path
    with no matching FileChange record (must be silently skipped)."""
    return [
        {"path": "a.py", "status": "modified"},
        {"path": "b.py", "status": "added"},
        {"new": {"path": "c.py"}, "old": {}, "status": "added"},
        {"path": "no-record.py", "status": "modified"},
    ]


def _filechange_records_fixture() -> dict[str, dict]:
    """{path: FileChange record} as returned by db.get_latest_filechange_per_path.

    a.py and b.py share commit-aaa (one commit touching two files); c.py is on
    a different commit-bbb with an empty reason (renders the placeholder).
    no-record.py has no entry -- render_commit_notes must skip it, not KeyError.
    """
    return {
        "a.py": {
            "reason": "Extracted friction aggregation to friction.py",
            "change_type": "modified",
            "commit_hash": "commit-aaa",
            "queried_rule_ids": ["SOLID-SRP-002"],
            "cited_rule_ids": ["SOLID-SRP-002", "CLEAN-FUNC-002"],
        },
        "b.py": {
            "reason": "Added pr_comments notes helpers",
            "change_type": "added",
            "commit_hash": "commit-aaa",
            "queried_rule_ids": ["TEST-MOCK-001"],
            "cited_rule_ids": [],
        },
        "c.py": {
            "reason": "",
            "change_type": "added",
            "commit_hash": "commit-bbb",
            "queried_rule_ids": [],
            "cited_rule_ids": ["DRY-DUP-002"],
        },
    }


def _rule_statements_fixture() -> dict[str, str]:
    return {
        "SOLID-SRP-002": "Each module owns one responsibility.",
        "CLEAN-FUNC-002": "Functions do one thing.",
        "TEST-MOCK-001": "Mock the external boundary.",
        "DRY-DUP-002": "Do not duplicate logic.",
    }


def _mock_db_and_host() -> tuple[AsyncMock, AsyncMock]:
    """Fresh db/host doubles wired to the fixtures above, matching the exact
    call pattern _render_commit_notes uses: host.get_pr_diffstat(...) ->
    db.get_latest_filechange_per_path(project, paths) ->
    db.get_rule_statements(all_ids)."""
    db = AsyncMock()
    db.get_latest_filechange_per_path = AsyncMock(return_value=_filechange_records_fixture())
    db.get_rule_statements = AsyncMock(return_value=_rule_statements_fixture())

    host = AsyncMock()
    host.get_pr_diffstat = AsyncMock(return_value=_diffstat_fixture())

    return db, host


# Captured expected value (parity fixture): produced by running the CURRENT
# writ.cli._render_commit_notes(db, host, "ws", "slug", "writ", 42) against
# the exact db/host doubles built by _mock_db_and_host(). Hardcoded rather
# than re-derived so this test can catch a divergence introduced by the move.
EXPECTED_NOTES_BY_COMMIT = {
    "commit-aaa": (
        "**Why this change** -- `a.py` (modified)\n\n"
        "Extracted friction aggregation to friction.py\n\n"
        "**Rules the AI was shown (queried)**\n"
        "- **SOLID-SRP-002** -- Each module owns one responsibility.\n\n"
        "**Rules the AI cited (governing)**\n"
        "- **SOLID-SRP-002** -- Each module owns one responsibility.\n"
        "- **CLEAN-FUNC-002** -- Functions do one thing.\n\n"
        "_Posted by Writ_"
        "\n\n---\n\n"
        "**Why this change** -- `b.py` (added)\n\n"
        "Added pr_comments notes helpers\n\n"
        "**Rules the AI was shown (queried)**\n"
        "- **TEST-MOCK-001** -- Mock the external boundary.\n\n"
        "_Posted by Writ_"
    ),
    "commit-bbb": (
        "**Why this change** -- `c.py` (added)\n\n"
        "No reason recorded\n\n"
        "**Rules the AI cited (governing)**\n"
        "- **DRY-DUP-002** -- Do not duplicate logic.\n\n"
        "_Posted by Writ_"
    ),
}


class TestRenderCommitNotesParity:
    @pytest.mark.asyncio
    async def test_render_commit_notes_matches_current(self) -> None:
        # RED: ImportError -- writ.session.pr_comments has no render_commit_notes yet.
        from writ.session.pr_comments import render_commit_notes

        db, host = _mock_db_and_host()

        result = await render_commit_notes(db, host, "ws", "slug", "writ", 42)

        assert result == EXPECTED_NOTES_BY_COMMIT, (
            f"render_commit_notes output diverges from the captured "
            f"writ.cli._render_commit_notes parity fixture.\ngot={result!r}"
        )

    @pytest.mark.asyncio
    async def test_render_commit_notes_returns_dict_of_str_to_str(self) -> None:
        # Interface contract from plan.md: dict[str, str] keyed by commit hash.
        # RED: ImportError -- writ.session.pr_comments has no render_commit_notes yet.
        from writ.session.pr_comments import render_commit_notes

        db, host = _mock_db_and_host()

        result = await render_commit_notes(db, host, "ws", "slug", "writ", 42)

        assert isinstance(result, dict)
        assert set(result.keys()) == {"commit-aaa", "commit-bbb"}
        for key, value in result.items():
            assert isinstance(key, str)
            assert isinstance(value, str)

    @pytest.mark.asyncio
    async def test_render_commit_notes_skips_path_with_no_filechange_record(self) -> None:
        # no-record.py has no entry in get_latest_filechange_per_path's return;
        # render_commit_notes must skip it silently (no KeyError, no extra commit).
        # RED: ImportError -- writ.session.pr_comments has no render_commit_notes yet.
        from writ.session.pr_comments import render_commit_notes

        db, host = _mock_db_and_host()

        result = await render_commit_notes(db, host, "ws", "slug", "writ", 42)

        assert "no-record.py" not in "".join(result.values()), (
            "a path with no FileChange record must not appear in any note body"
        )

    @pytest.mark.asyncio
    async def test_render_commit_notes_calls_diffstat_and_db_with_expected_args(self) -> None:
        # Parity of the CALL PATTERN, not just the return value: host.get_pr_diffstat
        # is called with (workspace, repo_slug, pr_id); db.get_latest_filechange_per_path
        # is called with (project, normalized_paths); db.get_rule_statements is called
        # with the deduped union of queried+cited rule ids.
        # RED: ImportError -- writ.session.pr_comments has no render_commit_notes yet.
        from writ.session.pr_comments import render_commit_notes

        db, host = _mock_db_and_host()

        await render_commit_notes(db, host, "ws", "slug", "writ", 42)

        host.get_pr_diffstat.assert_awaited_once_with("ws", "slug", 42)
        db.get_latest_filechange_per_path.assert_awaited_once_with(
            "writ", ["a.py", "b.py", "c.py", "no-record.py"]
        )
        db.get_rule_statements.assert_awaited_once_with(
            ["SOLID-SRP-002", "CLEAN-FUNC-002", "TEST-MOCK-001", "DRY-DUP-002"]
        )


# ===========================================================================
# Post-extraction __all__ contract
# ===========================================================================

class TestPrCommentsAllExports:
    def test_new_public_names_are_defined_and_exported(self) -> None:
        # RED now: writ.session.pr_comments currently exposes file_comment_body,
        # find_existing_comment, sync_pr_comments, etc. but not
        # render_commit_notes / write_commit_notes. This import of the *module*
        # succeeds today (it does not name the missing attributes), so this
        # test's RED reason is an AssertionError, not an ImportError --
        # documented separately from the parity tests above, which fail with
        # ImportError.
        import writ.session.pr_comments as pr_comments_mod

        for name in ("render_commit_notes", "write_commit_notes"):
            assert hasattr(pr_comments_mod, name), (
                f"writ.session.pr_comments has no attribute {name!r} yet "
                f"(extraction not landed)"
            )
            assert name in pr_comments_mod.__all__, (
                f"{name!r} must be added to writ.session.pr_comments.__all__"
            )
