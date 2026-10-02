"""PLUGIN ROLE NAMES: the hooks must use the names Claude Code registered for the Writ agents.

On a plugin install the agents live under the plugin's namespace (`writ:writ-explorer`),
the prefix being `name` in .claude-plugin/plugin.json. Bare `writ-*` names exist only when
scripts/bootstrap.sh linked agents/ into ~/.claude/agents/; scripts/bootstrap-plugin.sh
creates no such links. Four hooks assumed bare names:

  * writ-dispatch-discipline.sh and writ-agent-hotswap.sh rewrote dispatches to a bare
    name, which the Agent tool rejects ("Agent type 'writ-explorer' not found").
  * writ-subagent-stop.sh and writ-sdd-review-order.sh compared the incoming name with a
    bare one, so a plugin reviewer's verdict was never recorded (the CRITICAL-review commit
    gate never fired) and the spec-before-quality review order never held.

CLAUDE_PLUGIN_ROOT is the signal for the hot-swap prefix: the plugin loader sets it, a
settings.json-seeded hook does not. Dispatch names come from writ_agent_dispatch_name,
which returns the bare role only when $HOME/.claude/agents/<role>.md exists. Every test
sets or removes the plugin root and pins HOME under the tmp dir, so the ambient shell
cannot decide the outcome.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

# autouse: pins cwd to a sandbox so `mode set` cannot delete THIS repo's gate artifacts.
from tests.fixtures.session_state import sandbox_cwd  # noqa: F401

SKILL_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = SKILL_ROOT / "hooks" / "scripts"
PLUGIN_MANIFEST = SKILL_ROOT / ".claude-plugin" / "plugin.json"
HELPER = SKILL_ROOT / "bin" / "lib" / "writ-session.py"

BLOCKING_MESSAGE = """```json
{"spec_compliance": "fail", "status": "changes_requested",
 "critical": [{"file": "writ/gate.py", "line": 12, "finding": "auth check removed"}],
 "important": [], "minor": []}
```
"""


def _env(cache_dir: Path, *, plugin: bool) -> dict[str, str]:
    env = os.environ.copy()
    home = cache_dir / "home"
    home.mkdir(exist_ok=True)
    env["HOME"] = str(home)
    env["WRIT_CACHE_DIR"] = str(cache_dir)
    env["WRIT_FRICTION_LOG"] = str(cache_dir / "friction.log")
    env["WRIT_LOG_ROOT"] = str(cache_dir / "logs")
    if plugin:
        env["CLAUDE_PLUGIN_ROOT"] = str(SKILL_ROOT)
    else:
        env.pop("CLAUDE_PLUGIN_ROOT", None)
    return env


def _run(
    script: str, payload: dict, env: dict[str, str]
) -> subprocess.CompletedProcess:
    result = subprocess.run(
        ["bash", str(SCRIPTS / script)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        env=env,
        timeout=20,
    )
    assert result.returncode == 0, result.stderr  # these hooks never block by exit code
    return result


def _hook_output(stdout: str) -> dict:
    out = stdout.strip()
    return json.loads(out)["hookSpecificOutput"] if out else {}


def _seed_mode(cache_dir: Path, sid: str, mode: str) -> None:
    subprocess.run(
        [sys.executable, str(HELPER), "mode", "set", mode, sid],
        env=_env(cache_dir, plugin=False),
        check=True,
        capture_output=True,
        text=True,
    )


def _task(sid: str, subagent_type: str, **tool_input: str) -> dict:
    return {
        "session_id": sid,
        "hook_event_name": "PreToolUse",
        "tool_name": "Task",
        "tool_input": {"subagent_type": subagent_type, **tool_input},
    }


def test_plugin_manifest_name_is_the_role_prefix() -> None:
    """The hooks hardcode `writ:`; renaming the plugin must fail here, not in dispatch."""
    assert json.loads(PLUGIN_MANIFEST.read_text())["name"] == "writ"


class TestDispatchDiscipline:
    HOOK = "writ-dispatch-discipline.sh"
    EXPLORE_PROMPT = "explore the codebase structure and find where auth is handled"
    AMBIGUOUS_PROMPT = "handle this one-off miscellaneous chore"

    def test_plugin_rewrites_to_the_namespaced_explorer(self, tmp_path: Path) -> None:
        _seed_mode(tmp_path, "dd-plugin", "work")
        result = _run(
            self.HOOK,
            _task("dd-plugin", "general-purpose", prompt=self.EXPLORE_PROMPT),
            _env(tmp_path, plugin=True),
        )
        out = _hook_output(result.stdout)
        assert out["permissionDecision"] == "allow"
        assert out["updatedInput"]["subagent_type"] == "writ:writ-explorer"
        assert "'writ:writ-explorer'" in out["additionalContext"]

    def test_plugin_deny_names_the_namespaced_roles(self, tmp_path: Path) -> None:
        _seed_mode(tmp_path, "dd-deny", "work")
        result = _run(
            self.HOOK,
            _task("dd-deny", "general-purpose", prompt=self.AMBIGUOUS_PROMPT),
            _env(tmp_path, plugin=True),
        )
        out = _hook_output(result.stdout)
        assert out["permissionDecision"] == "deny"
        assert "writ:writ-explorer" in out["permissionDecisionReason"]
        assert "writ:writ-implementer" in out["permissionDecisionReason"]

    def test_standalone_keeps_the_bare_explorer(self, tmp_path: Path) -> None:
        # Bare only when bootstrap.sh linked the role into ~/.claude/agents.
        agents = tmp_path / "home" / ".claude" / "agents"
        agents.mkdir(parents=True)
        (agents / "writ-explorer.md").write_text("---\nname: writ-explorer\n---\n")
        _seed_mode(tmp_path, "dd-bare", "work")
        result = _run(
            self.HOOK,
            _task("dd-bare", "general-purpose", prompt=self.EXPLORE_PROMPT),
            _env(tmp_path, plugin=False),
        )
        assert (
            _hook_output(result.stdout)["updatedInput"]["subagent_type"]
            == "writ-explorer"
        )


class TestAgentHotswap:
    HOOK = "writ-agent-hotswap.sh"

    def test_plugin_explore_becomes_the_namespaced_explorer_on_opus(
        self, tmp_path: Path
    ) -> None:
        result = _run(
            self.HOOK,
            _task("hs-plugin", "Explore", prompt="look around"),
            _env(tmp_path, plugin=True),
        )
        updated = _hook_output(result.stdout)["updatedInput"]
        assert updated["subagent_type"] == "writ:writ-explorer"
        assert updated["model"] == "opus"

    def test_namespaced_implementer_without_model_gets_sonnet(
        self, tmp_path: Path
    ) -> None:
        result = _run(
            self.HOOK,
            _task("hs-model", "writ:writ-implementer", prompt="implement the plan"),
            _env(tmp_path, plugin=True),
        )
        updated = _hook_output(result.stdout)["updatedInput"]
        assert updated["subagent_type"] == "writ:writ-implementer"
        assert updated["model"] == "sonnet"

    def test_standalone_explore_keeps_the_bare_explorer(self, tmp_path: Path) -> None:
        result = _run(
            self.HOOK,
            _task("hs-bare", "Explore", prompt="look around"),
            _env(tmp_path, plugin=False),
        )
        assert (
            _hook_output(result.stdout)["updatedInput"]["subagent_type"]
            == "writ-explorer"
        )


class TestSubagentStop:
    HOOK = "writ-subagent-stop.sh"

    @pytest.mark.parametrize("agent_type", ["writ-reviewer", "writ:writ-reviewer"])
    def test_reviewer_verdict_is_recorded(
        self, tmp_path: Path, agent_type: str
    ) -> None:
        """The bare case proves the setup records; the namespaced case is the fix."""
        sid = "stop-reviewer"
        _run(
            self.HOOK,
            {
                "hook_event_name": "SubagentStop",
                "session_id": sid,
                "agent_id": "agent-rev-plugin",
                "agent_type": agent_type,
                "last_assistant_message": BLOCKING_MESSAGE,
            },
            _env(tmp_path, plugin=True),
        )
        cache_file = tmp_path / f"writ-session-{sid}.json"
        state = (
            json.loads(cache_file.read_text()).get("review_findings_state")
            if cache_file.exists()
            else None
        )
        assert state is not None, f"the {agent_type} verdict was not recorded"
        assert len(state["verdict"]["critical"]) == 1


class TestReviewOrder:
    HOOK = "writ-sdd-review-order.sh"

    @pytest.mark.parametrize(
        "subagent_type",
        ["writ-code-quality-reviewer", "writ:writ-code-quality-reviewer"],
    )
    def test_quality_review_before_spec_review_is_denied(
        self, tmp_path: Path, subagent_type: str
    ) -> None:
        """The bare case proves the setup reaches the gate; the namespaced case is the fix."""
        sid = "sdd-namespaced"
        (tmp_path / f"writ-session-{sid}.json").write_text(
            json.dumps({"mode": "work", "current_phase": "implementation"})
        )
        result = _run(
            self.HOOK,
            _task(sid, subagent_type, description="Review code"),
            _env(tmp_path, plugin=True),
        )
        out = _hook_output(result.stdout)
        assert out.get("permissionDecision") == "deny"
        assert "ENF-PROC-SDD-001" in out["permissionDecisionReason"]
