"""POL-5a-plugin: patch-global-config.sh delivers the statusLine to plugin installs.

A Claude Code plugin cannot ship the main statusLine (manifest has no field; plugin
settings.json honors only agent/subagentStatusLine; hooks can't set it). It is the
same gap class as permissions/CLAUDE.md, which patch-global-config.sh already merges
into the plugin user's real ~/.claude/settings.json. This adds the statusLine to that
merge, with policy: add-if-absent / refresh-if-Writ (upgrade-safe) / leave-if-foreign.

All cases run the real script with WRIT_SETTINGS_TARGET + WRIT_CLAUDE_MD_TARGET pointed
at temp files, so the real ~/.claude is never touched.

RED until patch-global-config.sh merges the statusLine.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

SKILL_DIR = Path.home() / ".claude/skills/writ"
PATCH_SCRIPT = SKILL_DIR / "scripts" / "patch-global-config.sh"
PATCH_SRC = PATCH_SCRIPT.read_text()

EXPECTED_CMD = f"bash {SKILL_DIR}/hooks/scripts/writ-statusline.sh"

_HAVE_TOOLS = shutil.which("jq") is not None and shutil.which("envsubst") is not None
requires_tools = pytest.mark.skipif(not _HAVE_TOOLS, reason="jq/envsubst not installed")


def _write_settings(path: Path, status_line=None, with_perms: bool = True) -> None:
    d: dict = {}
    if with_perms:
        d["permissions"] = {"allow": ["Bash(existing-user-entry *)"], "deny": []}
    if status_line is not None:
        d["statusLine"] = status_line
    path.write_text(json.dumps(d, indent=2) + "\n")


def _run_patch(tmp_dir: Path, settings_path: Path) -> subprocess.CompletedProcess:
    claude_md = tmp_dir / "CLAUDE.md"
    env = {
        **os.environ,
        "WRIT_SETTINGS_TARGET": str(settings_path),
        "WRIT_CLAUDE_MD_TARGET": str(claude_md),
    }
    return subprocess.run(
        ["bash", str(PATCH_SCRIPT)],
        capture_output=True, text=True, cwd=str(SKILL_DIR), env=env, timeout=30,
    )


# --------------------------------------------------------------------------- #
# source-shape
# --------------------------------------------------------------------------- #
class TestSourceShape:
    def test_script_references_statusline(self) -> None:
        assert "writ-statusline.sh" in PATCH_SRC, (
            "patch-global-config.sh must reference the statusLine hook"
        )
        assert "statusLine" in PATCH_SRC, (
            "patch-global-config.sh must assign a statusLine in its settings merge"
        )


# --------------------------------------------------------------------------- #
# behavioral (live script, temp targets)
# --------------------------------------------------------------------------- #
@requires_tools
class TestStatusLineMerge:
    def test_absent_gets_added(self, tmp_path) -> None:
        s = tmp_path / "settings.json"
        _write_settings(s, status_line=None)
        r = _run_patch(tmp_path, s)
        assert r.returncode == 0, f"exit {r.returncode}; stderr={r.stderr[:300]!r}"
        d = json.loads(s.read_text())
        assert d.get("statusLine", {}).get("type") == "command"
        assert d["statusLine"]["command"] == EXPECTED_CMD, (
            f"absent statusLine must be added with the current path; got {d.get('statusLine')!r}"
        )

    def test_foreign_left_untouched(self, tmp_path) -> None:
        foreign = {"type": "command", "command": "bash /usr/local/bin/my-statusline.sh"}
        s = tmp_path / "settings.json"
        _write_settings(s, status_line=foreign)
        r = _run_patch(tmp_path, s)
        assert r.returncode == 0, f"exit {r.returncode}; stderr={r.stderr[:300]!r}"
        d = json.loads(s.read_text())
        assert d["statusLine"]["command"] == "bash /usr/local/bin/my-statusline.sh", (
            "a foreign statusLine must never be clobbered"
        )

    def test_stale_writ_refreshed(self, tmp_path) -> None:
        stale = {"type": "command", "command": "bash /old/install/hooks/scripts/writ-statusline.sh"}
        s = tmp_path / "settings.json"
        _write_settings(s, status_line=stale)
        r = _run_patch(tmp_path, s)
        assert r.returncode == 0, f"exit {r.returncode}; stderr={r.stderr[:300]!r}"
        d = json.loads(s.read_text())
        assert d["statusLine"]["command"] == EXPECTED_CMD, (
            "a stale Writ statusLine path must be refreshed to the current install path"
        )

    def test_idempotent_second_run(self, tmp_path) -> None:
        s = tmp_path / "settings.json"
        _write_settings(s, status_line=None)
        _run_patch(tmp_path, s)
        first = s.read_text()
        r2 = _run_patch(tmp_path, s)
        assert s.read_text() == first, "second run must leave settings byte-identical"
        assert "No changes needed" in (r2.stdout + r2.stderr)

    def test_permissions_still_merged(self, tmp_path) -> None:
        s = tmp_path / "settings.json"
        _write_settings(s, status_line=None)
        r = _run_patch(tmp_path, s)
        assert r.returncode == 0, f"exit {r.returncode}; stderr={r.stderr[:300]!r}"
        d = json.loads(s.read_text())
        allow = d["permissions"]["allow"]
        assert any("writ-session.py" in a for a in allow), "Writ allow entries must still merge"
        assert "Bash(existing-user-entry *)" in allow, "existing user entries must be preserved"
