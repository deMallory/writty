"""Approval must not depend on a repo marker file being present.

The project root decides which plan.md the approval gate validates and where gate
artifacts land. It was found ONLY by walking up for one of six markers
(composer.json, package.json, Cargo.toml, go.mod, pyproject.toml, .git). Claude Code
runs anywhere, so in an unmarked directory the walk returned "" and the advance route
refused every approval AND spent the token, making the workflow unusable there.

resolve_project_root adds an ordered fallback: explicit root, then the marker dir at or
above the start dir, then the start dir itself. It never reads os.getcwd() on its own,
because server-side that is Writ's install dir (which carries .git, pyproject.toml AND
a plan.md, so an implicit fallback would validate Writ's own plan for someone else's
project).
"""
from __future__ import annotations

import os

import pytest

from writ.session.locators import (
    ROOT_FROM_CWD,
    ROOT_FROM_EXPLICIT,
    ROOT_FROM_MARKER,
    ROOT_FROM_NONE,
    resolve_project_root,
)


class TestTierOrder:
    def test_explicit_root_wins(self, tmp_path):
        marked = tmp_path / "marked"
        marked.mkdir()
        (marked / ".git").mkdir()
        root, tier = resolve_project_root(explicit="/given/root", start=str(marked))
        assert (root, tier) == ("/given/root", ROOT_FROM_EXPLICIT)

    def test_marker_above_start_wins_over_start(self, tmp_path):
        """Working deep inside a repo still approves the plan at the repo root."""
        (tmp_path / "pyproject.toml").write_text("")
        deep = tmp_path / "src" / "module"
        deep.mkdir(parents=True)
        root, tier = resolve_project_root(start=str(deep))
        assert (root, tier) == (str(tmp_path), ROOT_FROM_MARKER)

    def test_marker_at_start_itself_is_found(self, tmp_path):
        (tmp_path / "package.json").write_text("{}")
        root, tier = resolve_project_root(start=str(tmp_path))
        assert (root, tier) == (str(tmp_path), ROOT_FROM_MARKER)

    @pytest.mark.parametrize(
        "marker", ["composer.json", "package.json", "Cargo.toml", "go.mod", "pyproject.toml"]
    )
    def test_each_file_marker_resolves(self, tmp_path, marker):
        (tmp_path / marker).write_text("")
        assert resolve_project_root(start=str(tmp_path))[1] == ROOT_FROM_MARKER

    def test_git_dir_marker_resolves(self, tmp_path):
        (tmp_path / ".git").mkdir()
        assert resolve_project_root(start=str(tmp_path))[1] == ROOT_FROM_MARKER


class TestUnmarkedDirectory:
    def test_unmarked_start_falls_back_to_itself(self, tmp_path):
        """The fix: a directory with no marker is still a usable project root."""
        work = tmp_path / "no" / "markers" / "here"
        work.mkdir(parents=True)
        root, tier = resolve_project_root(start=str(work))
        assert (root, tier) == (str(work), ROOT_FROM_CWD)

    @pytest.mark.parametrize("rel", [".", "sub/dir", "./x", ".."])
    def test_relative_start_is_refused_not_resolved(self, tmp_path, monkeypatch, rel):
        """A relative start must resolve to nothing, never to the process cwd.

        os.path.abspath would resolve it against the caller's cwd. Inside the daemon that
        is Writ's own install dir, which has .git + pyproject.toml + a plan.md, so a
        relative cwd would make the gate approve Writ's plan for another project. Three
        independent reviewers flagged the abspath call for exactly this.
        """
        (tmp_path / ".git").mkdir()
        monkeypatch.chdir(tmp_path)
        assert resolve_project_root(start=rel) == ("", ROOT_FROM_NONE)

    def test_walk_terminates_at_filesystem_root(self, tmp_path):
        """No marker anywhere up to '/' must return the start, not loop or raise."""
        work = tmp_path / "deep" / "deeper"
        work.mkdir(parents=True)
        root, tier = resolve_project_root(start=str(work))
        assert tier in (ROOT_FROM_CWD, ROOT_FROM_MARKER)
        assert root


class TestNoImplicitCwd:
    def test_empty_start_resolves_to_nothing(self):
        """The daemon protection: with nothing supplied, resolve to none.

        If this ever fell back to os.getcwd(), the daemon (cwd = Writ's install dir,
        which has .git + pyproject.toml + plan.md) would validate Writ's own plan as
        the caller's approved artifact.
        """
        assert resolve_project_root() == ("", ROOT_FROM_NONE)
        assert resolve_project_root(explicit="", start="") == ("", ROOT_FROM_NONE)

    def test_cwd_is_not_consulted(self, tmp_path, monkeypatch):
        """Even standing inside a marked repo, an empty start resolves to none."""
        (tmp_path / ".git").mkdir()
        monkeypatch.chdir(tmp_path)
        assert resolve_project_root(start="") == ("", ROOT_FROM_NONE)


class TestCliWrapperKeepsCwdSemantics:
    def test_detect_project_root_uses_process_cwd(self, tmp_path, monkeypatch):
        """The CLI path supplies its own cwd, so today's behavior is preserved."""
        from writ.session.approval_workflow import _detect_project_root

        (tmp_path / "go.mod").write_text("")
        deep = tmp_path / "cmd" / "app"
        deep.mkdir(parents=True)
        monkeypatch.chdir(deep)
        assert _detect_project_root("") == str(tmp_path)

    def test_detect_project_root_honors_explicit(self, tmp_path, monkeypatch):
        from writ.session.approval_workflow import _detect_project_root

        monkeypatch.chdir(tmp_path)
        assert _detect_project_root("/explicit") == "/explicit"

    def test_detect_project_root_falls_back_to_unmarked_cwd(self, tmp_path, monkeypatch):
        from writ.session.approval_workflow import _detect_project_root

        work = tmp_path / "unmarked"
        work.mkdir()
        monkeypatch.chdir(work)
        assert _detect_project_root("") == str(work)


class TestPlanDiscoveryPrecedence:
    """_find_plan_md must approve the plan at the ROOT, not the most recently touched one.

    The old code built every candidate (root, monorepo module globs, and a bare
    `*/plan.md`) then sorted them all by mtime, so a newer plan one level down beat the
    root plan the user was actually looking at. With a root that resolved high (a $HOME
    carrying a .git), `*/plan.md` also reached into unrelated sibling projects.
    """

    def _plan(self, path, body="# plan\n"):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body)
        return path

    def test_root_plan_wins_over_a_newer_subdirectory_plan(self, tmp_path):
        from writ.session.locators import _find_plan_md

        root_plan = self._plan(tmp_path / "plan.md")
        os.utime(root_plan, (1_000_000, 1_000_000))          # deliberately OLD
        newer = self._plan(tmp_path / "other" / "plan.md")
        os.utime(newer, (2_000_000, 2_000_000))              # deliberately NEW
        assert _find_plan_md(str(tmp_path)) == str(root_plan)

    def test_sibling_project_plan_is_never_used(self, tmp_path):
        """A directory with its own marker is a different project, not a module."""
        from writ.session.locators import _find_plan_md

        sibling = tmp_path / "unrelated-project"
        (sibling / ".git").mkdir(parents=True)
        self._plan(sibling / "plan.md")
        assert _find_plan_md(str(tmp_path)) is None, (
            "another project's plan.md must not satisfy this project's gate"
        )

    def test_monorepo_module_plan_still_found(self, tmp_path):
        """A module carries no marker of its own, so it stays eligible."""
        from writ.session.locators import _find_plan_md

        module_plan = self._plan(tmp_path / "app" / "code" / "Vendor" / "Module" / "plan.md")
        assert _find_plan_md(str(tmp_path)) == str(module_plan)

    def test_newest_module_plan_wins_when_there_is_no_root_plan(self, tmp_path):
        from writ.session.locators import _find_plan_md

        old = self._plan(tmp_path / "src" / "alpha" / "plan.md")
        new = self._plan(tmp_path / "src" / "beta" / "plan.md")
        os.utime(old, (1_000_000, 1_000_000))
        os.utime(new, (2_000_000, 2_000_000))
        assert _find_plan_md(str(tmp_path)) == str(new)

    def test_module_plan_beside_a_sibling_project_picks_the_module(self, tmp_path):
        from writ.session.locators import _find_plan_md

        sibling = tmp_path / "other-checkout"
        (sibling / "package.json").parent.mkdir(parents=True, exist_ok=True)
        (sibling / "package.json").write_text("{}")
        sibling_plan = self._plan(sibling / "plan.md")
        os.utime(sibling_plan, (3_000_000, 3_000_000))       # newest of all
        module_plan = self._plan(tmp_path / "src" / "pkg" / "plan.md")
        os.utime(module_plan, (1_000_000, 1_000_000))
        assert _find_plan_md(str(tmp_path)) == str(module_plan)

    def test_no_plan_anywhere_returns_none(self, tmp_path):
        from writ.session.locators import _find_plan_md

        assert _find_plan_md(str(tmp_path)) is None
