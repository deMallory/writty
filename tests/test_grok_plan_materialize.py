"""writ grok materialize-plan copies the session plan and refuses to invent one."""

from __future__ import annotations

import os
from pathlib import Path

from writ.harness.grok_plan import encode_session_cwd, materialize_plan, session_plan_path
from writ.session.approval_workflow import _validate_phase_a

VALID_PLAN = """# Plan: test

## Files

- `writ/harness/grok_plan.py` (create) -- copies the Grok session plan

## Analysis

Copy only.

## Rules Applied

No matching rules.

## Capabilities

- [ ] copies a non-empty session plan
"""


def _write_session_plan(tmp_path: Path, cwd: str, sid: str, text: str) -> Path:
    dest = session_plan_path(cwd, sid, home=tmp_path)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(text, encoding="utf-8")
    return dest


def test_encode_cwd_matches_grok_percent_encoding():
    assert encode_session_cwd("/Users/me/proj") == "%2FUsers%2Fme%2Fproj"


def test_copies_session_plan_to_repo_root(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / ".git").mkdir()
    sid = "sess-1"
    _write_session_plan(tmp_path, str(repo), sid, VALID_PLAN)

    result = materialize_plan(str(repo), sid, home=tmp_path)
    assert result.ok
    assert result.action == "copied"
    dest = repo / "plan.md"
    assert dest.is_file()
    assert dest.read_text(encoding="utf-8") == VALID_PLAN


def test_refuses_missing_session_plan(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / ".git").mkdir()
    result = materialize_plan(str(repo), "missing", home=tmp_path)
    assert not result.ok
    assert result.action == "missing"
    assert not (repo / "plan.md").exists()


def test_refuses_empty_session_plan(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / ".git").mkdir()
    _write_session_plan(tmp_path, str(repo), "sess-empty", "   \n")
    result = materialize_plan(str(repo), "sess-empty", home=tmp_path)
    assert not result.ok
    assert result.action == "empty"
    assert not (repo / "plan.md").exists()


def test_keeps_newer_repo_root_plan_unless_forced(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / ".git").mkdir()
    sid = "sess-2"
    source = _write_session_plan(tmp_path, str(repo), sid, VALID_PLAN)
    dest = repo / "plan.md"
    dest.write_text("# newer local edit\n", encoding="utf-8")
    dest_stat = dest.stat()
    os.utime(source, (dest_stat.st_atime - 10, dest_stat.st_mtime - 10))

    kept = materialize_plan(str(repo), sid, home=tmp_path)
    assert kept.ok
    assert kept.action == "kept"
    assert dest.read_text(encoding="utf-8") == "# newer local edit\n"

    forced = materialize_plan(str(repo), sid, home=tmp_path, force=True)
    assert forced.ok
    assert forced.action == "copied"
    assert dest.read_text(encoding="utf-8") == VALID_PLAN


def test_materialized_plan_passes_phase_a_validator(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / ".git").mkdir()
    _write_session_plan(tmp_path, str(repo), "sess-3", VALID_PLAN)
    result = materialize_plan(str(repo), "sess-3", home=tmp_path)
    assert result.ok
    assert _validate_phase_a(str(repo), "sess-3") is None
