"""SUNSET-STANDALONE: hooks/hooks.json is the single source of truth for hook registration.

The standalone install path (templates/settings.json seeded into ~/.claude/settings.json by
scripts/install-harness-config.sh) is removed. This locks: the dead files are gone, nothing in
the active install/config surface references them, bootstrap uses patch-global-config.sh, and
hooks/hooks.json carries the full hook surface. RED until the move lands.

Per TEST-TDD-001: skeletons approved before implementation.
"""

from __future__ import annotations

import json
import os

import pytest

SKILL_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))


def _p(*parts):
    return os.path.join(SKILL_ROOT, *parts)


def _read(*parts):
    with open(_p(*parts)) as f:
        return f.read()


class TestDeadFilesRemoved:
    # Fork policy: see feat/upstream-resync migration (option A).
    # The standalone install path is deliberately restored in this fork;
    # these files must exist.
    @pytest.mark.parametrize("relpath", [
        "templates/settings.json",
        "templates/settings.README.md",
        "scripts/install-harness-config.sh",
        "tests/test_harness_installer.py",
    ])
    def test_file_deleted(self, relpath):
        assert os.path.exists(_p(relpath)), f"{relpath} must exist (fork restores standalone install)"


class TestBootstrapRepointed:
    def test_bootstrap_calls_patch_global_config(self):
        src = _read("scripts/bootstrap.sh")
        assert "patch-global-config.sh" in src
        assert "install-harness-config.sh" not in src

    def test_patch_global_config_drops_install_harness_allow(self):
        src = _read("scripts/patch-global-config.sh")
        assert "install-harness-config.sh" not in src, (
            "patch-global-config.sh ALLOW/comments must not reference the deleted installer"
        )


class TestHooksJsonIsSoleSource:
    # Fork policy: see feat/upstream-resync migration (option A).
    # hooks.json is NOT the sole source in this fork: registration is split
    # between hooks/hooks.json (13 pruned entries) and templates/settings.json
    # (.claude/hooks paths). Events/hooks below are checked across both.
    EXPECTED_EVENTS = {
        "SessionStart", "UserPromptSubmit", "SubagentStart", "SubagentStop", "Stop",
        "PostToolUseFailure", "PreCompact", "PostCompact", "SessionEnd", "CwdChanged",
        "PreToolUse", "PostToolUse",
    }
    CRITICAL_HOOKS = [
        "session-start-bootstrap.sh", "writ-rag-inject.sh", "writ-pre-write-dispatch.sh",
        "friction-logger.sh", "writ-precompact.sh", "writ-postcompact.sh",
    ]

    def _hooks(self):
        d = json.loads(_read("hooks", "hooks.json"))
        return d.get("hooks", d)

    def _settings_hooks(self):
        d = json.loads(_read("templates", "settings.json"))
        return d.get("hooks", {})

    def test_all_events_present(self):
        # Fork policy: see feat/upstream-resync migration (option A).
        events = set(self._hooks().keys()) | set(self._settings_hooks().keys())
        assert self.EXPECTED_EVENTS <= events, f"missing events: {self.EXPECTED_EVENTS - events}"

    def test_every_event_has_a_command(self):
        for event, matchers in self._hooks().items():
            cmds = [hk.get("command", "") for m in matchers for hk in m.get("hooks", [])]
            assert any(c.strip() for c in cmds), f"{event} has no hook command"

    def test_critical_hooks_registered(self):
        # Fork policy: see feat/upstream-resync migration (option A).
        src = _read("hooks", "hooks.json") + _read("templates", "settings.json")
        for name in self.CRITICAL_HOOKS:
            assert name in src, f"{name} missing from hook registration surfaces"

    def test_hooks_use_plugin_root(self):
        # SoT registers via the plugin root, never absolute home paths.
        src = _read("hooks", "hooks.json")
        assert "${CLAUDE_PLUGIN_ROOT}" in src
        assert "/.claude/skills/writ/" not in src


class TestPreWriteDispatchConsolidationFromHooksJson:
    """The PreToolUse Write|Edit consolidation invariants now read from the SoT (hooks/hooks.json),
    not from ~/.claude/settings.json (which no longer carries hooks)."""

    def _pretooluse_commands(self):
        # Fork policy: see feat/upstream-resync migration (option A).
        # The pre-write dispatch registers via templates/settings.json in this
        # fork; scan both registration surfaces.
        cmds = []
        for parts in (("hooks", "hooks.json"), ("templates", "settings.json")):
            d = json.loads(_read(*parts))
            hooks = d.get("hooks", d) if parts[0] == "hooks" else d.get("hooks", {})
            cmds.extend(self._extract(hooks))
        return cmds

    @staticmethod
    def _extract(hooks):
        cmds = []
        for entry in hooks.get("PreToolUse", []):
            matcher = entry.get("matcher", "")
            if "Write" in matcher or "Edit" in matcher or matcher in ("", "*"):
                for hk in entry.get("hooks", []):
                    cmds.append(hk.get("command", ""))
        return cmds

    def test_dispatch_present(self):
        assert any("writ-pre-write-dispatch" in c for c in self._pretooluse_commands())

    def test_legacy_hooks_absent(self):
        joined = "\n".join(self._pretooluse_commands())
        for dead in ("check-gate-approval", "enforce-final-gate", "writ-pretool-rag.sh"):
            assert dead not in joined, f"{dead} must not be in PreToolUse"
