"""Reads of secret files are refused in every mode (SEC-CREDENTIAL-READ).

Whatever Claude reads enters the transcript and leaves the machine, so reading a
.env is the leak, not writing it. The write side is covered by
tests/test_bash_write_gate.py; this module pins the read side:

  1. bin/lib/credential_read.find_credential_read, the pure classifier for Read,
     Grep and Bash inputs, reusing writ.session.gates._is_credential_path so the
     template allowlist (.env.example, ...) is shared with the write gate.
  2. hooks/scripts/writ-read-credential-gate.sh end to end: deny with no daemon,
     in every mode, and for a subagent envelope.
"""
from __future__ import annotations

import importlib.util
import json
import os
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
HOOK_SH = REPO / "hooks" / "scripts" / "writ-read-credential-gate.sh"
MODULE = REPO / "bin" / "lib" / "credential_read.py"
HELPER = REPO / "bin" / "lib" / "writ-session.py"


def _classifier():
    spec = importlib.util.spec_from_file_location("credential_read", MODULE)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.find_credential_read


def _run_hook(envelope: dict, tmp_path: Path) -> dict | None:
    """Full hook, service unreachable (WRIT_PORT=1). Returns hookSpecificOutput on
    a deny, None when the hook allows (empty stdout)."""
    env = os.environ.copy()
    env["WRIT_CACHE_DIR"] = str(tmp_path)
    env["WRIT_PORT"] = "1"
    p = subprocess.run(["bash", str(HOOK_SH)], input=json.dumps(envelope),
                       cwd=str(tmp_path), capture_output=True, text=True,
                       env=env, timeout=15)
    assert p.returncode == 0, p.stderr
    out = p.stdout.strip()
    if not out:
        return None
    return json.loads(out).get("hookSpecificOutput", {})


# --------------------------------------------------------------------------- #
# 1. classifier
# --------------------------------------------------------------------------- #
class TestReadTool:
    @pytest.mark.parametrize("path", [
        ".env", "config/.env.production", "~/.ssh/id_rsa", "certs/server.pem",
        "/srv/app/.env.local",
    ])
    def test_secret_file_is_flagged(self, path):
        assert _classifier()("Read", {"file_path": path}) is not None

    @pytest.mark.parametrize("path", [".env.example", ".env.sample", "README.md"])
    def test_template_and_plain_file_allowed(self, path):
        assert _classifier()("Read", {"file_path": path}) is None


class TestGrepTool:
    def test_grep_on_env_file_flagged(self):
        assert _classifier()("Grep", {"pattern": "KEY", "path": ".env"}) is not None

    def test_grep_on_directory_allowed(self):
        assert _classifier()("Grep", {"pattern": "KEY", "path": "."}) is None

    def test_grep_without_path_allowed(self):
        assert _classifier()("Grep", {"pattern": "KEY"}) is None


class TestBashTool:
    @pytest.mark.parametrize("cmd", [
        "cat .env",
        "head -n 3 .env",
        "source .env",
        ". .env",
        "grep KEY .env",
        "base64 .env",
        "cp .env /tmp/x",
        "FOO=1 cat .env",
        "env cat .env",
        "cat < .env",
        "ls | cat .env",
        "true && tail config/.env.production",
        "cat ~/.ssh/id_rsa",
        """python3 -c "print(open('.env').read())\"""",
        """node -e "require('fs').readFileSync('.env')\"""",
    ])
    def test_reading_secret_is_flagged(self, cmd):
        assert _classifier()("Bash", {"command": cmd}) is not None, cmd

    @pytest.mark.parametrize("cmd", [
        'echo ".env" >> .gitignore',
        "git add .env.example",
        "cat .env.example",
        "ls -la",
        "touch notes.txt",
        "cat README.md",
    ])
    def test_non_reading_or_template_allowed(self, cmd):
        assert _classifier()("Bash", {"command": cmd}) is None, cmd

    def test_returns_the_offending_path(self):
        assert _classifier()("Bash", {"command": "cat .env"}) == ".env"


class TestFalsePositives:
    """Probed live 2026-09-25: a bare secret-directory name (`secret`) read as the
    directory `secret/`, and the pattern of grep read as a file. Both refused
    commands that read nothing secret."""

    @pytest.mark.parametrize("cmd", [
        "grep -rn secret src/",
        "grep -rn '.env' src/",
        "rg -A 2 secret .",
        """python3 -c "d={'secret': 1}; print(d['secret'])\"""",
    ])
    def test_word_or_pattern_is_not_a_path(self, cmd):
        assert _classifier()("Bash", {"command": cmd}) is None, cmd

    @pytest.mark.parametrize("cmd", [
        "cat secrets/prod.json",
        "grep KEY .env",
        "grep -e x .env",
        "rg KEY -g .env",
        "cat .ssh/config",
        """python3 -c "open('.env')\"""",
    ])
    def test_real_secret_read_still_flagged(self, cmd):
        assert _classifier()("Bash", {"command": cmd}) is not None, cmd


class TestOtherTools:
    def test_unrelated_tool_ignored(self):
        assert _classifier()("Glob", {"pattern": ".env*"}) is None


# --------------------------------------------------------------------------- #
# 2. hook end to end: no daemon, every mode, subagents included
# --------------------------------------------------------------------------- #
class TestHookEndToEnd:
    def test_read_env_denied_without_service(self, tmp_path: Path):
        out = _run_hook({"session_id": "rcg-1", "tool_name": "Read",
                         "tool_input": {"file_path": ".env"}}, tmp_path)
        assert out is not None and out.get("permissionDecision") == "deny"
        assert "SEC-CREDENTIAL-READ" in out.get("permissionDecisionReason", "")

    def test_bash_cat_env_denied(self, tmp_path: Path):
        out = _run_hook({"session_id": "rcg-2", "tool_name": "Bash",
                         "tool_input": {"command": "cat .env"}}, tmp_path)
        assert out is not None and out.get("permissionDecision") == "deny"
        assert "SEC-CREDENTIAL-READ" in out.get("permissionDecisionReason", "")

    def test_subagent_is_not_exempt(self, tmp_path: Path):
        out = _run_hook({"session_id": "rcg-3", "agent_id": "sub-1",
                         "tool_name": "Read", "tool_input": {"file_path": ".env"}},
                        tmp_path)
        assert out is not None and out.get("permissionDecision") == "deny"

    @pytest.mark.parametrize("mode", ["conversation", "work", "debug", "review"])
    def test_denied_in_every_mode(self, tmp_path: Path, mode: str):
        env = os.environ.copy()
        env["WRIT_CACHE_DIR"] = str(tmp_path)
        env["WRIT_PORT"] = "1"
        subprocess.run(["python3", str(HELPER), "mode", "set", mode, "rcg-mode"],
                       cwd=str(tmp_path), capture_output=True, env=env, timeout=15)
        out = _run_hook({"session_id": "rcg-mode", "tool_name": "Read",
                         "tool_input": {"file_path": "config/.env.production"}},
                        tmp_path)
        assert out is not None and out.get("permissionDecision") == "deny"

    def test_template_read_allowed(self, tmp_path: Path):
        assert _run_hook({"session_id": "rcg-4", "tool_name": "Read",
                          "tool_input": {"file_path": ".env.example"}}, tmp_path) is None

    def test_plain_bash_allowed(self, tmp_path: Path):
        assert _run_hook({"session_id": "rcg-5", "tool_name": "Bash",
                          "tool_input": {"command": "ls -la"}}, tmp_path) is None


# --------------------------------------------------------------------------- #
# 3. the refusal reaches `writ audit-session`, which lists gate_denial rows only
# --------------------------------------------------------------------------- #
def _session_rows(sid: str) -> list[dict]:
    """This session's rows from the test's friction log (conftest points
    WRIT_FRICTION_LOG at tmp_path; the hook subprocess inherits it)."""
    from writ.analysis.friction import load_events
    return [e for e in load_events(None) if e.get("session") == sid]


def _denied_rules(sid: str) -> list[str]:
    """The rule ids `writ audit-session` prints under "Gate denials"."""
    from writ.analysis.friction import aggregate_session
    return [g["rule_id"] for g in aggregate_session(_session_rows(sid))["gate_denials"]]


class TestDenialIsAudited:
    def test_read_env_leaves_a_gate_denial(self, tmp_path: Path):
        out = _run_hook({"session_id": "rcg-a1", "tool_name": "Read",
                         "tool_input": {"file_path": ".env"}}, tmp_path)
        assert out is not None and out.get("permissionDecision") == "deny"
        assert _denied_rules("rcg-a1") == ["SEC-CREDENTIAL-READ"]

    def test_bash_cat_env_leaves_a_gate_denial(self, tmp_path: Path):
        out = _run_hook({"session_id": "rcg-a2", "tool_name": "Bash",
                         "tool_input": {"command": "cat .env"}}, tmp_path)
        assert out is not None and out.get("permissionDecision") == "deny"
        assert _denied_rules("rcg-a2") == ["SEC-CREDENTIAL-READ"]

    def test_allowed_read_leaves_no_gate_denial(self, tmp_path: Path):
        assert _run_hook({"session_id": "rcg-a3", "tool_name": "Read",
                          "tool_input": {"file_path": "src/main.py"}}, tmp_path) is None
        assert _denied_rules("rcg-a3") == []

    def test_path_is_recorded_exactly(self, tmp_path: Path):
        path = 'conf"ig/.env'
        out = _run_hook({"session_id": "rcg-a4", "tool_name": "Read",
                         "tool_input": {"file_path": path}}, tmp_path)
        assert out is not None and out.get("permissionDecision") == "deny"
        rows = [e for e in _session_rows("rcg-a4") if e.get("event") == "gate_denial"]
        assert [r.get("file_path") for r in rows] == [path]

    def test_audit_text_names_the_rule(self, tmp_path: Path):
        from writ.analysis.friction import aggregate_session, render_audit_text
        _run_hook({"session_id": "rcg-a5", "tool_name": "Read",
                   "tool_input": {"file_path": ".env"}}, tmp_path)
        rows = _session_rows("rcg-a5")
        assert "denied: SEC-CREDENTIAL-READ" in render_audit_text(
            "rcg-a5", rows, aggregate_session(rows))
