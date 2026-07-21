"""Phase 1f: git-notes per-commit log -- CLI tests for the _write_commit_notes block.

Test skeleton for the capability gate defined in capabilities.md and plan.md.
Every test in this file is RED until the implementer adds the git-notes block
to writ/cli.py pr_sync.

Tests use mocked subprocess.run so no real git repo or remote is needed.
The db and host doubles are minimal; only the git-notes subprocess calls and
their arguments are under test here.

Run interpreter: .venv/bin/python -m pytest (has onnxruntime; system python3
errors on embedding imports).

Capability map (items from plan.md / capabilities.md):
  [1f-cli-notes-1]  pr_sync writes exactly one `git notes --ref=writ-decisions add -f`
                    per distinct commit_hash
  [1f-cli-notes-2]  each commit note body contains the file_comment_body output
                    for that commit's changed paths
  [1f-cli-notes-3]  pr_sync pushes notes with
                    refs/notes/writ-decisions:refs/notes/writ-decisions refspec
  [1f-cli-notes-4]  every git subprocess call uses cwd=repo_root
  [1f-cli-notes-5]  re-running pr_sync is idempotent for notes (uses -f, overwrites)
  [1f-cli-notes-6]  a git-notes push CalledProcessError logs a warning and does NOT
                    raise out of pr_sync (offline/perms must not abort the sync)
  [1f-cli-notes-7]  a per-note write CalledProcessError skips that note and does NOT
                    raise; other notes continue to be written

ENF-SYS-005 note: the git-notes subprocess contract (correct args, cwd, refspec) is
the behavior under test. subprocess.run is mocked because the test does not need a
real git repo -- the assertions are on the call arguments, not on git output.
"""

from __future__ import annotations

import subprocess
from typing import Any
from unittest.mock import MagicMock, call, patch

import pytest


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_REPO_ROOT = "/tmp/fake-1f-notes-repo"
_WRIT_DECISIONS_REF = "refs/notes/writ-decisions:refs/notes/writ-decisions"


# ---------------------------------------------------------------------------
# Minimal stubs for _write_commit_notes tests
# (These tests target the module-level helper, NOT the full pr_sync CLI flow,
# to isolate the git-notes subprocess contract without wiring up the full
# typer CLI + async DB stack.)
# ---------------------------------------------------------------------------

def _notes_by_commit_factory(
    commit_hash: str = "deadbeef01",
    body: str = "note body for deadbeef01",
) -> dict[str, str]:
    """Minimal {commit_hash: note_body} dict for _write_commit_notes tests."""
    return {commit_hash: body}


def _completed(returncode: int = 0, stdout: str = "", stderr: str = "") -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess(
        args=[], returncode=returncode, stdout=stdout, stderr=stderr,
    )


# ===========================================================================
# _write_commit_notes unit tests (mock subprocess.run directly)
# ===========================================================================

class TestWriteCommitNotes:
    """Caps [1f-cli-notes-1] through [1f-cli-notes-7].

    Tests target the _write_commit_notes helper directly so the git-notes
    subprocess contract can be verified without the full CLI stack.

    RED: writ.cli._write_commit_notes does not yet exist (ImportError /
    AttributeError). After the implement phase adds it to cli.py, these
    tests turn GREEN.
    """

    def _import(self):
        """Import _write_commit_notes from writ.cli.
        RED: ImportError / AttributeError until the function is written."""
        from writ.cli import _write_commit_notes
        return _write_commit_notes

    def test_writes_one_git_note_per_distinct_commit_hash(self) -> None:
        # [1f-cli-notes-1]: exactly one `git notes --ref=writ-decisions add -f`
        # call per distinct commit_hash.
        # RED: _write_commit_notes does not exist (ImportError).
        _write_commit_notes = self._import()

        notes = {
            "commit-aaa": "body for aaa",
            "commit-bbb": "body for bbb",
        }
        with patch("subprocess.run", return_value=_completed(0)) as mock_run:
            count = _write_commit_notes(_REPO_ROOT, notes)

        add_calls = [
            c for c in mock_run.call_args_list
            if "add" in (c.args[0] if c.args else c.kwargs.get("args", []))
            or any("add" in str(a) for a in (c.args[0] if c.args else []))
        ]
        # More precisely: filter for calls that include "writ-decisions" and "add" and "-f".
        note_add_calls = [
            c for c in mock_run.call_args_list
            if c.args and isinstance(c.args[0], list)
            and "--ref=writ-decisions" in c.args[0]
            and "add" in c.args[0]
            and "-f" in c.args[0]
        ]
        assert len(note_add_calls) == 2, (
            f"Expected exactly 2 git notes add calls (one per commit); "
            f"got {len(note_add_calls)}. All calls: {mock_run.call_args_list}"
        )
        assert count == 2, (
            f"_write_commit_notes must return the count of notes written; got {count}"
        )

    def test_note_add_uses_force_flag(self) -> None:
        # [1f-cli-notes-5]: the `add -f` flag makes re-runs idempotent (overwrite).
        # RED: _write_commit_notes does not exist (ImportError).
        _write_commit_notes = self._import()

        notes = {"commit-aaa": "body"}
        with patch("subprocess.run", return_value=_completed(0)) as mock_run:
            _write_commit_notes(_REPO_ROOT, notes)

        # Find the note-add call.
        note_add_calls = [
            c for c in mock_run.call_args_list
            if c.args and isinstance(c.args[0], list)
            and "--ref=writ-decisions" in c.args[0]
            and "add" in c.args[0]
        ]
        assert note_add_calls, (
            "No git notes add call found; _write_commit_notes must call "
            "subprocess.run with a git notes add command"
        )
        cmd = note_add_calls[0].args[0]
        assert "-f" in cmd, (
            f"git notes add must use -f (force/idempotent overwrite); cmd={cmd!r}"
        )

    def test_note_body_is_passed_as_m_argument(self) -> None:
        # [1f-cli-notes-2]: the note body is passed via -m <body>.
        # RED: _write_commit_notes does not exist (ImportError).
        _write_commit_notes = self._import()

        expected_body = "## Why: add the session merge helper.\n\nRule: ENF-SYS-005"
        notes = {"commit-aaa": expected_body}
        with patch("subprocess.run", return_value=_completed(0)) as mock_run:
            _write_commit_notes(_REPO_ROOT, notes)

        note_add_calls = [
            c for c in mock_run.call_args_list
            if c.args and isinstance(c.args[0], list)
            and "--ref=writ-decisions" in c.args[0]
            and "add" in c.args[0]
        ]
        assert note_add_calls, "No git notes add call found"
        cmd = note_add_calls[0].args[0]
        assert "-m" in cmd, f"git notes add must pass body via -m; cmd={cmd!r}"
        m_index = cmd.index("-m")
        actual_body = cmd[m_index + 1]
        assert actual_body == expected_body, (
            f"note body passed to git notes add must be the full rendered body; "
            f"expected {expected_body!r}, got {actual_body!r}"
        )

    def test_commit_hash_is_last_argument(self) -> None:
        # [1f-cli-notes-1]: the commit hash must be passed as the last positional arg.
        # RED: _write_commit_notes does not exist (ImportError).
        _write_commit_notes = self._import()

        commit_hash = "deadbeefcafe1234"
        notes = {commit_hash: "body"}
        with patch("subprocess.run", return_value=_completed(0)) as mock_run:
            _write_commit_notes(_REPO_ROOT, notes)

        note_add_calls = [
            c for c in mock_run.call_args_list
            if c.args and isinstance(c.args[0], list)
            and "--ref=writ-decisions" in c.args[0]
            and "add" in c.args[0]
        ]
        assert note_add_calls, "No git notes add call found"
        cmd = note_add_calls[0].args[0]
        assert cmd[-1] == commit_hash, (
            f"commit hash must be the last argument to git notes add; "
            f"cmd[-1]={cmd[-1]!r}, expected {commit_hash!r}"
        )

    def test_every_subprocess_call_uses_cwd_repo_root(self) -> None:
        # [1f-cli-notes-4]: every subprocess.run call (both add and push) must pass
        # cwd=repo_root so git resolves the correct repository.
        # RED: _write_commit_notes does not exist (ImportError).
        _write_commit_notes = self._import()

        notes = {"commit-aaa": "body aaa", "commit-bbb": "body bbb"}
        with patch("subprocess.run", return_value=_completed(0)) as mock_run:
            _write_commit_notes(_REPO_ROOT, notes)

        for c in mock_run.call_args_list:
            # cwd is passed as a keyword argument.
            cwd = c.kwargs.get("cwd") if c.kwargs else None
            if cwd is None and len(c.args) > 1:
                # Some callers pass it positionally -- check that too.
                cwd = None  # subprocess.run(args, ...) doesn't have positional cwd
            assert cwd == _REPO_ROOT, (
                f"every subprocess call must use cwd={_REPO_ROOT!r}; "
                f"got cwd={cwd!r} for call {c}"
            )

    def test_push_uses_correct_refspec(self) -> None:
        # [1f-cli-notes-3]: the push call must use the dedicated note refspec
        # refs/notes/writ-decisions:refs/notes/writ-decisions.
        # RED: _write_commit_notes does not exist (ImportError).
        _write_commit_notes = self._import()

        notes = {"commit-aaa": "body"}
        with patch("subprocess.run", return_value=_completed(0)) as mock_run:
            _write_commit_notes(_REPO_ROOT, notes)

        push_calls = [
            c for c in mock_run.call_args_list
            if c.args and isinstance(c.args[0], list)
            and "push" in c.args[0]
        ]
        assert push_calls, (
            "No git push call found; _write_commit_notes must push after writing notes"
        )
        push_cmd = push_calls[0].args[0]
        assert _WRIT_DECISIONS_REF in push_cmd, (
            f"push must use refspec {_WRIT_DECISIONS_REF!r}; cmd={push_cmd!r}"
        )

    def test_push_not_called_when_no_notes_written(self) -> None:
        # [1f-cli-notes-3]: if notes_by_commit is empty, no push is issued.
        # RED: _write_commit_notes does not exist (ImportError).
        _write_commit_notes = self._import()

        with patch("subprocess.run", return_value=_completed(0)) as mock_run:
            count = _write_commit_notes(_REPO_ROOT, {})

        push_calls = [
            c for c in mock_run.call_args_list
            if c.args and isinstance(c.args[0], list)
            and "push" in c.args[0]
        ]
        assert push_calls == [], (
            "push must not be called when there are no notes to write"
        )
        assert count == 0, (
            f"_write_commit_notes must return 0 when notes_by_commit is empty; got {count}"
        )

    def test_push_called_only_once_for_multiple_commits(self) -> None:
        # [1f-cli-notes-3]: push happens exactly ONCE after all notes are written,
        # not once per commit.
        # RED: _write_commit_notes does not exist (ImportError).
        _write_commit_notes = self._import()

        notes = {
            "commit-aaa": "body aaa",
            "commit-bbb": "body bbb",
            "commit-ccc": "body ccc",
        }
        with patch("subprocess.run", return_value=_completed(0)) as mock_run:
            _write_commit_notes(_REPO_ROOT, notes)

        push_calls = [
            c for c in mock_run.call_args_list
            if c.args and isinstance(c.args[0], list)
            and "push" in c.args[0]
        ]
        assert len(push_calls) == 1, (
            f"push must be called exactly ONCE after all notes (not once per commit); "
            f"got {len(push_calls)} push calls"
        )

    def test_push_failure_logs_warning_and_does_not_raise(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        # [1f-cli-notes-6]: a push CalledProcessError must be swallowed with a
        # warning log; the function must still return the count of notes written.
        # RED: _write_commit_notes does not exist (ImportError).
        import logging
        _write_commit_notes = self._import()

        notes = {"commit-aaa": "body"}

        def _side_effect(args, **kwargs):
            if "push" in args:
                raise subprocess.CalledProcessError(1, args)
            return _completed(0)

        with patch("subprocess.run", side_effect=_side_effect):
            with caplog.at_level(logging.WARNING, logger="writ.pr_sync"):
                # Must not raise despite push failure.
                count = _write_commit_notes(_REPO_ROOT, notes)

        assert count == 1, (
            f"_write_commit_notes must return 1 (note was written) despite push failure; "
            f"got {count}"
        )
        # A warning must have been logged.
        warning_messages = [
            r.getMessage() for r in caplog.records if r.levelno >= logging.WARNING
        ]
        assert any("push" in m.lower() or "warn" in m.lower() or "writ-decisions" in m.lower()
                   for m in warning_messages), (
            f"A warning must be logged on push failure; "
            f"captured warnings: {warning_messages!r}"
        )

    def test_per_note_write_failure_skips_note_continues_others(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        # [1f-cli-notes-7]: a CalledProcessError on a single note-add call must skip
        # that note and NOT abort the loop -- remaining notes are still written.
        # RED: _write_commit_notes does not exist (ImportError).
        import logging
        _write_commit_notes = self._import()

        notes = {
            "commit-fail": "body that will fail",
            "commit-ok": "body that will succeed",
        }
        call_order = []

        def _side_effect(args, **kwargs):
            if isinstance(args, list) and "add" in args:
                # Fail for commit-fail, succeed for commit-ok.
                if "commit-fail" in args:
                    call_order.append(("add", "commit-fail", "fail"))
                    raise subprocess.CalledProcessError(1, args)
                else:
                    call_order.append(("add", "commit-ok", "ok"))
                    return _completed(0)
            # push succeeds
            return _completed(0)

        with patch("subprocess.run", side_effect=_side_effect):
            with caplog.at_level(logging.WARNING, logger="writ.pr_sync"):
                count = _write_commit_notes(_REPO_ROOT, notes)

        # The successful note must still be written.
        assert count >= 1, (
            f"At least 1 note must succeed despite the per-note failure; got count={count}"
        )
        # The loop must not have aborted after the first failure.
        ok_calls = [c for c in call_order if c[2] == "ok"]
        assert ok_calls, (
            "The loop must continue after a per-note add failure; "
            f"ok-add calls were not reached. call_order={call_order}"
        )

    def test_idempotent_rerun_uses_force_flag(self) -> None:
        # [1f-cli-notes-5]: a re-run on the same commits uses `add -f` which
        # overwrites the existing note. The test makes two sequential calls and
        # verifies both use -f (not append mode).
        # RED: _write_commit_notes does not exist (ImportError).
        _write_commit_notes = self._import()

        notes = {"commit-aaa": "first run body"}
        notes_v2 = {"commit-aaa": "second run body (updated)"}

        with patch("subprocess.run", return_value=_completed(0)) as mock_run:
            _write_commit_notes(_REPO_ROOT, notes)
            _write_commit_notes(_REPO_ROOT, notes_v2)

        add_calls = [
            c for c in mock_run.call_args_list
            if c.args and isinstance(c.args[0], list)
            and "--ref=writ-decisions" in c.args[0]
            and "add" in c.args[0]
        ]
        assert len(add_calls) == 2, (
            f"Two runs must produce 2 add calls; got {len(add_calls)}"
        )
        for c in add_calls:
            assert "-f" in c.args[0], (
                f"Every add call must use -f for idempotency; cmd={c.args[0]!r}"
            )


# ===========================================================================
# _write_commit_notes integration with pr_sync via CLI runner
# These tests verify the git-notes block is wired into pr_sync's _run coroutine.
# ===========================================================================

class TestPrSyncNotesBlock:
    """Verify the git-notes block is invoked by pr_sync after sync_pr_comments.

    Uses typer CliRunner with heavily mocked internals so no real DB or git is
    needed. The key assertion is that _write_commit_notes (or the equivalent
    subprocess calls) is invoked with the notes derived from the sync.

    RED: cli.py pr_sync does not yet call _write_commit_notes (or its inline
    equivalent) -- AttributeError on import or the mock is never called.
    """

    def test_write_commit_notes_called_after_sync_pr_comments(
        self,
    ) -> None:
        # [1f-cli-notes-1]: after sync_pr_comments completes, pr_sync must
        # call _write_commit_notes with a non-empty notes_by_commit dict.
        # Verified by patching _write_commit_notes and asserting it was called.
        # RED: _write_commit_notes does not exist in cli.py (ImportError / call
        # never happens -> mock.assert_called_once fails).
        #
        # This is a SYNCHRONOUS test (not @pytest.mark.asyncio): it drives the
        # typer CLI via CliRunner, and pr_sync internally calls asyncio.run().
        # Marking it async runs it inside an event loop, where asyncio.run()
        # raises "cannot be called from a running event loop" and the command
        # body never executes -- matching the sibling sync CLI tests in
        # test_decision_memory_pr_comments.py (which are plain def).
        from unittest.mock import AsyncMock, patch as _patch

        # Import _write_commit_notes to confirm it exists.
        from writ.cli import _write_commit_notes as _wcn  # noqa: F401

        # Patch at the module level where it is called.
        with _patch("writ.cli._write_commit_notes", return_value=1) as mock_wcn:
            with _patch("writ.cli._render_commit_notes", new=AsyncMock(return_value={"commit-aaa": "body"})):
                with _patch("writ.cli.sync_pr_comments", new=AsyncMock(return_value={"created": 1, "updated": 0, "unchanged": 0, "skipped_no_reason": 0})):
                    with _patch("writ.cli.get_bitbucket_email", return_value="ci@example.com"):
                        with _patch("writ.cli.get_bitbucket_token", return_value="test-token"):
                            with _patch("writ.cli.BitbucketClient") as mock_bb:
                                with _patch("writ.cli.derive_project_identity", return_value=(_REPO_ROOT, "https://bitbucket.org/ws/slug.git", "branch")):
                                    with _patch("writ.cli.parse_bitbucket_remote", return_value=("ws", "slug")):
                                        with _patch("writ.cli.ensure_project_registered", new=AsyncMock(return_value="test-proj")):
                                            with _patch("writ.cli._writ_db") as mock_db_ctx:
                                                mock_host = AsyncMock()
                                                mock_host.find_open_pr = AsyncMock(return_value=42)
                                                mock_host.close = AsyncMock()
                                                mock_bb.return_value = mock_host

                                                mock_db = AsyncMock()
                                                mock_db_ctx.return_value.__aenter__ = AsyncMock(return_value=mock_db)
                                                mock_db_ctx.return_value.__aexit__ = AsyncMock(return_value=None)

                                                from typer.testing import CliRunner
                                                from writ.cli import app
                                                runner = CliRunner()
                                                result = runner.invoke(app, ["pr", "sync"])

        # The test does not assert exit_code==0 because the full wiring may have
        # other missing pieces; the critical assertion is that _write_commit_notes
        # was called (or would be called once the helper exists).
        assert mock_wcn.called, (
            f"_write_commit_notes must be called by pr_sync after sync_pr_comments; "
            f"it was never called. pr sync output: {result.output!r}"
        )

    def test_pr_sync_notes_cwd_matches_repo_root(self) -> None:
        # [1f-cli-notes-4]: every subprocess call in the notes block uses
        # cwd=repo_root (resolved from the --repo option).
        # This is a static verification that the helper signature accepts repo_root
        # as its first argument (which it then passes to subprocess.run as cwd).
        # RED: _write_commit_notes does not exist (ImportError).
        import inspect
        from writ.cli import _write_commit_notes

        sig = inspect.signature(_write_commit_notes)
        params = list(sig.parameters.keys())
        assert params[0] == "repo_root", (
            f"_write_commit_notes first parameter must be 'repo_root'; "
            f"got {params[0]!r}. The function must pass it as cwd to subprocess.run."
        )
