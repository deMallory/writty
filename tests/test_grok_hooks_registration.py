"""Work-mode hooks and Grok tool matchers must be registered in hooks.json."""

from __future__ import annotations

import json
from pathlib import Path

HOOKS = json.loads(
    (Path(__file__).resolve().parent.parent / "hooks" / "hooks.json").read_text()
)["hooks"]


def _scripts() -> set[str]:
    found: set[str] = set()
    for groups in HOOKS.values():
        for group in groups:
            for hook in group.get("hooks", []):
                cmd = hook.get("command", "")
                if "hooks/scripts/" in cmd:
                    found.add(cmd.rsplit("/", 1)[-1])
    return found


def _matchers() -> set[str]:
    return {group.get("matcher", "") for groups in HOOKS.values() for group in groups}


def test_work_essential_scripts_are_registered():
    scripts = _scripts()
    for name in (
        "writ-pre-write-dispatch.sh",
        "auto-approve-gate.sh",
        "writ-rag-inject.sh",
        "validate-exit-plan.sh",
        "writ-run-pending-tests.sh",
        "writ-subagent-start.sh",
        "writ-subagent-stop.sh",
    ):
        assert name in scripts, f"{name} missing from hooks/hooks.json"


def test_grok_tool_matchers_are_registered():
    joined = " ".join(_matchers())
    for token in (
        "write",
        "search_replace",
        "run_terminal_command",
        "spawn_subagent",
        "exit_plan_mode",
    ):
        assert token in joined, f"matcher token {token!r} missing from hooks/hooks.json"


def test_session_start_bootstrap_accepts_grok_plugin_root():
    text = (
        Path(__file__).resolve().parent.parent
        / "hooks"
        / "scripts"
        / "session-start-bootstrap.sh"
    ).read_text()
    assert "GROK_PLUGIN_ROOT" in text


def test_bootstrap_grok_does_not_write_claude_settings():
    text = (
        Path(__file__).resolve().parent.parent / "scripts" / "bootstrap-grok.sh"
    ).read_text()
    assert "patch-global-config" not in text
    assert "~/.claude/settings.json" in text
    assert "Does not write ~/.claude/settings.json" in text or "does not write" in text.lower()
