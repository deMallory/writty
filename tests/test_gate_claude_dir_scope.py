"""The work gate must not exempt code just because it lives under a .claude dir.

Live bypass (session b1c8583c, 2026-07-29): gate-categories.json listed
`*/.claude/*` as a work-gate exclusion, so an implementation file written to
~/.claude/skills/<name>/bin/*.py was allowed with gate_status="excluded" while
mode=work and gates_approved=[]. The friction log recorded the allow one turn
before an identical write outside .claude was denied phase-a.

The exclusion existed for Claude Code CONFIG surfaces (settings, agents,
commands, notes) which must stay writable before plan approval so the agent can
bootstrap. It was never meant to cover source under .claude/skills/. These tests
pin the narrowed scope: config exempt, code gated. Writ's own tree stays writable
through the separate skill_dir exemption, not through this list.
"""
from __future__ import annotations

import importlib
import os
import sys
import uuid

import pytest

SKILL_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))


def _imp(name):
    if SKILL_ROOT not in sys.path:
        sys.path.insert(0, SKILL_ROOT)
    return importlib.import_module(name)


def _seed_work_unapproved() -> str:
    """A session in work mode with neither gate approved (the deny-by-default state)."""
    cache = _imp("writ.session.cache")
    sid = f"cds-{uuid.uuid4().hex[:8]}"
    data = cache._read_cache(sid)
    data.update(mode="work", gates_approved=[], current_phase="planning")
    cache._write_cache(sid, data)
    return sid


def _check(path: str, skill_dir: str = "/nonexistent/other-skill") -> dict:
    """Gate verdict for `path`, with skill_dir pointed AWAY from it.

    The default skill_dir keeps the skill_exempt branch out of the way so each
    case exercises the exclusion list, not Writ's self-edit exemption.
    """
    gates = _imp("writ.session.gates")
    return gates._can_write_check(
        _seed_work_unapproved(), {"tool_input": {"file_path": path}}, skill_dir
    )


class TestClaudeDirCodeIsGated:
    def test_skill_source_denied(self, tmp_path, monkeypatch):
        monkeypatch.setenv("WRIT_CACHE_DIR", str(tmp_path))
        home = os.environ.get("HOME", "/home/u")
        res = _check(f"{home}/.claude/skills/release-page/bin/release_table.py")
        assert res["can_write"] is False, "skill source under .claude must be plan-gated"
        assert "ENF-GATE-PLAN" in (res["reason"] or "")

    def test_project_claude_hook_script_denied(self, tmp_path, monkeypatch):
        monkeypatch.setenv("WRIT_CACHE_DIR", str(tmp_path))
        res = _check("/proj/.claude/hooks/my-hook.sh")
        assert res["can_write"] is False, "hook scripts are code, not config"

    def test_arbitrary_claude_path_denied(self, tmp_path, monkeypatch):
        monkeypatch.setenv("WRIT_CACHE_DIR", str(tmp_path))
        home = os.environ.get("HOME", "/home/u")
        res = _check(f"{home}/.claude/anything/evil.py")
        assert res["can_write"] is False

    @pytest.mark.parametrize("path", [
        # The exclusion patterns are matched against the RAW path (gates.py _matches_any),
        # and `*` spans `/`, so a directory glob like `*/.claude/agents/*` exempted any
        # depth and any extension under it -- and `..` made it exempt files the OS writes
        # OUTSIDE .claude entirely. Adversarial review caught this: the narrowed list had
        # replaced one hole with a smaller one. The config-only patterns that survive are
        # extension-anchored or exact filenames.
        "/proj/.claude/agents/../../src/app.py",
        "/proj/.claude/commands/../../src/app.php",
        "/proj/.claude/agents/sub/deep/impl.py",
        "/proj/.claude/commands/deep/nested/payload.py",
        "/proj/.claude/agents/helper.sh",
        # A .claude/agents dir the agent creates anywhere in the tree, no traversal needed.
        "/proj/src/.claude/agents/x/main.py",
    ])
    def test_code_under_agents_or_commands_denied(self, tmp_path, monkeypatch, path):
        monkeypatch.setenv("WRIT_CACHE_DIR", str(tmp_path))
        res = _check(path)
        assert res["can_write"] is False, f"{path} must be plan-gated, not exempt"

    def test_traversal_target_is_gated_the_same_as_its_plain_spelling(self, tmp_path, monkeypatch):
        """The same file must get the same verdict however the path is spelled."""
        monkeypatch.setenv("WRIT_CACHE_DIR", str(tmp_path))
        plain = _check("/proj/src/app.py")
        spelled = _check("/proj/.claude/agents/../../src/app.py")
        assert plain["can_write"] is False
        assert spelled["can_write"] is False, (
            "a traversal spelling reached the same file with the opposite verdict"
        )


class TestClaudeDirConfigStaysWritable:
    def test_project_settings_json_excluded(self, tmp_path, monkeypatch):
        # Project-level settings are NOT covered by the ~/.claude settings_exempt
        # branch, so they rely on this exclusion to stay writable pre-approval.
        monkeypatch.setenv("WRIT_CACHE_DIR", str(tmp_path))
        res = _check("/proj/.claude/settings.json")
        assert res["can_write"] is True

    def test_project_settings_local_json_excluded(self, tmp_path, monkeypatch):
        monkeypatch.setenv("WRIT_CACHE_DIR", str(tmp_path))
        res = _check("/proj/.claude/settings.local.json")
        assert res["can_write"] is True

    def test_agent_definition_excluded(self, tmp_path, monkeypatch):
        """Covered by the *.md pattern, not by a directory glob (see the deny cases)."""
        monkeypatch.setenv("WRIT_CACHE_DIR", str(tmp_path))
        res = _check("/proj/.claude/agents/writ-explorer.md")
        assert res["can_write"] is True

    def test_slash_command_excluded(self, tmp_path, monkeypatch):
        monkeypatch.setenv("WRIT_CACHE_DIR", str(tmp_path))
        res = _check("/proj/.claude/commands/writ-approve.md")
        assert res["can_write"] is True

    def test_every_shipped_definition_is_still_writable(self, tmp_path, monkeypatch):
        """Inventory check: the real agent/command files on disk must stay exempt.

        Removing the two directory globs is only safe because every actual definition is
        markdown. This walks the real directories instead of trusting that claim.
        """
        monkeypatch.setenv("WRIT_CACHE_DIR", str(tmp_path))
        home = os.environ.get("HOME", "")
        roots = [
            os.path.join(home, ".claude", "agents"),
            os.path.join(home, ".claude", "commands"),
            os.path.join(SKILL_ROOT, ".claude", "agents"),
            os.path.join(SKILL_ROOT, ".claude", "commands"),
        ]
        checked = 0
        for root in roots:
            if not os.path.isdir(root):
                continue
            for dirpath, _dirs, files in os.walk(root):
                for name in files:
                    target = os.path.join(dirpath, name)
                    checked += 1
                    assert _check(target)["can_write"] is True, (
                        f"a shipped definition became gated: {target}"
                    )
        assert checked, "no definitions found to check; the inventory assumption is untested"

    def test_memory_note_excluded(self, tmp_path, monkeypatch):
        # ~/.claude/projects/<slug>/memory/*.md is written mid-session by the
        # memory system; markdown under .claude stays exempt.
        monkeypatch.setenv("WRIT_CACHE_DIR", str(tmp_path))
        home = os.environ.get("HOME", "/home/u")
        res = _check(f"{home}/.claude/projects/-proj/memory/project_foo.md")
        assert res["can_write"] is True


class TestWritSelfEditUnaffected:
    def test_skill_dir_write_still_allowed(self, tmp_path, monkeypatch):
        """Narrowing the list must not lock Writ out of editing itself.

        Passing skill_dir=SKILL_ROOT reproduces the real hook call, where the
        exemption comes from skill_dir -- which works at ANY install path, not
        only under ~/.claude/skills.
        """
        monkeypatch.setenv("WRIT_CACHE_DIR", str(tmp_path))
        res = _check(f"{SKILL_ROOT}/writ/session/gates.py", skill_dir=SKILL_ROOT)
        assert res["can_write"] is True


class TestExclusionListShape:
    def test_no_blanket_claude_wildcard(self):
        """Pin the hole shut: a bare `*/.claude/*` re-exempts every path under it."""
        import json

        path = os.path.join(SKILL_ROOT, "bin", "lib", "gate-categories.json")
        with open(path) as fh:
            exclusions = json.load(fh)["exclusions"]
        assert "*/.claude/*" not in exclusions
