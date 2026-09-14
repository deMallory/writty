"""Fork-only hooks ported from .claude/hooks into the plugin manifest.

Pins the four surviving fork hooks (agent hotswap, output rewrite, bash-failure
telemetry, SDD review order) as registered hooks/scripts entries, their
behavior on representative envelopes, and the absence of the retired
.claude/hooks / settings.fork.json surface. See plan.md (2026-09-05).
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest

from writ.hooks_lint import lint_hooks

REPO = Path(__file__).resolve().parent.parent
HOOKS_JSON = REPO / "hooks" / "hooks.json"
SCRIPTS = REPO / "hooks" / "scripts"

PORTED = {
    "writ-agent-hotswap.sh": ("PreToolUse", "Task"),
    "writ-sdd-review-order.sh": ("PreToolUse", "Task"),
    "writ-output-rewrite.sh": ("PostToolUse", "Bash"),
    "writ-bash-failure.sh": ("PostToolUseFailure", "Bash"),
}


def _registrations() -> dict[str, list[tuple[str, str]]]:
    """script basename -> [(event, matcher)] from hooks.json."""
    data = json.loads(HOOKS_JSON.read_text())
    out: dict[str, list[tuple[str, str]]] = {}
    for event, groups in data["hooks"].items():
        for group in groups:
            for hook in group.get("hooks", []):
                name = os.path.basename(hook["command"].split()[-1])
                out.setdefault(name, []).append((event, group.get("matcher", "")))
    return out


def _run(script: str, envelope: str, tmp_path: Path) -> subprocess.CompletedProcess:
    env = os.environ.copy()
    env["WRIT_CACHE_DIR"] = str(tmp_path)
    env["WRIT_PORT"] = "1"
    return subprocess.run(
        ["bash", str(SCRIPTS / script)],
        input=envelope,
        capture_output=True,
        text=True,
        env=env,
        timeout=15,
    )


class TestRegistrations:
    @pytest.mark.parametrize("script,expected", sorted(PORTED.items()))
    def test_ported_hook_is_registered_under_its_event_and_matcher(
        self, script: str, expected: tuple[str, str]
    ) -> None:
        assert (SCRIPTS / script).is_file(), f"{script} missing from hooks/scripts"
        assert os.access(SCRIPTS / script, os.X_OK), f"{script} is not executable"
        assert expected in _registrations().get(script, []), (
            f"{script} not registered as {expected}"
        )

    def test_manifest_has_48_registrations_across_12_events(self) -> None:
        data = json.loads(HOOKS_JSON.read_text())
        assert len(data["hooks"]) == 12
        total = sum(
            len(group.get("hooks", []))
            for groups in data["hooks"].values()
            for group in groups
        )
        assert total == 48

    def test_settings_template_regenerates_byte_identically(self) -> None:
        result = subprocess.run(
            ["python3", str(REPO / "scripts" / "render-settings-template.py"), "--check"],
            capture_output=True,
            text=True,
            cwd=str(REPO),
            timeout=30,
        )
        assert result.returncode == 0, result.stdout + result.stderr


class TestAgentHotswap:
    def test_explore_without_model_becomes_writ_explorer_on_opus(self, tmp_path: Path) -> None:
        envelope = json.dumps({
            "session_id": "hotswap-1",
            "tool_name": "Task",
            "tool_input": {"subagent_type": "Explore", "prompt": "look around"},
        })
        result = _run("writ-agent-hotswap.sh", envelope, tmp_path)
        assert result.returncode == 0, result.stderr
        out = json.loads(result.stdout)["hookSpecificOutput"]
        assert out["hookEventName"] == "PreToolUse"
        assert out["updatedInput"]["subagent_type"] == "writ-explorer"
        assert out["updatedInput"]["model"] == "opus"
        assert out["updatedInput"]["prompt"] == "look around"

    def test_writ_type_with_explicit_model_passes_through(self, tmp_path: Path) -> None:
        envelope = json.dumps({
            "session_id": "hotswap-2",
            "tool_name": "Task",
            "tool_input": {"subagent_type": "writ-implementer", "model": "opus"},
        })
        result = _run("writ-agent-hotswap.sh", envelope, tmp_path)
        assert result.returncode == 0, result.stderr
        assert result.stdout.strip() == ""


class TestOutputRewrite:
    def test_aws_key_in_stdout_is_redacted_via_updated_tool_output(self, tmp_path: Path) -> None:
        key = "AKIA" + "ABCDEFGHIJKLMNOP"
        envelope = json.dumps({
            "session_id": "rewrite-1",
            "tool_name": "Bash",
            "tool_response": {"stdout": f"export AWS_KEY={key}\n", "stderr": ""},
        })
        result = _run("writ-output-rewrite.sh", envelope, tmp_path)
        assert result.returncode == 0, result.stderr
        out = json.loads(result.stdout)["hookSpecificOutput"]["updatedToolOutput"]
        assert key not in out["stdout"]
        assert "[REDACTED:writ-output-rewrite]" in out["stdout"]

    def test_clean_short_stdout_emits_nothing(self, tmp_path: Path) -> None:
        envelope = json.dumps({
            "session_id": "rewrite-2",
            "tool_name": "Bash",
            "tool_response": {"stdout": "ok\n", "stderr": ""},
        })
        result = _run("writ-output-rewrite.sh", envelope, tmp_path)
        assert result.returncode == 0, result.stderr
        assert result.stdout.strip() == ""


class TestNeverBlock:
    @pytest.mark.parametrize("script", ["writ-bash-failure.sh", "writ-sdd-review-order.sh"])
    def test_empty_stdin_exits_zero(self, script: str, tmp_path: Path) -> None:
        result = _run(script, "", tmp_path)
        assert result.returncode == 0, result.stderr
        assert "Traceback" not in result.stderr


class TestRetiredSurface:
    @pytest.mark.parametrize(
        "rel",
        [
            ".claude/hooks",
            "templates/settings.fork.json",
            "templates/writ-agent-hotswap.sh",
            "scripts/install-harness-config.sh",
        ],
    )
    def test_retired_path_is_gone(self, rel: str) -> None:
        assert not (REPO / rel).exists(), f"{rel} should have been removed"

    def test_lint_findings_are_only_the_known_two(self) -> None:
        findings = lint_hooks(HOOKS_JSON, REPO)
        flagged = {f["script"] for f in findings}
        assert flagged <= {"writ-postcompact.sh", "validate-exit-plan.sh"}, flagged
