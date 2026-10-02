"""Pair Ledger gatherers: writ/analysis/pair_ledger.py.

Every test builds a fake home under tmp_path: ~/.claude/CLAUDE.md, output styles,
~/.claude/projects/<encoded>/ with a transcript carrying `cwd` and a memory/ dir,
and real git repos for the sync states. Nothing here reads the operator's ~/.claude.
"""
from __future__ import annotations

import json
import os
import subprocess
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from writ.analysis.pair_ledger import (
    ProjectCopies,
    memory_copies,
    rule_sources,
    stale_notes,
)

COMMIT_DATE = "2026-09-01T12:00:00+00:00"


def _git(repo: Path, *args: str) -> None:
    env = {**os.environ, "GIT_AUTHOR_DATE": COMMIT_DATE, "GIT_COMMITTER_DATE": COMMIT_DATE}
    subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@example.com", *args],
        cwd=repo, env=env, check=True, capture_output=True,
    )


def _repo(path: Path, tracked: dict[str, str], untracked: dict[str, str] | None = None) -> Path:
    """A git repo whose `tracked` files sit in one commit dated COMMIT_DATE."""
    path.mkdir(parents=True, exist_ok=True)
    _git(path, "init", "-q")
    for rel, text in {**tracked, **(untracked or {})}.items():
        target = path / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text)
    _git(path, "add", *tracked)
    _git(path, "commit", "-q", "-m", "init")
    return path


def _project(
    home: Path,
    cwd: Path | None,
    notes: dict[str, str] | None = None,
    encoded: str | None = None,
) -> Path:
    """~/.claude/projects/<encoded>/ with a transcript naming `cwd` and optional notes."""
    encoded = encoded or str(cwd).replace("/", "-").replace(".", "-")
    project_dir = home / ".claude" / "projects" / encoded
    project_dir.mkdir(parents=True)
    if cwd is not None:
        # First line carries no cwd, as a real transcript's summary line does not.
        lines = [{"type": "summary"}, {"type": "user", "cwd": str(cwd)}]
        (project_dir / "s1.jsonl").write_text("".join(json.dumps(x) + "\n" for x in lines))
    for name, text in (notes or {}).items():
        memory = project_dir / "memory"
        memory.mkdir(exist_ok=True)
        (memory / f"{name}.md").write_text(text)
    return project_dir


def _note(name: str, body: str = "body", description: str = "desc") -> str:
    return f"---\nname: {name}\ndescription: {description}\nmetadata:\n  type: project\n---\n\n{body}\n"


def _row(name: str, project: str, body: str = "body", description: str = "desc",
         status: str = "live") -> dict:
    """A list_all_memories() row as the graph returns it for a mirrored note."""
    return {"name": name, "project": project, "path": "", "status": status, "type": "project",
            "updated_at": "2026-09-01T00:00:00Z", "description": description, "body": body}


@pytest.fixture
def home(tmp_path: Path) -> Path:
    h = tmp_path / "home"
    (h / ".claude").mkdir(parents=True)
    return h


def _by_path(home: Path) -> dict[str, object]:
    return {s.display_path: s for s in rule_sources(home)}


class TestRuleSourceDiscovery:
    def test_lists_global_styles_named_and_project_files_once(self, home: Path, tmp_path: Path) -> None:
        (home / ".claude" / "CLAUDE.md").write_text("- a\nRead `~/.claude/memory/GLOBAL.md` first.\n")
        styles = home / ".claude" / "output-styles"
        styles.mkdir()
        (styles / "kind.md").write_text("- terse\n")
        (styles / "kind.md.bak").write_text("- old\n")
        repo = _repo(tmp_path / "repo", {"CLAUDE.md": "- r\n"})
        worktree = repo / ".claude" / "worktrees" / "wt"
        worktree.mkdir(parents=True)
        (worktree / "CLAUDE.md").write_text("- copy\n")
        _project(home, repo)
        _project(home, repo, encoded="repo-again")
        _project(home, home)  # home/.claude/CLAUDE.md is the global file itself
        _project(home, worktree)

        paths = [s.display_path for s in rule_sources(home)]

        assert paths == [
            "~/.claude/CLAUDE.md",
            "~/.claude/output-styles/kind.md",
            "~/.claude/memory/GLOBAL.md",
            str(repo / "CLAUDE.md"),
        ]

    def test_named_file_absent_reads_missing(self, home: Path) -> None:
        (home / ".claude" / "CLAUDE.md").write_text("Always read `~/.claude/memory/GLOBAL.md`.\n")

        named = _by_path(home)["~/.claude/memory/GLOBAL.md"]

        assert named.sync == "missing"
        assert named.rules is None
        assert named.changed is None

    def test_project_dir_without_transcript_adds_no_row(self, home: Path) -> None:
        _project(home, None, encoded="-no-transcript")

        assert rule_sources(home) == []

    def test_cwd_comes_from_newest_transcript(self, home: Path, tmp_path: Path) -> None:
        old = _repo(tmp_path / "old", {"CLAUDE.md": "- old\n"})
        new = _repo(tmp_path / "new", {"CLAUDE.md": "- new\n"})
        project_dir = _project(home, old, encoded="-moved")
        newer = project_dir / "s2.jsonl"
        newer.write_text(json.dumps({"type": "user", "cwd": str(new)}) + "\n")
        stamp = datetime.now(UTC).timestamp()
        os.utime(project_dir / "s1.jsonl", (stamp - 3600, stamp - 3600))
        os.utime(newer, (stamp, stamp))

        paths = [s.display_path for s in rule_sources(home)]

        assert paths == [str(new / "CLAUDE.md")]


class TestSyncState:
    def test_tracked_file_reads_in_git_with_commit_date(self, home: Path, tmp_path: Path) -> None:
        repo = _repo(tmp_path / "repo", {"CLAUDE.md": "- r\n"})
        _project(home, repo)

        source = _by_path(home)[str(repo / "CLAUDE.md")]

        assert source.sync == "in git"
        assert source.changed == "2026-09-01"

    def test_untracked_home_file_with_identical_twin_reads_copy_same(self, home: Path, tmp_path: Path) -> None:
        text = "- global\n"
        (home / ".claude" / "CLAUDE.md").write_text(text)
        dotfiles = _repo(tmp_path / "dotfiles", {".claude/CLAUDE.md": text})
        _project(home, dotfiles)

        assert _by_path(home)["~/.claude/CLAUDE.md"].sync == "copy in dotfiles, same"

    def test_twin_with_different_content_reads_copy_differs(self, home: Path, tmp_path: Path) -> None:
        (home / ".claude" / "CLAUDE.md").write_text("- edited here\n")
        dotfiles = _repo(tmp_path / "dotfiles", {".claude/CLAUDE.md": "- global\n"})
        _project(home, dotfiles)

        assert _by_path(home)["~/.claude/CLAUDE.md"].sync == "copy in dotfiles, differs"

    def test_symlinked_style_resolves_before_compare(self, home: Path, tmp_path: Path) -> None:
        text = "- style\n"
        store = tmp_path / "store" / "kind.md"
        store.parent.mkdir()
        store.write_text(text)
        styles = home / ".claude" / "output-styles"
        styles.mkdir()
        (styles / "kind.md").symlink_to(store)
        dotfiles = _repo(tmp_path / "dotfiles", {".claude/output-styles/kind.md": text})
        _project(home, dotfiles)

        assert _by_path(home)["~/.claude/output-styles/kind.md"].sync == "copy in dotfiles, same"

    def test_untracked_file_without_twin_reads_this_mac_only(self, home: Path, tmp_path: Path) -> None:
        repo = _repo(tmp_path / "repo", {"README.md": "x\n"}, untracked={"CLAUDE.md": "- local\n"})
        mtime = datetime(2026, 7, 9, 12, tzinfo=UTC).timestamp()
        os.utime(repo / "CLAUDE.md", (mtime, mtime))
        _project(home, repo)

        source = _by_path(home)[str(repo / "CLAUDE.md")]

        assert source.sync == "this Mac only"
        assert source.changed == "2026-07-09"

    def test_global_file_outside_any_repo_reads_this_mac_only(self, home: Path) -> None:
        (home / ".claude" / "CLAUDE.md").write_text("- global\n")

        assert _by_path(home)["~/.claude/CLAUDE.md"].sync == "this Mac only"


class TestRuleCount:
    def test_counts_dash_star_plus_list_lines_only(self, home: Path) -> None:
        (home / ".claude" / "CLAUDE.md").write_text(
            "# Heading\n- a\n  - nested\n* b\n+ c\n**bold** line\n-not a bullet\n1. numbered\ntext - inline\n"
        )

        assert _by_path(home)["~/.claude/CLAUDE.md"].rules == 4


class TestMemoryCopies:
    def test_classifies_copied_outdated_and_missing_per_project(self, home: Path) -> None:
        notes = {n: _note(n) for n in ("n1", "n2", "n3", "n4")}
        project_dir = _project(home, Path("/work/alpha"), notes)
        encoded = project_dir.name
        rows = [
            _row("n1", encoded),
            _row("n2", encoded, body="older body"),
            _row("n4", encoded, status="deleted"),
        ]

        result = memory_copies(rows, home)

        assert result == [ProjectCopies(project="alpha", copied=1, outdated=1, missing=2,
                                        outdated_names=("n2",))]

    def test_description_change_counts_as_outdated(self, home: Path) -> None:
        project_dir = _project(home, Path("/work/alpha"), {"n1": _note("n1", description="new")})

        result = memory_copies([_row("n1", project_dir.name, description="old")], home)

        assert result[0].outdated == 1
        assert result[0].outdated_names == ("n1",)

    def test_row_in_another_project_is_not_a_copy(self, home: Path) -> None:
        _project(home, Path("/work/alpha"), {"n1": _note("n1")})

        result = memory_copies([_row("n1", "-some-other-project")], home)

        assert (result[0].copied, result[0].missing) == (0, 1)

    def test_none_rows_returns_none(self, home: Path) -> None:
        _project(home, Path("/work/alpha"), {"n1": _note("n1")})

        assert memory_copies(None, home) is None

    def test_memory_index_is_not_a_note(self, home: Path) -> None:
        _project(home, Path("/work/alpha"), {"n1": _note("n1"), "MEMORY": "- [n1](n1.md)\n"})

        result = memory_copies([], home)

        assert result[0].missing == 1

    def test_label_falls_back_to_encoded_dir(self, home: Path) -> None:
        _project(home, None, {"n1": _note("n1")}, encoded="-no-transcript")

        assert memory_copies([], home)[0].project == "-no-transcript"

    def test_projects_sorted_by_note_count(self, home: Path) -> None:
        _project(home, Path("/work/small"), {"a": _note("a")})
        _project(home, Path("/work/big"), {n: _note(n) for n in ("a", "b", "c")})

        assert [p.project for p in memory_copies([], home)] == ["big", "small"]

    def test_project_without_notes_adds_no_row(self, home: Path) -> None:
        _project(home, Path("/work/alpha"))

        assert memory_copies([], home) == []


class TestStaleNotes:
    def test_lists_notes_at_least_90_days_old_oldest_first(self, home: Path) -> None:
        now = datetime(2026, 10, 1, 12, tzinfo=UTC)
        project_dir = _project(
            home, Path("/work/alpha"),
            {n: _note(n) for n in ("a", "b", "c")} | {"MEMORY": "- index\n"},
        )
        for name, days in (("a", 120), ("b", 90), ("c", 89), ("MEMORY", 200)):
            stamp = (now - timedelta(days=days)).timestamp()
            os.utime(project_dir / "memory" / f"{name}.md", (stamp, stamp))

        result = stale_notes(home, now=now)

        assert [(n.name, n.project, n.age_days) for n in result] == [
            ("a", "alpha", 120),
            ("b", "alpha", 90),
        ]
        assert result[0].changed == "2026-06-03"
