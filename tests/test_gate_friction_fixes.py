"""Gate friction fixes (2026-09-13): the small causes behind "I had to type approved
again" and "I had to edit plan.md myself".

- Docs and scratch files are not plan-gated in work mode (gate-categories.json).
- The implementation-phase plan.md denial names the command that starts a new task.
- /writ-approve no longer tells the agent to read the token file (the Bash gate
  refuses that, so the command could only ever fail).
- ensure-server compares the daemon's cache dir against the RESOLVED hook dir, and
  SessionStart realigns on macOS, so a daemon born on another store is healed.
"""
from __future__ import annotations

import importlib
import os
import sys
import uuid
from pathlib import Path

SKILL_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
WRIT_ROOT = Path(SKILL_ROOT)


def _imp(name):
    if SKILL_ROOT not in sys.path:
        sys.path.insert(0, SKILL_ROOT)
    return importlib.import_module(name)


def _seed_work_unapproved() -> str:
    cache = _imp("writ.session.cache")
    sid = f"gff-{uuid.uuid4().hex[:8]}"
    data = cache._read_cache(sid)
    data.update(mode="work", gates_approved=[], current_phase="planning")
    cache._write_cache(sid, data)
    return sid


def _check(path: str) -> dict:
    gates = _imp("writ.session.gates")
    return gates._can_write_check(
        _seed_work_unapproved(), {"tool_input": {"file_path": path}}, "/nonexistent/other-skill"
    )


class TestDocsAndScratchAreNotPlanGated:
    def test_markdown_allowed_before_approval(self, tmp_path, monkeypatch):
        monkeypatch.setenv("WRIT_CACHE_DIR", str(tmp_path))
        assert _check("/proj/README.md")["can_write"] is True

    def test_text_allowed_before_approval(self, tmp_path, monkeypatch):
        monkeypatch.setenv("WRIT_CACHE_DIR", str(tmp_path))
        assert _check("/proj/notes.txt")["can_write"] is True

    def test_scratchpad_allowed_before_approval(self, tmp_path, monkeypatch):
        monkeypatch.setenv("WRIT_CACHE_DIR", str(tmp_path))
        assert _check("/private/tmp/claude/claude-1/x/scratchpad/sheet.html")["can_write"] is True
        assert _check("/tmp/claude/claude-1/x/scratchpad/sheet.html")["can_write"] is True
        # Only the Claude scratchpad root is exempt; a project living under /tmp is still gated.
        assert _check("/tmp/proj/src/a.py")["can_write"] is False

    def test_source_still_denied(self, tmp_path, monkeypatch):
        monkeypatch.setenv("WRIT_CACHE_DIR", str(tmp_path))
        res = _check("/proj/src/x.py")
        assert res["can_write"] is False
        assert "ENF-GATE-PLAN" in (res["reason"] or "")


class TestImplementationPlanDenialNamesReset:
    def test_reason_names_mode_set_work(self):
        gates = _imp("writ.session.gates")
        res = gates._check_special_files("plan.md", "work", "implementation")
        assert res is not None and res["can_write"] is False
        assert "mode set work" in (res["reason"] or ""), (
            "the agent can run the reset itself only if the denial names it"
        )


class TestWritApproveIsStatusOnly:
    def test_neither_copy_reads_the_token_or_posts(self):
        for path in (WRIT_ROOT / ".claude" / "commands" / "writ-approve.md",
                     WRIT_ROOT / "templates" / "commands" / "writ-approve.md"):
            content = path.read_text()
            assert "writ-gate-token" not in content, f"{path} must not read the token file"
            assert "advance-phase" not in content, f"{path} must not POST the advance"
            assert "approved" in content, f"{path} must tell the user what to type"


class TestEnsureServerAlignsToResolvedDir:
    def test_lib_compares_against_resolved_dir(self):
        body = (WRIT_ROOT / "scripts" / "lib" / "writ-server-lib.sh").read_text()
        assert '"$running_cache" != "$(writ_session_cache_dir)"' in body, (
            "alignment must compare the daemon's cache_dir with the RESOLVED hook dir, "
            "not only with a raw WRIT_CACHE_DIR env value"
        )

    def test_bootstrap_realigns_on_darwin(self):
        body = (WRIT_ROOT / "hooks" / "scripts" / "session-start-bootstrap.sh").read_text()
        assert "WRIT_REALIGN_CACHE" in body and "Darwin" in body, (
            "SessionStart must opt into realign where no systemd unit owns the daemon"
        )
