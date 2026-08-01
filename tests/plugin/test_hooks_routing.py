"""Tests for hooks/hooks.json event routing (Phase B + C).

Verifies the hooks manifest exists, is the single source of truth for hook
registration, uses ${CLAUDE_PLUGIN_ROOT} for all paths, and that every
referenced script file exists on disk and is executable.
"""

from __future__ import annotations

import json
import os
import stat
from pathlib import Path

import pytest

from tests.plugin.conftest import REPO_ROOT, _expand_plugin_root

HOOKS_JSON_PATH = REPO_ROOT / "hooks" / "hooks.json"

# Fork policy: see feat/upstream-resync migration (option A).
# hooks.json is pruned to the 13 hooks with no .claude/hooks/ counterpart;
# the remainder register via templates/settings.json.
EXPECTED_EVENT_SCRIPTS: dict[str, list[str]] = {
    "SessionStart": ["writ-blackbox-capture.sh", "session-start-bootstrap.sh"],
    "SubagentStop": ["writ-blackbox-capture.sh"],
    "Stop": ["writ-comms-output-gate.sh"],
    "PostToolUseFailure": ["writ-blackbox-capture.sh"],
    "PostCompact": ["writ-blackbox-capture.sh"],
    "CwdChanged": ["writ-blackbox-capture.sh"],
    "PreToolUse": [
        "writ-read-junk-gate.sh",
        "writ-debug-code-gate.sh",
        "writ-dispatch-discipline.sh",
        "writ-bash-write-gate.sh",
    ],
    "PostToolUse": ["writ-web-capture.sh", "writ-bible-authoring-push.sh"],
}


def _collect_all_registrations(hooks_data: dict) -> list[dict]:
    """Flatten all hook registration entries from the hooks dict."""
    registrations = []
    hooks_section = hooks_data.get("hooks", hooks_data)
    for event_entries in hooks_section.values():
        if isinstance(event_entries, list):
            registrations.extend(event_entries)
    return registrations


def _collect_all_commands(hooks_data: dict) -> list[str]:
    """Extract all command strings from every registration entry.

    The standard Claude Code hooks schema nests commands under each matcher
    entry's ``hooks`` array: ``{matcher, hooks: [{type, command}]}``. This
    helper flattens that structure into a list of command strings.
    """
    commands = []
    hooks_section = hooks_data.get("hooks", hooks_data)
    for event_entries in hooks_section.values():
        if isinstance(event_entries, list):
            commands.extend(_collect_event_commands(event_entries))
    return commands


def _collect_event_commands(event_entries: list) -> list[str]:
    """Extract all command strings registered under a single event."""
    commands: list[str] = []
    for entry in event_entries:
        if isinstance(entry, dict):
            if "command" in entry:
                commands.append(entry["command"])
            inner_hooks = entry.get("hooks")
            if isinstance(inner_hooks, list):
                for inner in inner_hooks:
                    if isinstance(inner, dict) and "command" in inner:
                        commands.append(inner["command"])
        elif isinstance(entry, str):
            commands.append(entry)
    return commands


class TestHooksJsonExists:
    def test_hooks_json_exists_and_parses(self) -> None:
        """hooks/hooks.json must exist and be valid JSON."""
        if not HOOKS_JSON_PATH.exists():
            pytest.skip("Phase B artifact hooks/hooks.json not yet created")
        data = json.loads(HOOKS_JSON_PATH.read_text())
        assert isinstance(data, dict)


class TestHooksJsonStructure:
    @pytest.fixture()
    def hooks_data(self) -> dict:
        if not HOOKS_JSON_PATH.exists():
            pytest.skip("Phase B artifact hooks/hooks.json not yet created")
        return json.loads(HOOKS_JSON_PATH.read_text())

    def test_hooks_json_has_top_level_hooks_key(self, hooks_data: dict) -> None:
        """Schema must be {'hooks': {...}} with a top-level 'hooks' key."""
        assert "hooks" in hooks_data, (
            "hooks.json must have a top-level 'hooks' key"
        )

    def test_hooks_json_registration_count(self, hooks_data: dict) -> None:
        """Total matcher-group registrations. The count is derived from hooks.json;
        bump it (and HANDBOOK's 'registers **N hook scripts**') when adding or
        removing a registration. #1 removed the dead PreToolUse TodoWrite gate and
        #3 removed the dead PostToolUseFailure track-failed-writes gate (40 -> 38);
        #6 added the PreToolUse Bash writ-bash-write-gate (38 -> 39); the token-saving
        read-junk gate added the PreToolUse Read writ-read-junk-gate (39 -> 40); the
        comms-output gate added the Stop writ-comms-output-gate (40 -> 41)."""
        registrations = _collect_all_registrations(hooks_data)
        # Fork policy: see feat/upstream-resync migration (option A).
        # hooks.json carries only the 13 hooks with no .claude/hooks/ counterpart.
        assert len(registrations) == 13, (
            f"hooks.json registration count drifted; found {len(registrations)}, "
            f"expected 13. Update this and HANDBOOK if the change is intentional."
        )

    def test_hooks_json_event_mapping(self, hooks_data: dict) -> None:
        """Each expected event must have its expected script names present in command strings."""
        hooks_section = hooks_data.get("hooks", {})
        for event, expected_scripts in EXPECTED_EVENT_SCRIPTS.items():
            assert event in hooks_section, (
                f"hooks.json must have an entry for event '{event}'"
            )
            event_entries = hooks_section[event]
            all_commands = " ".join(_collect_event_commands(event_entries))
            for script in expected_scripts:
                assert script in all_commands, (
                    f"Event '{event}' must reference script '{script}'"
                )

    def test_hooks_json_paths_use_claude_plugin_root(self, hooks_data: dict) -> None:
        """Every command must contain ${CLAUDE_PLUGIN_ROOT} (no hardcoded paths, no $HOME, no $WRIT_DIR)."""
        commands = _collect_all_commands(hooks_data)
        for command in commands:
            assert "${CLAUDE_PLUGIN_ROOT}" in command, (
                f"Command does not use ${{CLAUDE_PLUGIN_ROOT}}: {command!r}"
            )
            assert "$HOME" not in command, (
                f"Command must not hardcode $HOME: {command!r}"
            )
            assert "$WRIT_DIR" not in command, (
                f"Command must not use $WRIT_DIR: {command!r}"
            )


class TestHooksJsonPhaseC:
    """SessionStart bootstrap entry is added in Phase C."""

    @pytest.fixture()
    def hooks_data(self) -> dict:
        if not HOOKS_JSON_PATH.exists():
            pytest.skip("Phase B/C artifact hooks/hooks.json not yet created")
        return json.loads(HOOKS_JSON_PATH.read_text())

    def test_hooks_json_session_start_bootstrap_registered(self, hooks_data: dict) -> None:
        """Phase C: SessionStart event must map to hooks/scripts/session-start-bootstrap.sh."""
        hooks_section = hooks_data.get("hooks", {})
        if "SessionStart" not in hooks_section:
            pytest.skip("Phase C: SessionStart entry not yet added to hooks.json")
        entries = hooks_section["SessionStart"]
        all_commands = " ".join(_collect_event_commands(entries))
        assert "session-start-bootstrap.sh" in all_commands, (
            "SessionStart event must reference session-start-bootstrap.sh"
        )


class TestHookScriptFiles:
    @pytest.fixture()
    def hooks_data(self) -> dict:
        if not HOOKS_JSON_PATH.exists():
            pytest.skip("Phase B artifact hooks/hooks.json not yet created")
        return json.loads(HOOKS_JSON_PATH.read_text())

    def test_hook_scripts_exist_for_every_registration(self, hooks_data: dict) -> None:
        """Every command path in hooks.json must resolve to an existing .sh file on disk."""
        commands = _collect_all_commands(hooks_data)
        missing = []
        for command in commands:
            # Extract the script path portion (last token that ends in .sh)
            tokens = command.split()
            for token in tokens:
                if token.endswith(".sh") and "${CLAUDE_PLUGIN_ROOT}" in token:
                    resolved = _expand_plugin_root(token, REPO_ROOT)
                    if not resolved.exists():
                        missing.append(str(resolved))
        assert not missing, (
            f"The following hook scripts referenced in hooks.json do not exist:\n"
            + "\n".join(missing)
        )

    def test_hook_scripts_are_executable(self, hooks_data: dict) -> None:
        """Every hook script referenced in hooks.json must have the executable bit set."""
        commands = _collect_all_commands(hooks_data)
        not_executable = []
        for command in commands:
            tokens = command.split()
            for token in tokens:
                if token.endswith(".sh") and "${CLAUDE_PLUGIN_ROOT}" in token:
                    resolved = _expand_plugin_root(token, REPO_ROOT)
                    if resolved.exists() and not os.access(resolved, os.X_OK):
                        not_executable.append(str(resolved))
        assert not not_executable, (
            f"The following hook scripts are not executable:\n"
            + "\n".join(not_executable)
        )
