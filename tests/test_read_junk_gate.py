"""Read-junk gate hook tests.

Exercises hooks/scripts/writ-read-junk-gate.sh (does NOT exist yet -- all
subprocess calls will fail to find the script -> RED for the right reason).

Drives the hook with synthetic CC PreToolUse envelopes on stdin (same shape
used by test_bash_write_gate.py: session_id / tool_name / tool_input.file_path).
WRIT_FRICTION_LOG is set to a tmp file so events are readable without touching
the repo log (the autouse conftest fixture already does this, but we also set
it explicitly in _run so the hook subprocess inherits it).

Exit-code contract: the hook ALWAYS exits 0 (fail-open). Deny is communicated
only via stdout JSON (permissionDecision:"deny"), never via a non-zero exit.
"""
from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest

SKILL_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
HOOK = os.path.join(SKILL_ROOT, "hooks", "scripts", "writ-read-junk-gate.sh")

_SESSION_ID = "test-read-junk-gate"


def _run(
    file_path: str,
    *,
    mode: str = "observe",
    size_kb: int | None = None,
    friction_log: str,
    extra_env: dict | None = None,
) -> subprocess.CompletedProcess:
    """Invoke the hook with a CC PreToolUse Read envelope on stdin.

    Matches the envelope shape verified from parse-hook-stdin.py:
      { session_id, tool_name, tool_input: { file_path } }

    Returns the CompletedProcess so callers can assert returncode / stdout.
    """
    envelope = json.dumps(
        {
            "session_id": _SESSION_ID,
            "tool_name": "Read",
            "tool_input": {"file_path": file_path},
        }
    )
    env = {
        **os.environ,
        "WRIT_FRICTION_LOG": friction_log,
        "WRIT_READ_JUNK_GATE": mode,
        "WRIT_NO_AUTOSTART": "1",
    }
    if size_kb is not None:
        env["WRIT_READ_SIZE_KB"] = str(size_kb)
    if extra_env:
        env.update(extra_env)
    return subprocess.run(
        ["bash", HOOK],
        input=envelope,
        capture_output=True,
        text=True,
        env=env,
        timeout=30,
    )


def _events(friction_log: str) -> list[dict]:
    """Read the JSONL friction log and return only read_blocked events."""
    p = Path(friction_log)
    if not p.exists():
        return []
    events = []
    for line in p.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            ev = json.loads(line)
        except (ValueError, json.JSONDecodeError):
            continue
        if ev.get("event") == "read_blocked":
            events.append(ev)
    return events


# ---------------------------------------------------------------------------
# TestClassification -- path blocklist and binary hits
# ---------------------------------------------------------------------------

class TestClassification:
    @pytest.mark.parametrize("file_path, expected_reason", [
        ("/project/node_modules/lodash/x.js", "path_blocklist"),
        ("/project/src/bundle.min.js", "path_blocklist"),
        ("/project/dist/main.js.map", "path_blocklist"),
        ("/project/backup/data.bak", "path_blocklist"),
        ("/project/old/config.py~", "path_blocklist"),
        ("/project/package-lock.json", "path_blocklist"),
    ])
    def test_blocklist_path_emits_path_blocklist_event(
        self, file_path, expected_reason, tmp_path
    ):
        flog = str(tmp_path / "friction.log")
        result = _run(file_path, friction_log=flog)
        assert result.returncode == 0
        evs = _events(flog)
        assert len(evs) == 1, (
            f"Expected 1 read_blocked event for {file_path}, got {len(evs)}"
        )
        assert evs[0]["block_reason"] == expected_reason, evs[0]

    def test_png_binary_emits_binary_event(self, tmp_path):
        file_path = "/project/assets/logo.png"
        flog = str(tmp_path / "friction.log")
        result = _run(file_path, friction_log=flog)
        assert result.returncode == 0
        evs = _events(flog)
        assert len(evs) == 1, f"Expected 1 read_blocked event for binary, got {len(evs)}"
        assert evs[0]["block_reason"] == "binary", evs[0]


# ---------------------------------------------------------------------------
# TestGitignore -- gitignored paths
# ---------------------------------------------------------------------------

class TestGitignore:
    def test_gitignored_file_emits_gitignore_event(self, tmp_path):
        if subprocess.run(["git", "--version"], capture_output=True).returncode != 0:
            pytest.skip("git not available")

        repo = tmp_path / "repo"
        repo.mkdir()
        subprocess.run(["git", "init", str(repo)], capture_output=True, check=True)
        (repo / ".gitignore").write_text("ignored/\n")
        ignored_dir = repo / "ignored"
        ignored_dir.mkdir()
        target = ignored_dir / "secret.txt"
        target.write_text("some content that should be ignored\n")

        flog = str(tmp_path / "friction.log")
        result = _run(str(target), friction_log=flog)
        assert result.returncode == 0
        evs = _events(flog)
        assert len(evs) == 1, f"Expected 1 read_blocked event, got {len(evs)}"
        assert evs[0]["block_reason"] == "gitignore", evs[0]


# ---------------------------------------------------------------------------
# TestSizeGate -- oversized files
# ---------------------------------------------------------------------------

class TestSizeGate:
    def test_oversized_file_emits_size_gate_event(self, tmp_path):
        # Write a file that exceeds the 1 KB threshold we pass as size_kb=1.
        target = tmp_path / "large.txt"
        target.write_bytes(b"x" * 4096)  # 4 KB

        flog = str(tmp_path / "friction.log")
        result = _run(str(target), size_kb=1, friction_log=flog)
        assert result.returncode == 0
        evs = _events(flog)
        assert len(evs) == 1, (
            f"Expected 1 read_blocked event for oversized file, got {len(evs)}"
        )
        assert evs[0]["block_reason"] == "size_gate", evs[0]

    def test_under_threshold_file_emits_no_event(self, tmp_path):
        # Write a file smaller than the threshold.
        target = tmp_path / "small.txt"
        target.write_bytes(b"x" * 100)  # well under 1 KB

        flog = str(tmp_path / "friction.log")
        result = _run(str(target), size_kb=1, friction_log=flog)
        assert result.returncode == 0
        evs = _events(flog)
        assert len(evs) == 0, (
            f"Expected no events for under-threshold file, got {evs}"
        )


# ---------------------------------------------------------------------------
# TestObserveMode -- observe is the default: never deny, would_block=True, enforced=False
# ---------------------------------------------------------------------------

class TestObserveMode:
    def test_observe_mode_stdout_is_empty_for_junk_path(self, tmp_path):
        # node_modules path is always junk; in observe mode the hook exits 0 silently.
        flog = str(tmp_path / "friction.log")
        result = _run(
            "/project/node_modules/react/index.js",
            mode="observe",
            friction_log=flog,
        )
        assert result.returncode == 0
        assert result.stdout.strip() == "", (
            f"Observe mode must produce no stdout (no deny); got: {result.stdout!r}"
        )

    def test_observe_mode_event_has_would_block_true_and_enforced_false(self, tmp_path):
        flog = str(tmp_path / "friction.log")
        _run(
            "/project/node_modules/react/index.js",
            mode="observe",
            friction_log=flog,
        )
        evs = _events(flog)
        assert len(evs) == 1
        assert evs[0].get("would_block") is True, evs[0]
        assert evs[0].get("enforced") is False, evs[0]


# ---------------------------------------------------------------------------
# TestEnforceMode -- enforce: stdout is deny JSON with a redirect recipe
# ---------------------------------------------------------------------------

class TestEnforceMode:
    def test_enforce_mode_emits_deny_json_with_permission_decision(self, tmp_path):
        flog = str(tmp_path / "friction.log")
        result = _run(
            "/project/node_modules/lodash/x.js",
            mode="enforce",
            friction_log=flog,
        )
        assert result.returncode == 0
        assert result.stdout.strip() != "", (
            "Enforce mode must emit a deny JSON on stdout"
        )
        parsed = json.loads(result.stdout.strip())
        hso = parsed.get("hookSpecificOutput", {})
        assert hso.get("permissionDecision") == "deny", parsed

    def test_enforce_mode_deny_reason_contains_redirect_recipe(self, tmp_path):
        flog = str(tmp_path / "friction.log")
        result = _run(
            "/project/node_modules/lodash/x.js",
            mode="enforce",
            friction_log=flog,
        )
        parsed = json.loads(result.stdout.strip())
        reason = parsed.get("hookSpecificOutput", {}).get("permissionDecisionReason", "")
        # The redirect recipe advertises `rg` (ripgrep) as the cheap alternative.
        assert "rg" in reason, (
            f"permissionDecisionReason must contain the rg redirect recipe; got: {reason!r}"
        )


# ---------------------------------------------------------------------------
# TestFailOpen -- missing file_path, stat-failure paths
# ---------------------------------------------------------------------------

class TestFailOpen:
    def test_missing_file_path_exits_0_empty_stdout_no_event(self, tmp_path):
        # Envelope with no file_path: hook must not crash-block.
        envelope = json.dumps(
            {"session_id": _SESSION_ID, "tool_name": "Read", "tool_input": {}}
        )
        flog = str(tmp_path / "friction.log")
        env = {
            **os.environ,
            "WRIT_FRICTION_LOG": flog,
            "WRIT_READ_JUNK_GATE": "observe",
            "WRIT_NO_AUTOSTART": "1",
        }
        result = subprocess.run(
            ["bash", HOOK],
            input=envelope,
            capture_output=True,
            text=True,
            env=env,
            timeout=30,
        )
        assert result.returncode == 0
        assert result.stdout.strip() == ""
        assert len(_events(flog)) == 0

    def test_nonexistent_junk_path_does_not_crash(self, tmp_path):
        # A path that matches the blocklist but does not exist on disk (stat fails).
        flog = str(tmp_path / "friction.log")
        result = _run(
            "/project/node_modules/lodash/x.js",
            friction_log=flog,
        )
        # Must exit 0 regardless of stat failure on a non-existent path.
        assert result.returncode == 0


# ---------------------------------------------------------------------------
# TestPreventedFloor -- bytes/4 floor and gross_bytes_upper_bound
# ---------------------------------------------------------------------------

class TestPreventedFloor:
    def test_text_file_floor_equals_bytes_divided_by_4(self, tmp_path):
        # Use a *.bak path (blocklist hit) so we control the file and get real stat bytes.
        content = b"a" * 200
        bak = tmp_path / "data.bak"
        bak.write_bytes(content)
        file_bytes = len(content)

        flog = str(tmp_path / "friction.log")
        _run(str(bak), friction_log=flog)
        evs = _events(flog)
        assert len(evs) == 1
        ev = evs[0]
        expected_floor = file_bytes // 4
        assert ev["prevented_tokens_floor"] == expected_floor, ev
        assert ev["gross_bytes_upper_bound"] == file_bytes, ev

    def test_binary_extension_floor_is_zero_gross_bytes_is_file_bytes(self, tmp_path):
        # For a binary extension, prevented_tokens_floor must be 0.
        content = b"\x89PNG" + b"\x00" * 196  # 200 bytes
        target = tmp_path / "image.png"
        target.write_bytes(content)
        file_bytes = len(content)

        flog = str(tmp_path / "friction.log")
        _run(str(target), friction_log=flog)
        evs = _events(flog)
        assert len(evs) == 1
        ev = evs[0]
        assert ev["prevented_tokens_floor"] == 0, (
            f"Binary extension must have floor=0; got: {ev}"
        )
        assert ev["gross_bytes_upper_bound"] == file_bytes, ev


# ---------------------------------------------------------------------------
# TestCredentialNotSpecialCased -- credential-looking paths are NOT blocked by
# the junk gate unless they independently match a junk rule
# ---------------------------------------------------------------------------

class TestCredentialNotSpecialCased:
    def test_small_private_key_file_not_blocked_by_junk_gate(self, tmp_path):
        # A small file named id_rsa that is NOT under a junk dir and NOT gitignored
        # must produce NO read_blocked event. The credential guard is a write-path
        # concern (gates.py); the junk gate must not duplicate it for reads.
        target = tmp_path / "id_rsa"
        # Write a plausible placeholder -- no real key material, just the shape.
        target.write_text("placeholder-key-content\n")

        flog = str(tmp_path / "friction.log")
        result = _run(str(target), friction_log=flog)
        assert result.returncode == 0
        evs = _events(flog)
        assert len(evs) == 0, (
            f"Junk gate must NOT block credential-looking files; got events: {evs}"
        )

    def test_small_env_file_not_blocked_by_junk_gate(self, tmp_path):
        # A small .env file not under a junk directory must not be blocked here.
        target = tmp_path / "x.env"
        target.write_text("DB_HOST=localhost\n")

        flog = str(tmp_path / "friction.log")
        result = _run(str(target), friction_log=flog)
        assert result.returncode == 0
        evs = _events(flog)
        assert len(evs) == 0, (
            f"Junk gate must NOT block .env files (not a junk pattern); got events: {evs}"
        )


# ---------------------------------------------------------------------------
# TestLegitimateSourceNotBlocked -- under-threshold source files are always allowed
# ---------------------------------------------------------------------------

class TestLegitimateSourceNotBlocked:
    def test_small_py_source_file_not_blocked_and_empty_stdout(self, tmp_path):
        src = tmp_path / "src"
        src.mkdir()
        target = src / "foo.py"
        target.write_text("def hello(): pass\n")

        flog = str(tmp_path / "friction.log")
        result = _run(str(target), friction_log=flog)
        assert result.returncode == 0
        assert result.stdout.strip() == "", (
            f"Legitimate source must never be denied; stdout: {result.stdout!r}"
        )
        evs = _events(flog)
        assert len(evs) == 0, (
            f"Legitimate source must not emit read_blocked; got: {evs}"
        )
