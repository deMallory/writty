"""Vibe bridge (writ/harness/vibe.py): translation, script dispatch, merge, fail-closed.

Hook scripts here are stubs in a throwaway plugin root, so every assertion is about the
bridge and none about Writ's gates. The real scripts run in test_harness_vibe_hooks.py.
"""

from __future__ import annotations

import fcntl
import io
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

from writ.harness import vibe, vibe_context

REPO = Path(__file__).resolve().parent.parent
SHIM = REPO / "bin" / "writ-vibe-hook"
FIXTURES = REPO / "tests" / "fixtures" / "vibe" / "envelopes.jsonl"


@pytest.fixture(autouse=True)
def _vibe_home(tmp_path, monkeypatch):
    """Keeps every state refresh off the developer's own Vibe sessions."""
    monkeypatch.setenv("VIBE_HOME", str(tmp_path / "vibe-home"))

# Every stub logs what it received, so a test can read back the envelope and env.
_PRELUDE = """#!/bin/bash
IN=$(cat)
printf '%s' "$IN" > "$VIBE_TEST_LOG/{name}.$$.in.json"
printf '%s\\n%s\\n%s\\n' "$CLAUDE_PLUGIN_ROOT" "$WRIT_STRICT" "$(pwd -P)" > "$VIBE_TEST_LOG/{name}.$$.env"
"""


def _json_body(payload: dict, code: int = 0) -> str:
    return f"cat <<'JSON'\n{json.dumps(payload)}\nJSON\nexit {code}\n"


class Plugin:
    """A throwaway plugin root: hooks/hooks.json plus stub scripts."""

    def __init__(self, tmp_path: Path, groups: dict[str, list[dict]]):
        self.root = tmp_path / "plugin"
        self.log = tmp_path / "log"
        scripts = self.root / "hooks" / "scripts"
        scripts.mkdir(parents=True)
        self.log.mkdir()
        config: dict[str, list] = {}
        for event, entries in groups.items():
            config[event] = []
            for entry in entries:
                hooks = []
                for name, body in entry["scripts"].items():
                    (scripts / f"{name}.sh").write_text(_PRELUDE.format(name=name) + body)
                    hook = {"type": "command",
                            "command": f'bash "${{CLAUDE_PLUGIN_ROOT}}/hooks/scripts/{name}.sh"'}
                    if "timeout" in entry:
                        hook["timeout"] = entry["timeout"]
                    hooks.append(hook)
                config[event].append({"matcher": entry["matcher"], "hooks": hooks})
        (self.root / "hooks" / "hooks.json").write_text(json.dumps({"hooks": config}))

    def env(self) -> dict:
        return {**os.environ, "VIBE_TEST_LOG": str(self.log)}

    def runs(self, name: str) -> list[dict]:
        return [json.loads(p.read_text()) for p in sorted(self.log.glob(f"{name}.*.in.json"))]

    def envs(self, name: str) -> list[list[str]]:
        return [p.read_text().splitlines() for p in sorted(self.log.glob(f"{name}.*.env"))]


def _handle(plugin: Plugin, event: str, envelope: dict | str, *, sid: str | None = "sid-1",
            resolver=None, context_dir: Path | None = None) -> str:
    raw = envelope if isinstance(envelope, str) else json.dumps(envelope)
    return vibe.handle(
        event, raw,
        plugin_root=str(plugin.root),
        base_env=plugin.env(),
        session_resolver=resolver or (lambda _env: sid),
        context_dir=str(context_dir or plugin.log / "ctx"),
    )


def _pre(cwd: Path, tool: str, tool_input: dict, call_id: str = "call1") -> dict:
    return {"cwd": str(cwd), "hook_event_name": "pre_tool", "tool_name": tool,
            "tool_call_id": call_id, "tool_input": tool_input}


def _post(cwd: Path, tool: str, tool_input: dict, *, call_id: str = "call1",
          status: str = "success", output=None, text: str = "", error=None) -> dict:
    return {**_pre(cwd, tool, tool_input, call_id), "hook_event_name": "post_tool",
            "tool_status": status, "tool_output": output, "tool_output_text": text,
            "tool_error": error, "duration_ms": 0}


def _deny_reason(out: str) -> str:
    data = json.loads(out)
    assert data["decision"] == "deny", data
    return data["reason"]


ALLOW = "exit 0\n"


# --------------------------------------------------------------------------- #
# Envelope translation
# --------------------------------------------------------------------------- #
class TestToClaude:
    def test_unified_write_relative_path_becomes_absolute_claude_write(self, tmp_path):
        plugin = Plugin(tmp_path, {"PreToolUse": [{"matcher": "Write", "scripts": {"w": ALLOW}}]})
        out = _handle(plugin, "pre_tool",
                      _pre(tmp_path, "file_system.write_file",
                           {"path": "src/a.py", "content": "x = 1\n"}, call_id="abc"))
        assert out == ""
        [seen] = plugin.runs("w")
        assert seen["hook_event_name"] == "PreToolUse"
        assert seen["tool_name"] == "Write"
        assert seen["tool_input"]["file_path"] == str(tmp_path / "src" / "a.py")
        assert seen["tool_input"]["content"] == "x = 1\n"
        assert seen["tool_use_id"] == "abc"
        assert seen["session_id"] == "sid-1"
        assert seen["transcript_path"] == ""
        assert seen["cwd"] == str(tmp_path)

    @pytest.mark.parametrize("tool, tool_input, claude_tool, expected", [
        ("file_system.read_file", {"path": "a.txt", "offset": 0, "limit": 10},
         "Read", {"file_path": "{cwd}/a.txt", "offset": 0, "limit": 10}),
        ("read_file", {"file_path": "/abs/a.txt", "offset": 0, "limit": 10},
         "Read", {"file_path": "/abs/a.txt"}),
        ("file_system.bash", {"command": "ls", "timeout_seconds": 5}, "Bash", {"command": "ls"}),
        ("bash", {"command": "ls", "timeout": 5}, "Bash", {"command": "ls"}),
        ("process.start", {"command": "make", "cwd": "", "env": {}}, "Bash", {"command": "make"}),
        ("grep", {"pattern": "x", "path": "src"}, "Grep", {"pattern": "x", "path": "{cwd}/src"}),
        ("edit", {"file_path": "a.py", "old_string": "a", "new_string": "b", "replace_all": False},
         "Edit", {"file_path": "{cwd}/a.py", "old_string": "a", "new_string": "b",
                  "replace_all": False}),
        ("write_file", {"file_path": "a.py", "content": "c"},
         "Write", {"file_path": "{cwd}/a.py", "content": "c"}),
        ("file_system.search_replace",
         {"file_path": "a.py", "content": [{"old_str": "a", "new_str": "b", "replace_all": True}]},
         "Edit", {"file_path": "{cwd}/a.py", "old_string": "a", "new_string": "b",
                  "replace_all": True}),
    ])
    def test_tool_map(self, tmp_path, tool, tool_input, claude_tool, expected):
        [env] = vibe.to_claude(_pre(tmp_path, tool, tool_input), "pre_tool", "sid-1")
        assert env["hook_event_name"] == "PreToolUse"
        assert env["tool_name"] == claude_tool
        for key, value in expected.items():
            if isinstance(value, str):
                value = value.replace("{cwd}", str(tmp_path))
            assert env["tool_input"][key] == value, key

    def test_search_replace_two_blocks_yield_two_edits(self, tmp_path):
        blocks = [{"old_str": "a", "new_str": "b"}, {"old_str": "c", "new_str": "d"}]
        envs = vibe.to_claude(
            _pre(tmp_path, "file_system.search_replace", {"file_path": "a.py", "content": blocks}),
            "pre_tool", "sid-1")
        assert [e["tool_input"]["old_string"] for e in envs] == ["a", "c"]
        assert [e["tool_input"]["new_string"] for e in envs] == ["b", "d"]
        assert {e["tool_name"] for e in envs} == {"Edit"}

    @pytest.mark.parametrize("tool, tool_input", [
        ("subagent.wait", {"agentName": "h", "timeoutMs": 1000}),
        ("task", {"agent": "explore", "task": "t"}),
        ("skill.read", {"name": "s"}),
    ])
    def test_unmapped_tool_runs_no_script(self, tmp_path, tool, tool_input):
        plugin = Plugin(tmp_path, {"PreToolUse": [{"matcher": ".*", "scripts": {"all": ALLOW}}]})
        assert vibe.to_claude(_pre(tmp_path, tool, tool_input), "pre_tool", "sid-1") == []
        assert _handle(plugin, "pre_tool", _pre(tmp_path, tool, tool_input)) == ""
        assert plugin.runs("all") == []

    def test_post_envelope_carries_tool_response_and_text(self, tmp_path):
        output = {"command": "echo hi", "returncode": 0, "stderr": "", "stdout": "hi\n"}
        [env] = vibe.to_claude(
            _post(tmp_path, "file_system.bash", {"command": "echo hi"}, output=output,
                  text="stdout: hi"), "post_tool", "sid-1")
        assert env["hook_event_name"] == "PostToolUse"
        assert env["tool_response"] == output
        assert env["tool_output"] == "stdout: hi"

    def test_post_failure_becomes_post_tool_use_failure(self, tmp_path):
        [env] = vibe.to_claude(
            _post(tmp_path, "file_system.bash", {"command": "false"}, status="failure",
                  error="exit 1"), "post_tool", "sid-1")
        assert env["hook_event_name"] == "PostToolUseFailure"
        assert env["error"] == "exit 1"


# --------------------------------------------------------------------------- #
# Script selection and execution
# --------------------------------------------------------------------------- #
class TestDispatch:
    def test_only_fullmatching_groups_run(self, tmp_path):
        plugin = Plugin(tmp_path, {"PreToolUse": [
            {"matcher": "Write", "scripts": {"w": ALLOW}},
            {"matcher": "Read", "scripts": {"r": ALLOW}},
            {"matcher": "Write|Edit", "scripts": {"we": ALLOW}},
            {"matcher": "Writ", "scripts": {"prefix": ALLOW}},
            {"matcher": "", "scripts": {"any": ALLOW}},
        ]})
        _handle(plugin, "pre_tool", _pre(tmp_path, "file_system.write_file",
                                         {"path": "a.py", "content": ""}))
        assert len(plugin.runs("w")) == 1
        assert len(plugin.runs("we")) == 1
        assert len(plugin.runs("any")) == 1
        assert plugin.runs("r") == []
        assert plugin.runs("prefix") == []

    def test_post_failure_selects_failure_groups(self, tmp_path):
        plugin = Plugin(tmp_path, {
            "PostToolUse": [{"matcher": "Bash", "scripts": {"ok": ALLOW}}],
            "PostToolUseFailure": [{"matcher": "Bash", "scripts": {"fail": ALLOW}}],
        })
        _handle(plugin, "post_tool", _post(tmp_path, "file_system.bash", {"command": "false"},
                                           status="failure", error="exit 1"))
        assert len(plugin.runs("fail")) == 1
        assert plugin.runs("ok") == []

    def test_scripts_get_plugin_root_strict_flag_and_envelope_cwd(self, tmp_path):
        work = tmp_path / "proj"
        work.mkdir()
        plugin = Plugin(tmp_path, {"PreToolUse": [{"matcher": "Bash", "scripts": {"b": ALLOW}}]})
        _handle(plugin, "pre_tool", _pre(work, "file_system.bash", {"command": "ls"}))
        [[root, strict, cwd]] = plugin.envs("b")
        assert root == str(plugin.root)
        assert strict == "1"
        assert os.path.realpath(cwd) == os.path.realpath(work)

    def test_scripts_run_in_parallel(self, tmp_path):
        plugin = Plugin(tmp_path, {"PreToolUse": [
            {"matcher": "Bash", "scripts": {"s1": "sleep 1\n"}},
            {"matcher": "Bash", "scripts": {"s2": "sleep 1\n"}},
        ]})
        start = time.monotonic()
        assert _handle(plugin, "pre_tool", _pre(tmp_path, "file_system.bash",
                                                {"command": "ls"})) == ""
        assert time.monotonic() - start < 1.8

    def test_search_replace_deny_on_second_block_denies_call(self, tmp_path):
        body = 'case "$IN" in *BAD*) echo "bad block" >&2; exit 2;; esac\nexit 0\n'
        plugin = Plugin(tmp_path, {"PreToolUse": [{"matcher": "Edit", "scripts": {"e": body}}]})
        blocks = [{"old_str": "a", "new_str": "ok"}, {"old_str": "c", "new_str": "BAD"}]
        out = _handle(plugin, "pre_tool", _pre(tmp_path, "file_system.search_replace",
                                               {"file_path": "a.py", "content": blocks}))
        assert "bad block" in _deny_reason(out)
        assert len(plugin.runs("e")) == 2


# --------------------------------------------------------------------------- #
# Reading script answers (pre_tool)
# --------------------------------------------------------------------------- #
class TestPreDecisions:
    @pytest.mark.parametrize("body, needle", [
        (_json_body({"hookSpecificOutput": {"hookEventName": "PreToolUse",
                                            "permissionDecision": "deny",
                                            "permissionDecisionReason": "R-DENY"}}), "R-DENY"),
        (_json_body({"hookSpecificOutput": {"hookEventName": "PreToolUse",
                                            "permissionDecision": "ask",
                                            "permissionDecisionReason": "R-ASK"}}), "R-ASK"),
        (_json_body({"decision": "block", "reason": "R-BLOCK"}), "R-BLOCK"),
        (_json_body({"decision": "deny", "reason": "R-DUAL"}), "R-DUAL"),
        (_json_body({"continue": False, "stopReason": "R-STOP"}), "R-STOP"),
        ('echo "R-EXIT2" >&2\nexit 2\n', "R-EXIT2"),
    ])
    def test_deny_shapes(self, tmp_path, body, needle):
        plugin = Plugin(tmp_path, {"PreToolUse": [{"matcher": "Bash", "scripts": {"g": body}}]})
        out = _handle(plugin, "pre_tool", _pre(tmp_path, "file_system.bash", {"command": "ls"}))
        assert needle in _deny_reason(out)

    def test_ask_reason_says_vibe_cannot_ask(self, tmp_path):
        body = _json_body({"hookSpecificOutput": {"hookEventName": "PreToolUse",
                                                  "permissionDecision": "ask",
                                                  "permissionDecisionReason": "confirm?"}})
        plugin = Plugin(tmp_path, {"PreToolUse": [{"matcher": "Bash", "scripts": {"g": body}}]})
        out = _handle(plugin, "pre_tool", _pre(tmp_path, "file_system.bash", {"command": "ls"}))
        assert "cannot ask" in _deny_reason(out).lower()

    def test_non_json_stdout_is_ignored(self, tmp_path):
        plugin = Plugin(tmp_path, {"PreToolUse": [
            {"matcher": "Bash", "scripts": {"g": "echo plain text\nexit 0\n"}}]})
        assert _handle(plugin, "pre_tool", _pre(tmp_path, "file_system.bash",
                                                {"command": "ls"})) == ""

    def test_two_denies_join_in_hooks_json_order(self, tmp_path):
        plugin = Plugin(tmp_path, {"PreToolUse": [
            {"matcher": "Bash", "scripts": {"first": 'echo "REASON-ONE" >&2\nexit 2\n'}},
            {"matcher": "Bash", "scripts": {"second": 'echo "REASON-TWO" >&2\nexit 2\n'}},
        ]})
        reason = _deny_reason(_handle(plugin, "pre_tool",
                                      _pre(tmp_path, "file_system.bash", {"command": "ls"})))
        assert reason.index("REASON-ONE") < reason.index("REASON-TWO")


# --------------------------------------------------------------------------- #
# Fail closed (pre_tool) and fail quiet (post_tool)
# --------------------------------------------------------------------------- #
def _raise(_env):
    raise RuntimeError("bridge exploded")


class TestFailClosed:
    def test_unparseable_envelope_denies(self, tmp_path):
        plugin = Plugin(tmp_path, {})
        _deny_reason(_handle(plugin, "pre_tool", "not json"))

    def test_unresolved_session_denies(self, tmp_path):
        plugin = Plugin(tmp_path, {"PreToolUse": [{"matcher": "Bash", "scripts": {"b": ALLOW}}]})
        out = _handle(plugin, "pre_tool", _pre(tmp_path, "file_system.bash", {"command": "ls"}),
                      sid=None)
        assert "session" in _deny_reason(out).lower()
        assert plugin.runs("b") == []

    def test_script_exit_1_denies_and_names_script(self, tmp_path):
        plugin = Plugin(tmp_path, {"PreToolUse": [
            {"matcher": "Bash", "scripts": {"crashy": "exit 1\n"}}]})
        out = _handle(plugin, "pre_tool", _pre(tmp_path, "file_system.bash", {"command": "ls"}))
        assert "crashy" in _deny_reason(out)

    def test_script_timeout_denies_without_waiting_it_out(self, tmp_path):
        plugin = Plugin(tmp_path, {"PreToolUse": [
            {"matcher": "Bash", "timeout": 1, "scripts": {"slow": "sleep 5\n"}}]})
        start = time.monotonic()
        out = _handle(plugin, "pre_tool", _pre(tmp_path, "file_system.bash", {"command": "ls"}))
        assert "slow" in _deny_reason(out)
        assert time.monotonic() - start < 4

    def test_bridge_exception_denies(self, tmp_path):
        plugin = Plugin(tmp_path, {"PreToolUse": [{"matcher": "Bash", "scripts": {"b": ALLOW}}]})
        out = _handle(plugin, "pre_tool", _pre(tmp_path, "file_system.bash", {"command": "ls"}),
                      resolver=_raise)
        _deny_reason(out)

    def test_shim_denies_garbage_and_exits_zero(self):
        proc = subprocess.run([sys.executable, str(SHIM), "pre_tool"], input="garbage",
                              capture_output=True, text=True, timeout=30)
        assert proc.returncode == 0
        _deny_reason(proc.stdout)

    def test_shim_allows_unmapped_tool_and_exits_zero(self, tmp_path):
        proc = subprocess.run([sys.executable, str(SHIM), "pre_tool"],
                              input=json.dumps(_pre(tmp_path, "subagent.wait", {})),
                              capture_output=True, text=True, timeout=30)
        assert proc.returncode == 0
        assert proc.stdout.strip() == ""

    @pytest.mark.parametrize("case", ["garbage", "script_exit_1", "bridge_exception"])
    def test_post_errors_print_nothing(self, tmp_path, case):
        plugin = Plugin(tmp_path, {"PostToolUse": [
            {"matcher": "Bash", "scripts": {"p": "exit 1\n" if case == "script_exit_1" else ALLOW}}]})
        envelope = "garbage" if case == "garbage" else _post(
            tmp_path, "file_system.bash", {"command": "ls"}, output={"stdout": "x"})
        out = _handle(plugin, "post_tool", envelope,
                      resolver=_raise if case == "bridge_exception" else None)
        assert out == ""


# --------------------------------------------------------------------------- #
# Rewrites (pre_tool updatedInput -> Vibe tool_input)
# --------------------------------------------------------------------------- #
def _rewrite(updated: dict) -> str:
    return _json_body({"hookSpecificOutput": {"hookEventName": "PreToolUse",
                                              "permissionDecision": "allow",
                                              "updatedInput": updated}})


class TestRewrites:
    def test_bash_rewrite_keeps_vibe_names(self, tmp_path):
        plugin = Plugin(tmp_path, {"PreToolUse": [
            {"matcher": "Bash", "scripts": {"b": _rewrite({"command": "safe"})}}]})
        out = json.loads(_handle(plugin, "pre_tool", _pre(
            tmp_path, "file_system.bash", {"command": "orig", "timeout_seconds": 5})))
        assert out["decision"] == "allow"
        assert out["hook_specific_output"]["tool_input"] == {"command": "safe",
                                                             "timeout_seconds": 5}

    @pytest.mark.parametrize("tool, path_key", [
        ("file_system.write_file", "path"),
        ("write_file", "file_path"),
    ])
    def test_write_rewrite_uses_the_original_path_key(self, tmp_path, tool, path_key):
        target = str(tmp_path / "a.py")
        plugin = Plugin(tmp_path, {"PreToolUse": [{"matcher": "Write", "scripts": {
            "w": _rewrite({"file_path": target, "content": "NEW"})}}]})
        out = json.loads(_handle(plugin, "pre_tool",
                                 _pre(tmp_path, tool, {path_key: target, "content": "old"})))
        assert out["hook_specific_output"]["tool_input"] == {path_key: target, "content": "NEW"}

    def test_single_block_search_replace_rewrite(self, tmp_path):
        target = str(tmp_path / "a.py")
        plugin = Plugin(tmp_path, {"PreToolUse": [{"matcher": "Edit", "scripts": {
            "e": _rewrite({"file_path": target, "old_string": "a", "new_string": "B2",
                           "replace_all": False})}}]})
        out = json.loads(_handle(plugin, "pre_tool", _pre(
            tmp_path, "file_system.search_replace",
            {"file_path": target, "content": [{"old_str": "a", "new_str": "b"}]})))
        [block] = out["hook_specific_output"]["tool_input"]["content"]
        assert block["old_str"] == "a"
        assert block["new_str"] == "B2"

    def test_multi_block_rewrite_denies(self, tmp_path):
        target = str(tmp_path / "a.py")
        plugin = Plugin(tmp_path, {"PreToolUse": [{"matcher": "Edit", "scripts": {
            "e": _rewrite({"file_path": target, "old_string": "x", "new_string": "y"})}}]})
        blocks = [{"old_str": "a", "new_str": "b"}, {"old_str": "c", "new_str": "d"}]
        _deny_reason(_handle(plugin, "pre_tool", _pre(
            tmp_path, "file_system.search_replace", {"file_path": target, "content": blocks})))

    def test_rewrite_of_unmapped_key_denies(self, tmp_path):
        plugin = Plugin(tmp_path, {"PreToolUse": [{"matcher": "Bash", "scripts": {
            "b": _rewrite({"command": "orig", "run_in_background": True})}}]})
        _deny_reason(_handle(plugin, "pre_tool",
                             _pre(tmp_path, "file_system.bash", {"command": "orig"})))


# --------------------------------------------------------------------------- #
# post_tool translation and deferred pre-tool context
# --------------------------------------------------------------------------- #
class TestPost:
    def _bash_post(self, tmp_path, call_id="call1"):
        return _post(tmp_path, "file_system.bash", {"command": "ls"}, call_id=call_id,
                     output={"stdout": "x" * 50, "stderr": ""}, text="stdout: ...")

    def test_additional_context_is_passed_through(self, tmp_path):
        plugin = Plugin(tmp_path, {"PostToolUse": [{"matcher": "Bash", "scripts": {"p": _json_body(
            {"hookSpecificOutput": {"hookEventName": "PostToolUse",
                                    "additionalContext": "CTX-1"}})}}]})
        out = json.loads(_handle(plugin, "post_tool", self._bash_post(tmp_path)))
        assert "CTX-1" in out["hook_specific_output"]["additional_context"]
        assert out.get("decision") != "deny"

    def test_post_block_reason_is_appended_not_denied(self, tmp_path):
        plugin = Plugin(tmp_path, {"PostToolUse": [{"matcher": "Bash", "scripts": {
            "p": _json_body({"decision": "block", "reason": "FIX-THIS"})}}]})
        out = json.loads(_handle(plugin, "post_tool", self._bash_post(tmp_path)))
        assert out.get("decision") != "deny"
        assert "FIX-THIS" in out["hook_specific_output"]["additional_context"]

    def test_updated_tool_output_replaces_result(self, tmp_path):
        plugin = Plugin(tmp_path, {"PostToolUse": [{"matcher": "Bash", "scripts": {"p": _json_body(
            {"hookSpecificOutput": {"hookEventName": "PostToolUse",
                                    "updatedToolOutput": {"stdout": "short", "stderr": ""}}})}}]})
        reason = _deny_reason(_handle(plugin, "post_tool", self._bash_post(tmp_path)))
        assert "stdout: short" in reason

    def test_pre_context_is_emitted_once_in_matching_post(self, tmp_path):
        ctx = tmp_path / "ctx"
        plugin = Plugin(tmp_path, {
            "PreToolUse": [{"matcher": "Read", "scripts": {"rag": _json_body(
                {"hookSpecificOutput": {"hookEventName": "PreToolUse",
                                        "permissionDecision": "allow",
                                        "additionalContext": "RULES-X"}})}}],
            "PostToolUse": [{"matcher": "Read", "scripts": {"p": ALLOW}}],
        })
        read_in = {"path": "a.txt"}
        pre_out = _handle(plugin, "pre_tool",
                          _pre(tmp_path, "file_system.read_file", read_in, call_id="r1"),
                          context_dir=ctx)
        assert "RULES-X" not in pre_out
        post = _post(tmp_path, "file_system.read_file", read_in, call_id="r1",
                     output={"content": "hi"}, text="content: hi")
        first = json.loads(_handle(plugin, "post_tool", post, context_dir=ctx))
        assert "RULES-X" in first["hook_specific_output"]["additional_context"]
        assert "RULES-X" not in _handle(plugin, "post_tool", post, context_dir=ctx)
        assert [p for p in ctx.rglob("*") if p.is_file()] == []


# --------------------------------------------------------------------------- #
# Session id resolution
# --------------------------------------------------------------------------- #
class TestSessionId:
    CHAIN = {300: 200, 200: 100, 100: 1}

    def _lock(self, home: Path, sid: str, pid: int, live: bool, held: list) -> None:
        active = home / "logs" / "session" / "active"
        active.mkdir(parents=True, exist_ok=True)
        (active / f"{sid}.lock.json").write_text(json.dumps({"process_id": pid}))
        lock = active / f"{sid}.lock"
        lock.write_text("")
        if live:
            handle = open(lock)
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
            held.append(handle)

    def _resolve(self, home: Path, envelope: dict | None = None):
        return vibe.resolve_session_id(envelope or {}, vibe_home=str(home), start_pid=300,
                                       parent_of=self.CHAIN.get)

    def test_payload_session_id_wins_without_walking(self, tmp_path):
        def boom(_pid):
            raise AssertionError("the pid-walk ran although the payload had a session id")

        assert vibe.resolve_session_id({"session_id": "leg-1"}, vibe_home=str(tmp_path),
                                       start_pid=300, parent_of=boom) == "leg-1"

    def test_walk_skips_child_and_dead_locks(self, tmp_path):
        held: list = []
        try:
            self._lock(tmp_path, "parent-sid", 200, True, held)
            self._lock(tmp_path, "child-abc", 200, True, held)
            self._lock(tmp_path, "dead-sid", 200, False, held)
            assert self._resolve(tmp_path) == "parent-sid"
        finally:
            for handle in held:
                handle.close()

    def test_two_live_candidates_are_unresolved(self, tmp_path):
        held: list = []
        try:
            self._lock(tmp_path, "one", 200, True, held)
            self._lock(tmp_path, "two", 200, True, held)
            assert self._resolve(tmp_path) is None
        finally:
            for handle in held:
                handle.close()

    def test_no_lock_in_the_chain_is_unresolved(self, tmp_path):
        held: list = []
        try:
            self._lock(tmp_path, "elsewhere", 999, True, held)
            assert self._resolve(tmp_path) is None
        finally:
            for handle in held:
                handle.close()


# --------------------------------------------------------------------------- #
# User-only commands (`!mistty approve` and the rest)
# --------------------------------------------------------------------------- #
_USER_ONLY_COMMANDS = [
    "mistty approve",
    "mistty replan",
    "mistty grant manual-test",
    "~/.local/bin/mistty approve",
    "MISTTY approve",
    "python3 -m writ.harness.vibe_user approve",
]


def _no_session_lookup(_env):
    raise AssertionError("the user-only deny must not need a session")


class TestUserOnlyCommands:
    @pytest.mark.parametrize("tool", ["bash", "file_system.bash", "process.start"])
    @pytest.mark.parametrize("command", _USER_ONLY_COMMANDS)
    def test_model_shell_call_running_a_user_command_is_denied(self, tmp_path, tool, command):
        plugin = Plugin(tmp_path, {"PreToolUse": [{"matcher": "Bash", "scripts": {"b": ALLOW}}]})
        out = _handle(plugin, "pre_tool", _pre(tmp_path, tool, {"command": command}),
                      resolver=_no_session_lookup)
        assert "!mistty" in _deny_reason(out)
        assert plugin.runs("b") == []

    @pytest.mark.parametrize("command", [
        "ls ~/dev/mistty",
        "mistty --version",
        ".venv/bin/python -m pytest tests/test_harness_vibe_user.py -q",
        # The model sets the mode itself, as it does under Claude Code.
        "mistty mode work",
        "writ mode set work sid-1",
    ])
    def test_other_commands_naming_mistty_reach_the_scripts(self, tmp_path, command):
        plugin = Plugin(tmp_path, {"PreToolUse": [{"matcher": "Bash", "scripts": {"b": ALLOW}}]})
        out = _handle(plugin, "pre_tool", _pre(tmp_path, "file_system.bash", {"command": command}))
        assert out == ""
        assert [r["tool_input"]["command"] for r in plugin.runs("b")] == [command]

    def test_a_write_mentioning_the_command_is_not_refused(self, tmp_path):
        plugin = Plugin(tmp_path, {"PreToolUse": [{"matcher": "Write", "scripts": {"w": ALLOW}}]})
        out = _handle(plugin, "pre_tool", _pre(
            tmp_path, "file_system.write_file",
            {"path": "notes.md", "content": "Type `!mistty approve` to advance.\n"}))
        assert out == ""
        assert len(plugin.runs("w")) == 1


# --------------------------------------------------------------------------- #
# process.write: typed input to a running process
# --------------------------------------------------------------------------- #
_SAFE_KEYS = ["ctrl_c", "ctrl_d", "ctrl_z", "esc", "enter"]


@pytest.fixture
def writ_cache(tmp_path, monkeypatch):
    """Points the bridge at a temp Writ session cache. seed(None) leaves sid-1 with no
    file, a dict is written as its JSON, a str is written as is."""
    cache = tmp_path / "writ-cache"
    cache.mkdir()
    monkeypatch.setenv("WRIT_CACHE_DIR", str(cache))

    def seed(state):
        if state is not None:
            body = state if isinstance(state, str) else json.dumps(state)
            (cache / "writ-session-sid-1.json").write_text(body)
    return seed


def _write(cwd: Path, tool_input: dict) -> dict:
    return _pre(cwd, "process.write", {"processId": "p1", **tool_input})


def _any_script(tmp_path: Path) -> Plugin:
    return Plugin(tmp_path, {"PreToolUse": [{"matcher": ".*", "scripts": {"all": ALLOW}}],
                             "PostToolUse": [{"matcher": ".*", "scripts": {"post": ALLOW}}]})


def _no_lookup(_env):
    raise AssertionError("this decision must not need a session")


class TestProcessWrite:
    @pytest.mark.parametrize("state, named", [
        ({"mode": "work"}, "work mode"),
        ({"mode": "debug"}, "debug mode"),
        (None, "no Writ mode"),
        ({"current_phase": "planning"}, "no Writ mode"),
        ("{not json", "no Writ mode"),
    ])
    def test_typed_text_is_denied_where_writ_gates_writes(self, tmp_path, writ_cache,
                                                          state, named):
        writ_cache(state)
        plugin = _any_script(tmp_path)
        reason = _deny_reason(_handle(plugin, "pre_tool",
                                      _write(tmp_path, {"text": "print(1)\n"})))
        assert named in reason
        for key in _SAFE_KEYS:
            assert key in reason
        assert plugin.runs("all") == []

    @pytest.mark.parametrize("tool_input", [
        {"bytesBase64": "cHJpbnQoMSkK"},
        {"control": ["up", "enter"]},
        {"control": ["down"]},
        {"control": ["tab"]},
        {"control": ["ctrl_c", {"key": "up"}]},
        {},
    ])
    def test_other_typed_input_is_denied_in_work_mode(self, tmp_path, writ_cache, tool_input):
        writ_cache({"mode": "work"})
        plugin = _any_script(tmp_path)
        assert "work mode" in _deny_reason(_handle(plugin, "pre_tool",
                                                   _write(tmp_path, tool_input)))
        assert plugin.runs("all") == []

    @pytest.mark.parametrize("keys", [["ctrl_c"], ["enter"], _SAFE_KEYS])
    def test_safe_keys_pass_in_work_mode_without_a_session_lookup(self, tmp_path, writ_cache,
                                                                  keys):
        writ_cache({"mode": "work"})
        plugin = _any_script(tmp_path)
        out = _handle(plugin, "pre_tool", _write(tmp_path, {"control": keys}),
                      resolver=_no_lookup)
        assert out == ""
        assert plugin.runs("all") == []

    @pytest.mark.parametrize("mode", ["conversation", "review", "investigate"])
    def test_typed_text_passes_where_writ_leaves_writes_open(self, tmp_path, writ_cache, mode):
        writ_cache({"mode": mode})
        plugin = _any_script(tmp_path)
        assert _handle(plugin, "pre_tool", _write(tmp_path, {"text": "print(1)\n"})) == ""
        assert plugin.runs("all") == []

    @pytest.mark.parametrize("command", _USER_ONLY_COMMANDS)
    def test_user_command_typed_into_a_process_is_denied_in_any_mode(self, tmp_path,
                                                                     writ_cache, command):
        writ_cache({"mode": "conversation"})
        plugin = _any_script(tmp_path)
        out = _handle(plugin, "pre_tool", _write(tmp_path, {"text": f"{command}\n"}),
                      resolver=_no_lookup)
        assert "!mistty" in _deny_reason(out)
        assert plugin.runs("all") == []

    def test_typed_input_without_a_session_gets_the_no_session_deny(self, tmp_path, writ_cache):
        writ_cache({"mode": "conversation"})
        plugin = _any_script(tmp_path)
        typed = _handle(plugin, "pre_tool", _write(tmp_path, {"text": "print(1)\n"}), sid=None)
        shell = _handle(plugin, "pre_tool",
                        _pre(tmp_path, "file_system.bash", {"command": "ls"}), sid=None)
        assert _deny_reason(typed) == _deny_reason(shell)
        assert plugin.runs("all") == []

    @pytest.mark.parametrize("tool_input", [{"text": "print(1)\n"}, {"control": ["ctrl_c"]}])
    def test_post_tool_returns_nothing_and_runs_no_script(self, tmp_path, writ_cache,
                                                          tool_input):
        writ_cache({"mode": "work"})
        plugin = _any_script(tmp_path)
        envelope = _post(tmp_path, "process.write", {"processId": "p1", **tool_input},
                         output={"ok": True})
        assert _handle(plugin, "post_tool", envelope, resolver=_no_lookup) == ""
        assert plugin.runs("all") == []
        assert plugin.runs("post") == []

    def test_typed_text_keeps_its_reason_word_for_word(self, tmp_path, writ_cache):
        writ_cache({"mode": "work"})
        plugin = _any_script(tmp_path)
        assert _deny_reason(_handle(plugin, "pre_tool", _write(tmp_path, {"text": "x\n"}))) == (
            "Writ refuses typed input to a running process in work mode: its shell checks "
            "cannot see what the process does with it. Only the keys ctrl_c, ctrl_d, ctrl_z, "
            "esc and enter go through. Pass the input as a flag (`--yes`) or pipe it in "
            "through bash (`printf 'y\\n' | cmd`), which Writ checks."
        )


# --------------------------------------------------------------------------- #
# Subagents: the bridge decides the calls that hand a child work
# --------------------------------------------------------------------------- #
_SUBAGENT_WORK = ["subagent.spawn", "subagent.send_message"]


def _child(cwd: Path, tool: str, message: str = "Read notes.txt and summarise it") -> dict:
    return _pre(cwd, tool, {"agentName": "helper1", "message": message})


class TestSubagent:
    @pytest.mark.parametrize("tool", _SUBAGENT_WORK)
    @pytest.mark.parametrize("state, named", [
        ({"mode": "work"}, "in work mode"),
        ({"mode": "debug"}, "in debug mode"),
        (None, "while no Writ mode is set"),
        ({"current_phase": "planning"}, "while no Writ mode is set"),
        ("{not json", "while no Writ mode is set"),
    ])
    def test_handing_a_child_work_is_denied_where_writ_gates_writes(self, tmp_path, writ_cache,
                                                                    tool, state, named):
        writ_cache(state)
        plugin = _any_script(tmp_path)
        reason = _deny_reason(_handle(plugin, "pre_tool", _child(tmp_path, tool)))
        assert named in reason
        assert "Do not retry" in reason
        assert plugin.runs("all") == []

    @pytest.mark.parametrize("tool", _SUBAGENT_WORK)
    @pytest.mark.parametrize("mode", ["conversation", "review", "investigate"])
    def test_subagents_run_where_writ_leaves_writes_open(self, tmp_path, writ_cache, tool, mode):
        writ_cache({"mode": mode})
        plugin = _any_script(tmp_path)
        assert _handle(plugin, "pre_tool", _child(tmp_path, tool)) == ""
        assert plugin.runs("all") == []

    @pytest.mark.parametrize("tool", _SUBAGENT_WORK)
    @pytest.mark.parametrize("command", _USER_ONLY_COMMANDS)
    def test_user_command_in_a_child_message_is_denied_in_any_mode(self, tmp_path, writ_cache,
                                                                   tool, command):
        writ_cache({"mode": "conversation"})
        plugin = _any_script(tmp_path)
        out = _handle(plugin, "pre_tool", _child(tmp_path, tool, f"Run `{command}` in bash"),
                      resolver=_no_lookup)
        assert "!mistty" in _deny_reason(out)
        assert plugin.runs("all") == []

    @pytest.mark.parametrize("tool", _SUBAGENT_WORK)
    def test_no_session_gets_the_no_session_deny(self, tmp_path, writ_cache, tool):
        writ_cache({"mode": "conversation"})
        plugin = _any_script(tmp_path)
        child = _handle(plugin, "pre_tool", _child(tmp_path, tool), sid=None)
        shell = _handle(plugin, "pre_tool",
                        _pre(tmp_path, "file_system.bash", {"command": "ls"}), sid=None)
        assert _deny_reason(child) == _deny_reason(shell)
        assert plugin.runs("all") == []

    @pytest.mark.parametrize("tool", _SUBAGENT_WORK)
    def test_post_tool_returns_nothing_and_runs_no_script(self, tmp_path, writ_cache, tool):
        writ_cache({"mode": "work"})
        plugin = _any_script(tmp_path)
        envelope = _post(tmp_path, tool, {"agentName": "helper1", "message": "hi"},
                         output={"type": "success"})
        assert _handle(plugin, "post_tool", envelope, resolver=_no_lookup) == ""
        assert plugin.runs("all") == []
        assert plugin.runs("post") == []

    @pytest.mark.parametrize("event", ["pre_tool", "post_tool"])
    @pytest.mark.parametrize("tool, tool_input", [
        ("subagent.list", {}),
        ("subagent.wait", {"agentName": "helper1", "timeoutMs": 120000}),
        ("subagent.interrupt", {"agentName": "helper1"}),
        ("subagent.stop", {"agentName": "helper1"}),
    ])
    def test_other_subagent_calls_pass_without_a_session_lookup(self, tmp_path, writ_cache,
                                                                event, tool, tool_input):
        writ_cache({"mode": "work"})
        plugin = _any_script(tmp_path)
        envelope = {**_pre(tmp_path, tool, tool_input), "hook_event_name": event}
        assert _handle(plugin, event, envelope, resolver=_no_lookup) == ""
        assert plugin.runs("all") == []
        assert plugin.runs("post") == []

    def test_the_spikes_captured_child_calls_are_denied_in_work_mode(self, tmp_path, writ_cache):
        writ_cache({"mode": "work"})
        plugin = _any_script(tmp_path)
        rows = [r["envelope"] for r in _CAPTURED
                if r["envelope"]["hook_event_name"] == "pre_tool"
                and r["envelope"]["tool_name"] in _SUBAGENT_WORK]
        assert {e["tool_name"] for e in rows} == set(_SUBAGENT_WORK)
        assert any("secret.txt" in e["tool_input"]["message"] for e in rows)
        for envelope in rows:
            assert "in work mode" in _deny_reason(_handle(plugin, "pre_tool", envelope))
        assert plugin.runs("all") == []


# --------------------------------------------------------------------------- #
# Writ's state file in the scratchpad: refreshed after each tool call
# --------------------------------------------------------------------------- #
@pytest.fixture
def refreshes(monkeypatch):
    """Records every state refresh instead of running it."""
    calls: list[tuple[str, dict]] = []

    def fake(sid, **kwargs):
        calls.append((sid, kwargs))
        return True
    monkeypatch.setattr(vibe_context, "refresh", fake)
    return calls


def _bash_post(cwd: Path) -> dict:
    return _post(cwd, "file_system.bash", {"command": "ls"}, output={"stdout": "x"},
                 text="stdout: x")


class TestStateRefresh:
    def test_post_tool_refreshes_after_the_scripts_ran(self, tmp_path, monkeypatch):
        plugin = Plugin(tmp_path, {"PostToolUse": [{"matcher": "Bash", "scripts": {"p": ALLOW}}]})
        seen = []

        def fake(sid, **kwargs):
            seen.append((sid, kwargs["plugin_root"], len(plugin.runs("p"))))
            return True
        monkeypatch.setattr(vibe_context, "refresh", fake)
        _handle(plugin, "post_tool", _bash_post(tmp_path))
        assert seen == [("sid-1", str(plugin.root), 1)]

    @pytest.mark.parametrize("tool, tool_input", [
        ("file_system.write_file", {"path": "a.py", "content": ""}),
        ("file_system.read_file", {"path": "a.py"}),
        ("grep", {"pattern": "x"}),
        ("process.start", {"command": "make"}),
    ])
    def test_every_mapped_tool_refreshes(self, tmp_path, refreshes, tool, tool_input):
        plugin = _any_script(tmp_path)
        _handle(plugin, "post_tool", _post(tmp_path, tool, tool_input, output={"ok": True}))
        assert [sid for sid, _ in refreshes] == ["sid-1"]

    def test_pre_tool_does_not_refresh(self, tmp_path, refreshes):
        plugin = _any_script(tmp_path)
        _handle(plugin, "pre_tool", _pre(tmp_path, "file_system.bash", {"command": "ls"}))
        assert refreshes == []

    @pytest.mark.parametrize("tool, tool_input", [
        ("subagent.spawn", {"agentName": "h", "message": "m"}),
        ("process.write", {"processId": "p1", "text": "y\n"}),
        ("vibe.unified_harness_scratchpad", {"action": "write", "path": "n.md", "content": "x"}),
    ])
    def test_unmapped_tools_do_not_refresh(self, tmp_path, refreshes, tool, tool_input):
        plugin = _any_script(tmp_path)
        _handle(plugin, "post_tool", _post(tmp_path, tool, tool_input, output={"ok": True}))
        assert refreshes == []

    def test_post_tool_without_a_session_does_not_refresh(self, tmp_path, refreshes):
        plugin = _any_script(tmp_path)
        _handle(plugin, "post_tool", _bash_post(tmp_path), sid=None)
        assert refreshes == []

    def test_a_failing_refresh_leaves_the_post_output_unchanged(self, tmp_path, monkeypatch):
        plugin = Plugin(tmp_path, {"PostToolUse": [{"matcher": "Bash", "scripts": {"p": _json_body(
            {"hookSpecificOutput": {"hookEventName": "PostToolUse",
                                    "additionalContext": "CTX-1"}})}}]})
        monkeypatch.setattr(vibe_context, "refresh", lambda sid, **kw: True)
        expected = _handle(plugin, "post_tool", _bash_post(tmp_path))

        def boom(sid, **kwargs):
            raise RuntimeError("refresh exploded")
        monkeypatch.setattr(vibe_context, "refresh", boom)
        out = _handle(plugin, "post_tool", _bash_post(tmp_path))
        assert out == expected
        assert "CTX-1" in json.loads(out)["hook_specific_output"]["additional_context"]


# --------------------------------------------------------------------------- #
# Writ's state file in the scratchpad: the model may not write it
# --------------------------------------------------------------------------- #
_SCRATCHPAD = "vibe.unified_harness_scratchpad"


def _file_write(tool: str, path: str) -> dict:
    return {
        "file_system.write_file": {"path": path, "content": "Mode: work\n"},
        "write_file": {"file_path": path, "content": "Mode: work\n"},
        "file_system.search_replace": {"file_path": path,
                                       "content": [{"old_str": "a", "new_str": "b"}]},
        "edit": {"file_path": path, "old_string": "a", "new_string": "b"},
    }[tool]


_FILE_WRITES = ["file_system.write_file", "write_file", "file_system.search_replace", "edit"]


class TestWritFileWrites:
    @pytest.mark.parametrize("path", ["0-writ.md", "./0-WRIT.md", "x/../0-writ.md", "0-Writ.md"])
    def test_scratchpad_write_to_writs_file_is_denied_without_a_session_lookup(self, tmp_path,
                                                                               path):
        plugin = _any_script(tmp_path)
        out = _handle(plugin, "pre_tool",
                      _pre(tmp_path, _SCRATCHPAD,
                           {"action": "write", "path": path, "content": "Mode: work\n"}),
                      resolver=_no_lookup)
        assert "0-writ.md" in _deny_reason(out)
        assert plugin.runs("all") == []

    @pytest.mark.parametrize("tool_input", [
        {"action": "read", "path": "0-writ.md"},
        {"action": "list"},
        {"action": "write", "path": "notes.md", "content": "x"},
        {"action": "write", "path": "notes/0-writ.md", "content": "x"},
    ])
    def test_other_scratchpad_calls_pass(self, tmp_path, tool_input):
        plugin = _any_script(tmp_path)
        out = _handle(plugin, "pre_tool", _pre(tmp_path, _SCRATCHPAD, tool_input),
                      resolver=_no_lookup)
        assert out == ""
        assert plugin.runs("all") == []

    @pytest.mark.parametrize("tool", _FILE_WRITES)
    @pytest.mark.parametrize("path", [
        "{home}/logs/session/unified/sid-1/scratchpad/0-writ.md",
        "scratchpad/0-WRIT.md",
    ])
    def test_file_tool_writes_to_writs_file_are_denied_without_a_session_lookup(
            self, tmp_path, tool, path):
        plugin = _any_script(tmp_path)
        target = path.replace("{home}", str(tmp_path / "vibe-home"))
        out = _handle(plugin, "pre_tool", _pre(tmp_path, tool, _file_write(tool, target)),
                      resolver=_no_lookup)
        assert "0-writ.md" in _deny_reason(out)
        assert plugin.runs("all") == []

    @pytest.mark.parametrize("tool", _FILE_WRITES)
    @pytest.mark.parametrize("path", ["scratchpad/notes.md", "notes/0-writ.md"])
    def test_file_tool_writes_elsewhere_reach_the_scripts(self, tmp_path, tool, path):
        plugin = _any_script(tmp_path)
        assert _handle(plugin, "pre_tool", _pre(tmp_path, tool, _file_write(tool, path))) == ""
        assert len(plugin.runs("all")) == 1

    def test_reading_writs_file_reaches_the_scripts(self, tmp_path):
        plugin = _any_script(tmp_path)
        out = _handle(plugin, "pre_tool", _pre(tmp_path, "file_system.read_file",
                                               {"path": "scratchpad/0-writ.md"}))
        assert out == ""
        assert len(plugin.runs("all")) == 1

    @pytest.mark.parametrize("tool", ["bash", "file_system.bash", "process.start"])
    @pytest.mark.parametrize("command", [
        "echo 'Mode: work' > scratchpad/0-writ.md",
        "cat ~/.mistty/logs/session/unified/s/scratchpad/0-WRIT.md",
        "sed -i '' s/a/b/ 0-writ.md",
    ])
    def test_shell_commands_naming_writs_file_are_denied(self, tmp_path, tool, command):
        plugin = _any_script(tmp_path)
        out = _handle(plugin, "pre_tool", _pre(tmp_path, tool, {"command": command}),
                      resolver=_no_lookup)
        assert "0-writ.md" in _deny_reason(out)
        assert plugin.runs("all") == []

    def test_shell_commands_not_naming_it_reach_the_scripts(self, tmp_path):
        plugin = _any_script(tmp_path)
        out = _handle(plugin, "pre_tool", _pre(tmp_path, "file_system.bash",
                                               {"command": "ls scratchpad"}))
        assert out == ""
        assert len(plugin.runs("all")) == 1

    def test_typed_text_naming_writs_file_is_denied_in_any_mode(self, tmp_path, writ_cache):
        writ_cache({"mode": "conversation"})
        plugin = _any_script(tmp_path)
        out = _handle(plugin, "pre_tool", _write(tmp_path, {"text": "cat > 0-writ.md\n"}),
                      resolver=_no_lookup)
        assert "0-writ.md" in _deny_reason(out)
        assert plugin.runs("all") == []


# --------------------------------------------------------------------------- #
# post_agent: Writ's Stop checks at the end of a turn
# --------------------------------------------------------------------------- #
def _agent(cwd: Path) -> dict:
    return {"cwd": str(cwd), "hook_event_name": "post_agent"}


def _refusing(text: str, code: int = 2) -> str:
    return f'echo "{text}" >&2\nexit {code}\n'


class TestStop:
    def test_every_stop_script_runs_once_with_a_claude_stop_envelope(self, tmp_path):
        work = tmp_path / "proj"
        work.mkdir()
        plugin = Plugin(tmp_path, {
            "Stop": [{"matcher": "", "scripts": {"s1": ALLOW}},
                     {"matcher": "", "scripts": {"s2": ALLOW}}],
            "PreToolUse": [{"matcher": "", "scripts": {"pre": ALLOW}}],
            "PostToolUse": [{"matcher": "", "scripts": {"post": ALLOW}}],
        })
        assert _handle(plugin, "post_agent", _agent(work)) == ""
        for name in ("s1", "s2"):
            assert plugin.runs(name) == [{
                "session_id": "sid-1", "transcript_path": "", "cwd": str(work),
                "hook_event_name": "Stop", "stop_hook_active": False,
            }]
        assert plugin.runs("pre") == plugin.runs("post") == []
        [[root, strict, cwd]] = plugin.envs("s1")
        assert root == str(plugin.root)
        assert strict == "1"
        assert os.path.realpath(cwd) == os.path.realpath(work)

    @pytest.mark.parametrize("body, needle", [
        (_refusing("R-EXIT2", 2), "R-EXIT2"),
        (_refusing("R-EXIT1", 1), "R-EXIT1"),
        (_json_body({"decision": "block", "reason": "R-BLOCK"}), "R-BLOCK"),
    ])
    def test_a_refusing_script_denies_the_turn_under_writs_header(self, tmp_path, body, needle):
        plugin = Plugin(tmp_path, {"Stop": [{"matcher": "", "scripts": {"check": body}}]})
        reason = _deny_reason(_handle(plugin, "post_agent", _agent(tmp_path)))
        assert reason.startswith(vibe._STOP_HEADER)
        assert needle in reason

    @pytest.mark.parametrize("code", [1, 2])
    def test_a_silent_refusal_names_the_script(self, tmp_path, code):
        plugin = Plugin(tmp_path, {"Stop": [{"matcher": "", "scripts": {"quiet": f"exit {code}\n"}}]})
        assert "quiet" in _deny_reason(_handle(plugin, "post_agent", _agent(tmp_path)))

    def test_refusals_join_into_one_deny_in_hooks_json_order(self, tmp_path):
        plugin = Plugin(tmp_path, {"Stop": [
            {"matcher": "", "scripts": {"first": _refusing("REASON-ONE", 2)}},
            {"matcher": "", "scripts": {"passes": ALLOW}},
            {"matcher": "", "scripts": {"second": _refusing("REASON-TWO", 1)}},
        ]})
        out = _handle(plugin, "post_agent", _agent(tmp_path))
        assert json.loads(out) == {
            "decision": "deny",
            "reason": f"{vibe._STOP_HEADER}\n\nREASON-ONE\n\nREASON-TWO",
        }

    @pytest.mark.parametrize("body", [
        ALLOW,
        "echo chatter\nexit 0\n",
        _json_body({"decision": "approve"}),
        _json_body({"continue": False, "stopReason": "done"}),
        _refusing("crashed", 3),
        _refusing("command not found", 127),
    ])
    def test_any_other_answer_accepts_the_turn(self, tmp_path, body):
        plugin = Plugin(tmp_path, {"Stop": [{"matcher": "", "scripts": {"check": body}}]})
        assert _handle(plugin, "post_agent", _agent(tmp_path)) == ""
        assert len(plugin.runs("check")) == 1

    def test_a_timed_out_script_accepts_the_turn_without_waiting_it_out(self, tmp_path):
        plugin = Plugin(tmp_path, {"Stop": [
            {"matcher": "", "timeout": 1, "scripts": {"slow": "sleep 5\nexit 2\n"}}]})
        start = time.monotonic()
        assert _handle(plugin, "post_agent", _agent(tmp_path)) == ""
        assert time.monotonic() - start < 4

    def test_no_session_accepts_the_turn_and_runs_nothing(self, tmp_path):
        plugin = Plugin(tmp_path, {"Stop": [{"matcher": "", "scripts": {"s": _refusing("R")}}]})
        assert _handle(plugin, "post_agent", _agent(tmp_path), sid=None) == ""
        assert plugin.runs("s") == []

    @pytest.mark.parametrize("raw", ["garbage", "[]", ""])
    def test_unreadable_input_accepts_the_turn_and_runs_nothing(self, tmp_path, raw):
        plugin = Plugin(tmp_path, {"Stop": [{"matcher": "", "scripts": {"s": _refusing("R")}}]})
        assert _handle(plugin, "post_agent", raw) == ""
        assert plugin.runs("s") == []

    def test_a_bridge_exception_accepts_the_turn(self, tmp_path):
        plugin = Plugin(tmp_path, {"Stop": [{"matcher": "", "scripts": {"s": _refusing("R")}}]})
        assert _handle(plugin, "post_agent", _agent(tmp_path), resolver=_raise) == ""

    def test_stop_scripts_default_to_the_stop_timeout_and_tool_scripts_keep_theirs(
            self, tmp_path, monkeypatch):
        plugin = Plugin(tmp_path, {
            "Stop": [{"matcher": "", "scripts": {"plain": ALLOW}},
                     {"matcher": "", "timeout": 7, "scripts": {"pinned": ALLOW}}],
            "PreToolUse": [{"matcher": "Bash", "scripts": {"pre": ALLOW}}],
        })
        seen: dict[str, float] = {}
        real = vibe._run

        def spy(command, stdin, *, cwd, env, timeout):
            seen[vibe._script_name(command)] = timeout
            return real(command, stdin, cwd=cwd, env=env, timeout=timeout)
        monkeypatch.setattr(vibe, "_run", spy)
        _handle(plugin, "post_agent", _agent(tmp_path))
        _handle(plugin, "pre_tool", _pre(tmp_path, "file_system.bash", {"command": "ls"}))
        assert vibe.STOP_SCRIPT_TIMEOUT_S == 180.0
        assert seen == {"plain": vibe.STOP_SCRIPT_TIMEOUT_S, "pinned": 7.0,
                        "pre": vibe.DEFAULT_SCRIPT_TIMEOUT_S}

    @pytest.mark.parametrize("argv", [["post_agent"], []])
    def test_main_routes_post_agent_from_argv_and_from_the_payload(self, monkeypatch, argv):
        seen = []

        def fake(event, raw):
            seen.append(event)
            return ""
        monkeypatch.setattr(vibe, "handle", fake)
        monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(_agent(Path("/")))))
        assert vibe.main(argv) == 0
        assert seen == ["post_agent"]

    def test_shim_accepts_garbage_and_exits_zero(self):
        proc = subprocess.run([sys.executable, str(SHIM), "post_agent"], input="garbage",
                              capture_output=True, text=True, timeout=30)
        assert proc.returncode == 0
        assert proc.stdout.strip() == ""


# --------------------------------------------------------------------------- #
# user_prompt and session_start: Writ's UserPromptSubmit and SessionStart scripts
# --------------------------------------------------------------------------- #
def _prompt(cwd: Path, prompt: str = "add a dry-run flag", **extra) -> dict:
    return {"cwd": str(cwd), "hook_event_name": "user_prompt", "prompt": prompt,
            "last_assistant_message": None, **extra}


def _start(cwd: Path, source: str = "startup") -> dict:
    return {"cwd": str(cwd), "hook_event_name": "session_start", "source": source}


def _context(out: str) -> str:
    return json.loads(out)["hook_specific_output"]["additional_context"]


def _echo(*lines: str) -> str:
    return "".join(f"echo '{line}'\n" for line in lines) + "exit 0\n"


class TestPrompt:
    def test_every_prompt_script_runs_once_with_a_claude_envelope(self, tmp_path, refreshes):
        work = tmp_path / "proj"
        work.mkdir()
        plugin = Plugin(tmp_path, {
            "UserPromptSubmit": [{"matcher": "", "scripts": {"u1": ALLOW}},
                                 {"matcher": "", "scripts": {"u2": ALLOW}}],
            "SessionStart": [{"matcher": "", "scripts": {"start": ALLOW}}],
            "Stop": [{"matcher": "", "scripts": {"stop": ALLOW}}],
        })
        reply = "Plan written to plan.md.\n\nSay approved to proceed."
        envelope = _prompt(work, "approved", last_assistant_message=reply)
        assert _handle(plugin, "user_prompt", envelope) == ""
        for name in ("u1", "u2"):
            assert plugin.runs(name) == [{
                "session_id": "sid-1", "transcript_path": "", "cwd": str(work),
                "prompt": "approved", "last_assistant_message": reply,
                "hook_event_name": "UserPromptSubmit",
            }]
        assert plugin.runs("start") == plugin.runs("stop") == []
        [[root, strict, cwd]] = plugin.envs("u1")
        assert root == str(plugin.root)
        assert strict == "1"
        assert os.path.realpath(cwd) == os.path.realpath(work)

    def test_a_null_previous_reply_stays_null_and_a_missing_one_stays_missing(
            self, tmp_path, refreshes):
        plugin = Plugin(tmp_path, {"UserPromptSubmit": [{"matcher": "", "scripts": {"u": ALLOW}}]})
        without = _prompt(tmp_path)
        del without["last_assistant_message"]
        _handle(plugin, "user_prompt", _prompt(tmp_path))
        _handle(plugin, "user_prompt", without)
        runs = plugin.runs("u")
        assert sorted("last_assistant_message" in run for run in runs) == [False, True]
        assert [run["last_assistant_message"] for run in runs
                if "last_assistant_message" in run] == [None]

    def test_plain_stdout_and_additional_context_join_in_hooks_json_order(
            self, tmp_path, refreshes):
        plugin = Plugin(tmp_path, {"UserPromptSubmit": [
            {"matcher": "", "scripts": {"rules": _echo("--- WRIT RULES ---", "RULE-1")}},
            {"matcher": "", "scripts": {"quiet": ALLOW}},
            {"matcher": "", "scripts": {"json": _json_body({"hookSpecificOutput": {
                "hookEventName": "UserPromptSubmit", "additionalContext": "CTX-2"}})}},
        ]})
        out = _handle(plugin, "user_prompt", _prompt(tmp_path))
        assert json.loads(out) == {"hook_specific_output": {
            "additional_context": "--- WRIT RULES ---\nRULE-1\n\nCTX-2"}}

    @pytest.mark.parametrize("body", [
        _json_body({"continue": True}),
        _json_body({"hookSpecificOutput": {"hookEventName": "UserPromptSubmit"}}),
    ])
    def test_a_json_answer_without_context_adds_nothing(self, tmp_path, refreshes, body):
        plugin = Plugin(tmp_path, {"UserPromptSubmit": [{"matcher": "", "scripts": {"u": body}}]})
        assert _handle(plugin, "user_prompt", _prompt(tmp_path)) == ""

    @pytest.mark.parametrize("body, reason", [
        (_refusing("R-EXIT2", 2), "R-EXIT2"),
        (_json_body({"decision": "block", "reason": "R-BLOCK"}), "R-BLOCK"),
        ("exit 2\n", "gate blocked the call"),
    ])
    def test_a_blocking_script_denies_the_prompt_and_drops_the_context(
            self, tmp_path, refreshes, body, reason):
        plugin = Plugin(tmp_path, {"UserPromptSubmit": [
            {"matcher": "", "scripts": {"gate": body}},
            {"matcher": "", "scripts": {"rules": _echo("RULES")}},
        ]})
        out = _handle(plugin, "user_prompt", _prompt(tmp_path))
        assert json.loads(out) == {"decision": "deny", "reason": reason}

    @pytest.mark.parametrize("body", [_refusing("crashed", 1), _refusing("not found", 127)])
    def test_a_failing_script_is_dropped_and_the_others_still_answer(
            self, tmp_path, refreshes, body):
        plugin = Plugin(tmp_path, {"UserPromptSubmit": [
            {"matcher": "", "scripts": {"broken": "echo LOST\n" + body}},
            {"matcher": "", "scripts": {"rules": _echo("RULES")}},
        ]})
        assert _context(_handle(plugin, "user_prompt", _prompt(tmp_path))) == "RULES"

    def test_a_timed_out_script_passes_the_prompt_without_waiting_it_out(
            self, tmp_path, refreshes):
        plugin = Plugin(tmp_path, {"UserPromptSubmit": [
            {"matcher": "", "timeout": 1, "scripts": {"slow": "sleep 5\nexit 2\n"}}]})
        start = time.monotonic()
        assert _handle(plugin, "user_prompt", _prompt(tmp_path)) == ""
        assert time.monotonic() - start < 4

    def test_the_state_file_is_rewritten_after_the_scripts_ran_even_on_a_block(
            self, tmp_path, monkeypatch):
        plugin = Plugin(tmp_path, {"UserPromptSubmit": [
            {"matcher": "", "scripts": {"gate": _refusing("R")}}]})
        seen = []

        def fake(sid, **kwargs):
            seen.append((sid, kwargs["plugin_root"], len(plugin.runs("gate"))))
            return True
        monkeypatch.setattr(vibe_context, "refresh", fake)
        assert _deny_reason(_handle(plugin, "user_prompt", _prompt(tmp_path))) == "R"
        assert seen == [("sid-1", str(plugin.root), 1)]


class TestSessionStart:
    def test_every_start_script_runs_once_with_a_claude_envelope(self, tmp_path, refreshes):
        plugin = Plugin(tmp_path, {
            "SessionStart": [{"matcher": "", "scripts": {"s1": ALLOW}},
                             {"matcher": "", "scripts": {"s2": ALLOW}}],
            "UserPromptSubmit": [{"matcher": "", "scripts": {"prompt": ALLOW}}],
        })
        assert _handle(plugin, "session_start", _start(tmp_path, "fork")) == ""
        for name in ("s1", "s2"):
            assert plugin.runs(name) == [{
                "session_id": "sid-1", "transcript_path": "", "cwd": str(tmp_path),
                "source": "fork", "hook_event_name": "SessionStart",
            }]
        assert plugin.runs("prompt") == []
        assert refreshes == []

    def test_a_matcher_is_compared_against_the_source(self, tmp_path, refreshes):
        plugin = Plugin(tmp_path, {"SessionStart": [
            {"matcher": "resume|fork", "scripts": {"later": ALLOW}},
            {"matcher": "startup", "scripts": {"first": ALLOW}},
        ]})
        _handle(plugin, "session_start", _start(tmp_path, "resume"))
        assert len(plugin.runs("later")) == 1
        assert plugin.runs("first") == []

    def test_stdout_and_additional_context_become_context(self, tmp_path, refreshes):
        plugin = Plugin(tmp_path, {"SessionStart": [
            {"matcher": "", "scripts": {"boot": _echo("DAEMON-UP")}},
            {"matcher": "", "scripts": {"json": _json_body({"hookSpecificOutput": {
                "hookEventName": "SessionStart", "additionalContext": "CTX-2"}})}},
        ]})
        assert _context(_handle(plugin, "session_start", _start(tmp_path))) == "DAEMON-UP\n\nCTX-2"

    @pytest.mark.parametrize("body", [
        _refusing("R-EXIT2", 2),
        _json_body({"decision": "block", "reason": "R-BLOCK"}),
    ])
    def test_a_refusing_script_never_blocks_the_session(self, tmp_path, refreshes, body):
        plugin = Plugin(tmp_path, {"SessionStart": [{"matcher": "", "scripts": {"s": body}}]})
        assert _handle(plugin, "session_start", _start(tmp_path)) == ""


_PROMPT_EVENTS = [("user_prompt", "UserPromptSubmit", _prompt),
                  ("session_start", "SessionStart", _start)]


@pytest.mark.parametrize("event, claude_event, envelope", _PROMPT_EVENTS)
class TestPromptEventsFailOpen:
    def test_no_session_runs_nothing(self, tmp_path, refreshes, event, claude_event, envelope):
        plugin = Plugin(tmp_path, {claude_event: [{"matcher": "", "scripts": {"s": _refusing("R")}}]})
        assert _handle(plugin, event, envelope(tmp_path), sid=None) == ""
        assert plugin.runs("s") == []
        assert refreshes == []

    @pytest.mark.parametrize("raw", ["garbage", "[]", ""])
    def test_unreadable_input_runs_nothing(self, tmp_path, event, claude_event, envelope, raw):
        plugin = Plugin(tmp_path, {claude_event: [{"matcher": "", "scripts": {"s": _refusing("R")}}]})
        assert _handle(plugin, event, raw) == ""
        assert plugin.runs("s") == []

    def test_a_bridge_exception_passes(self, tmp_path, event, claude_event, envelope):
        plugin = Plugin(tmp_path, {claude_event: [{"matcher": "", "scripts": {"s": _refusing("R")}}]})
        assert _handle(plugin, event, envelope(tmp_path), resolver=_raise) == ""

    @pytest.mark.parametrize("argv", [True, False])
    def test_main_routes_the_event_from_argv_and_from_the_payload(
            self, monkeypatch, event, claude_event, envelope, argv):
        seen = []

        def fake(routed, raw):
            seen.append(routed)
            return ""
        monkeypatch.setattr(vibe, "handle", fake)
        monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(envelope(Path("/")))))
        assert vibe.main([event] if argv else []) == 0
        assert seen == [event]

    def test_shim_accepts_garbage_and_exits_zero(self, event, claude_event, envelope):
        proc = subprocess.run([sys.executable, str(SHIM), event], input="garbage",
                              capture_output=True, text=True, timeout=30, check=False)
        assert proc.returncode == 0
        assert proc.stdout.strip() == ""


# --------------------------------------------------------------------------- #
# Captured envelopes
# --------------------------------------------------------------------------- #
_CAPTURED = [json.loads(line) for line in FIXTURES.read_text().splitlines() if line.strip()]


@pytest.mark.parametrize("row", _CAPTURED, ids=[r["source"] for r in _CAPTURED])
def test_every_captured_envelope_translates(tmp_path, row):
    plugin = Plugin(tmp_path, {
        "PreToolUse": [{"matcher": "", "scripts": {"pre": ALLOW}}],
        "PostToolUse": [{"matcher": "", "scripts": {"post": ALLOW}}],
        "PostToolUseFailure": [{"matcher": "", "scripts": {"fail": ALLOW}}],
    })
    envelope = row["envelope"]
    event = envelope["hook_event_name"]
    vibe.to_claude(envelope, event, "sid-1")
    out = _handle(plugin, event, envelope)
    if out:
        assert json.loads(out)["decision"] in ("allow", "deny")
