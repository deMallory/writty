"""MTY-413: unbounded recursive greps over session stores and .vibe trees are
refused before they run.

Session `c1a56bcc` spent 9 model rounds on
`grep -ril "ephesus\\|sydd" <mistty>/.vibe/`, hit the 300s bash timeout over a
1.9 GB tree, and never found the session it wanted. The `vibe.session_search`
tool and the session-archaeology skill are the replacements; this hook is the
enforcement: a PreToolUse gate on Bash that denies a recursive `grep` or a
`find` whose target sits in a session store or a `.vibe`/`.mistty` tree unless
the scan is bounded (`--exclude-dir` on grep, `-prune`/`-path` on find).

Two layers, as the other bash gates are tested: TestGrepGuardExtraction runs the
hook's embedded python extractor directly (fast, no daemon, no cache), and
TestGrepGuardDecision runs the full hook script against a seeded session and
asserts the user-observable decision. Idioms reused from
tests/test_bash_write_gate.py (`_seed`, `_sid`) and
tests/test_bash_egress_gate.py (`_run_hook`), imported or mirrored, not
duplicated.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import uuid
from pathlib import Path

from tests.fixtures.session_state import sandbox_cwd  # noqa: F401

SKILL_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
HOOKS_JSON = os.path.join(SKILL_ROOT, "hooks", "hooks.json")
HOOK_SH = os.path.join(SKILL_ROOT, "hooks", "scripts", "writ-bash-grep-guard.sh")

# The last line the extractor prints on every completed path (mirrors
# WRIT_EXTRACTOR_SENTINEL in bin/lib/common.sh; the wrapper treats its absence
# as a fault, never as a silent allow).
SENTINEL = "status\tcomplete"

_C1A56BCC_CMD = (
    'grep -ril "ephesus\\|sydd" /Users/david.malinen/Documents/laarge/dev/mistty/.vibe/'
)
_EXCLUDES = "--exclude-dir=.venv --exclude-dir=target --exclude-dir=worktrees"


def _imp(name):
    if SKILL_ROOT not in sys.path:
        sys.path.insert(0, SKILL_ROOT)
    return __import__(name, fromlist=["_"])


def _seed(sid, **fields):
    cache = _imp("writ.session.cache")
    data = cache._read_cache(sid)
    data.update(fields)
    cache._write_cache(sid, data)


def _sid() -> str:
    return f"grep-guard-{uuid.uuid4().hex[:8]}"


def _extractor_src() -> str:
    text = Path(HOOK_SH).read_text()
    marker = text.index("<<'PY'")
    start = text.index("\n", marker) + 1
    end = text.index("\nPY\n", start)
    return text[start:end]


def run_extractor(cmd: str, cwd: str = "/proj", *, env: dict | None = None):
    """Run the embedded extractor on CMD and return (proc, decision rows).

    The command crosses on a FILE (`WRIT_GG_CMD_FILE`), the transport the hook
    itself uses, and the working directory via `WRIT_CWD`; the sentinel is
    stripped before the rows are read.
    """
    base = dict(os.environ if env is None else env)
    fd, cmd_path = tempfile.mkstemp(prefix="writ-test-ggcmd-")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", errors="surrogateescape") as fh:
            fh.write(cmd)
        base.update(WRIT_GG_CMD_FILE=cmd_path, WRIT_CWD=str(cwd))
        proc = subprocess.run(
            [sys.executable, "-c", _extractor_src()],
            env=base,
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
    finally:
        os.unlink(cmd_path)
    lines = [ln for ln in proc.stdout.splitlines() if ln != SENTINEL]
    return proc, lines


def _deny_rows(cmd: str, cwd: str = "/proj", extra_env: dict | None = None):
    """The extractor's `deny<TAB>target<TAB>reason` rows for CMD."""
    env = dict(os.environ)
    if extra_env:
        env.update(extra_env)
    _proc, lines = run_extractor(cmd, cwd, env=env)
    rows = []
    for line in lines:
        parts = line.split("\t", 2)
        if len(parts) == 3 and parts[0] == "deny":
            rows.append((parts[1], parts[2]))
    return rows


def _run_hook(cmd: str, sid: str, cwd: str, extra_env: dict | None = None):
    """Invoke the full hook with a synthetic Bash envelope; the parsed
    hookSpecificOutput, or None when the hook stays silent."""
    envelope = json.dumps(
        {"session_id": sid, "tool_name": "Bash", "tool_input": {"command": cmd}}
    )
    env = dict(os.environ)
    if extra_env:
        env.update(extra_env)
    p = subprocess.run(
        ["bash", HOOK_SH],
        input=envelope,
        cwd=cwd,
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    out = p.stdout.strip()
    if not out:
        return None
    return json.loads(out).get("hookSpecificOutput", {})


class TestGrepGuardExtraction:
    def test_the_exact_c1a56bcc_command_is_denied(self):
        rows = _deny_rows(_C1A56BCC_CMD)
        assert rows, "the unbounded scan over the repo's .vibe tree must be denied"
        target, reason = rows[0]
        assert ".vibe" in target
        assert "--exclude-dir" in reason

    def test_the_same_command_with_exclude_dirs_is_allowed(self):
        assert _deny_rows(_C1A56BCC_CMD + " " + _EXCLUDES) == []

    def test_a_recursive_grep_outside_the_trees_is_allowed(self):
        assert _deny_rows("grep -rn needle src/ hooks/") == []

    def test_session_store_targets_name_the_tool_remedy(self):
        for cmd in (
            "grep -r needle ~/.vibe/logs/session",
            "grep -r needle ~/.mistty/logs/session",
        ):
            rows = _deny_rows(cmd)
            assert rows, cmd
            assert "vibe.session_search" in rows[0][1], cmd

    def test_a_custom_vibe_home_store_is_denied(self):
        rows = _deny_rows(
            "grep -r needle /zz/test-home/logs/session",
            extra_env={"VIBE_HOME": "/zz/test-home"},
        )
        assert rows
        assert "vibe.session_search" in rows[0][1]

    def test_a_quoted_target_is_denied(self):
        assert _deny_rows("grep -r needle '~/.vibe'")

    def test_an_assignment_prefix_is_denied(self):
        assert _deny_rows("FOO=1 grep -r needle .vibe/")

    def test_a_wrapper_prefix_is_denied(self):
        assert _deny_rows("sudo grep -r needle .vibe/")

    def test_a_chained_form_is_denied_per_segment(self):
        assert _deny_rows("cd /x && grep -r needle ~/.mistty/logs/session")

    def test_a_piped_form_is_denied_per_segment(self):
        assert _deny_rows("cat f | grep -r needle .vibe | wc -l")

    def test_a_group_form_is_denied(self):
        assert _deny_rows("(grep -r needle .vibe)")

    def test_a_heredoc_body_is_not_judged(self):
        cmd = "cat <<'EOF'\ngrep -r needle .vibe\nEOF"
        assert _deny_rows(cmd) == []

    def test_find_over_a_tree_is_denied_and_pruned_finds_are_allowed(self):
        assert _deny_rows("find .vibe -name '*.json'")
        assert _deny_rows("find .vibe -name .venv -prune -o -name '*.json'") == []
        assert _deny_rows("find .vibe -path '*/.venv/*' -prune -o -print") == []

    def test_a_non_recursive_grep_in_the_trees_is_allowed(self):
        assert _deny_rows("grep needle /Users/x/.vibe/config.toml") == []

    def test_a_recursive_grep_with_no_operand_is_allowed(self):
        assert _deny_rows("cat x | grep -r needle") == []

    def test_a_dot_operand_inside_a_deep_cwd_is_denied(self):
        assert _deny_rows("grep -r needle .", cwd="/proj/.vibe/worktrees/x")


class TestGrepGuardDecision:
    def _deny(self, cmd: str, tmp_path: Path, mode: str = "work"):
        sid = _sid()
        _seed(sid, mode=mode)
        return _run_hook(cmd, sid, str(tmp_path))

    def test_the_exact_c1a56bcc_command_is_refused(self, tmp_path: Path):
        out = self._deny(_C1A56BCC_CMD, tmp_path)
        assert out is not None and out.get("permissionDecision") == "deny"
        assert "--exclude-dir" in out.get("permissionDecisionReason", "")

    def test_the_bounded_command_runs(self, tmp_path: Path):
        assert self._deny(_C1A56BCC_CMD + " " + _EXCLUDES, tmp_path) is None

    def test_a_store_grep_is_refused_naming_session_search(self, tmp_path: Path):
        out = self._deny("grep -r needle ~/.mistty/logs/session", tmp_path)
        assert out is not None and out.get("permissionDecision") == "deny"
        assert "vibe.session_search" in out.get("permissionDecisionReason", "")

    def test_the_guard_fires_in_every_governed_mode(self, tmp_path: Path):
        for mode in ("conversation", "review", "work"):
            out = self._deny("grep -r needle .vibe/", tmp_path, mode=mode)
            assert out is not None and out.get("permissionDecision") == "deny", mode

    def test_no_session_id_stays_silent(self, tmp_path: Path):
        assert _run_hook("grep -r needle .vibe/", "", str(tmp_path)) is None

    def test_a_fault_fails_open_never_a_false_deny(self, tmp_path: Path):
        sid = _sid()
        _seed(sid, mode="work")
        env = {"TMPDIR": str(tmp_path / "no-such-dir")}
        envelope = json.dumps(
            {
                "session_id": sid,
                "tool_name": "Bash",
                "tool_input": {"command": "grep -r needle .vibe/"},
            }
        )
        p = subprocess.run(
            ["bash", HOOK_SH],
            input=envelope,
            cwd=str(tmp_path),
            env={**os.environ, **env},
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
        out = p.stdout.strip()
        decision = (
            json.loads(out).get("hookSpecificOutput", {}).get("permissionDecision")
            if out
            else None
        )
        assert p.returncode == 0 and decision != "deny"


def test_the_hook_is_registered_on_bash_and_run_terminal_command():
    spec = json.loads(Path(HOOKS_JSON).read_text())
    commands = [
        hook["command"]
        for entry in spec["hooks"]["PreToolUse"]
        if entry["matcher"] == "Bash|run_terminal_command"
        for hook in entry["hooks"]
    ]
    assert any("writ-bash-grep-guard.sh" in command for command in commands)
