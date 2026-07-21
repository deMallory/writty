"""F3: the write gate logs (but does not gate) edits to its own skill dir.

_can_write_check exempts files under skill_dir and under ~/.claude/settings from
gating -- you cannot require gate approval to edit the gate itself. But the exempt
allow used to return WITHOUT emitting write_attempt, so editing Writ's own repo (the
skill dir) produced zero write telemetry: Writ was blind to its own development.
These tests pin that the exempt allow is now LOGGED (result=allow, gate_status=
skill_exempt/settings_exempt) while still allowing the write.

M2 (Wave 1 Cycle 3): the settings exemption used a bare
`file_path.startswith(os.path.join(home, ".claude", "settings"))` prefix match, which
also matched impostors like settings-evil.json and settingsX/anything under ~/.claude,
letting them bypass every write gate and be logged as a legitimate settings_exempt
allow. The tests below pin that only the exact basenames settings.json and
settings.local.json directly under ~/.claude are exempt; everything else falls
through to the mode gate (a fresh cache has mode=None, so it is denied no_mode).
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest


def _write_attempts(log: Path) -> list[dict]:
    if not log.exists():
        return []
    out = []
    for line in log.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            e = json.loads(line)
        except json.JSONDecodeError:
            continue
        if e.get("event") == "write_attempt":
            out.append(e)
    return out


def test_skill_dir_write_logged_and_allowed(tmp_path, monkeypatch) -> None:
    # autouse _isolate_friction_log points WRIT_FRICTION_LOG at tmp_path/workflow-friction.log
    monkeypatch.setenv("WRIT_CACHE_DIR", str(tmp_path / "cache"))
    (tmp_path / "cache").mkdir()
    from writ.session.gates import _can_write_check

    skill = str(tmp_path / "skill")
    target = f"{skill}/writ/session/gates.py"
    result = _can_write_check("sid-f3-skill", {"tool_input": {"file_path": target}}, skill_dir=skill)
    assert result["can_write"] is True, "skill-dir edits stay exempt (allowed)"

    wa = _write_attempts(tmp_path / "workflow-friction.log")
    assert wa, "a skill-dir write must now emit a write_attempt (self-observability)"
    last = wa[-1]
    assert last["gate_status"] == "skill_exempt"
    assert last["result"] == "allow"
    assert last["file_path"] == target


def test_settings_write_logged_and_allowed(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("WRIT_CACHE_DIR", str(tmp_path / "cache"))
    (tmp_path / "cache").mkdir()
    from writ.session.gates import _can_write_check

    home = os.environ.get("HOME", "")
    target = os.path.join(home, ".claude", "settings.json")
    result = _can_write_check(
        "sid-f3-settings", {"tool_input": {"file_path": target}}, skill_dir=str(tmp_path / "other")
    )
    assert result["can_write"] is True

    wa = _write_attempts(tmp_path / "workflow-friction.log")
    assert wa, "a ~/.claude/settings write must emit a write_attempt"
    assert wa[-1]["gate_status"] == "settings_exempt"
    assert wa[-1]["result"] == "allow"


def test_settings_local_json_exempt(tmp_path, monkeypatch) -> None:
    """settings.local.json directly under ~/.claude stays exempt (M2 invariant)."""
    monkeypatch.setenv("WRIT_CACHE_DIR", str(tmp_path / "cache"))
    (tmp_path / "cache").mkdir()
    from writ.session.gates import _can_write_check

    home = os.environ.get("HOME", "")
    target = os.path.join(home, ".claude", "settings.local.json")
    result = _can_write_check(
        "sid-m2-local", {"tool_input": {"file_path": target}}, skill_dir=str(tmp_path / "other")
    )
    assert result["can_write"] is True
    wa = _write_attempts(tmp_path / "workflow-friction.log")
    assert wa and wa[-1]["gate_status"] == "settings_exempt"


def test_settings_evil_json_not_exempt(tmp_path, monkeypatch) -> None:
    """A settings-prefixed impostor (settings-evil.json) must NOT bypass the gate.

    Regression for the prefix-match bug: startswith("~/.claude/settings") also
    matches settings-evil.json. A fresh cache has mode=None, so a non-exempt path
    is denied no_mode -- this asserts the impostor reaches that denial instead of
    being waved through as settings_exempt.
    """
    monkeypatch.setenv("WRIT_CACHE_DIR", str(tmp_path / "cache"))
    (tmp_path / "cache").mkdir()
    from writ.session.gates import _can_write_check

    home = os.environ.get("HOME", "")
    target = os.path.join(home, ".claude", "settings-evil.json")
    result = _can_write_check(
        "sid-m2-evil", {"tool_input": {"file_path": target}}, skill_dir=str(tmp_path / "other")
    )
    assert result["can_write"] is False, "settings-evil.json must not bypass the gate"
    wa = _write_attempts(tmp_path / "workflow-friction.log")
    assert not any(e.get("gate_status") == "settings_exempt" for e in wa), (
        "a settings-prefixed impostor must never be logged as settings_exempt"
    )


def test_settings_subdir_not_exempt(tmp_path, monkeypatch) -> None:
    """A settings-prefixed sub-directory (settingsX/foo.json) must NOT be exempt."""
    monkeypatch.setenv("WRIT_CACHE_DIR", str(tmp_path / "cache"))
    (tmp_path / "cache").mkdir()
    from writ.session.gates import _can_write_check

    home = os.environ.get("HOME", "")
    target = os.path.join(home, ".claude", "settingsX", "foo.json")
    result = _can_write_check(
        "sid-m2-subdir", {"tool_input": {"file_path": target}}, skill_dir=str(tmp_path / "other")
    )
    assert result["can_write"] is False
    wa = _write_attempts(tmp_path / "workflow-friction.log")
    assert not any(e.get("gate_status") == "settings_exempt" for e in wa)


def test_settings_json_outside_claude_not_exempt(tmp_path, monkeypatch) -> None:
    """An out-of-tree settings.json (not under ~/.claude) must NOT be exempt."""
    monkeypatch.setenv("WRIT_CACHE_DIR", str(tmp_path / "cache"))
    (tmp_path / "cache").mkdir()
    from writ.session.gates import _can_write_check

    target = str(tmp_path / "settings.json")  # not under ~/.claude
    result = _can_write_check(
        "sid-m2-outside", {"tool_input": {"file_path": target}}, skill_dir=str(tmp_path / "other")
    )
    assert result["can_write"] is False
    wa = _write_attempts(tmp_path / "workflow-friction.log")
    assert not any(e.get("gate_status") == "settings_exempt" for e in wa)


def test_settings_symlink_traversal_not_exempt(tmp_path, monkeypatch) -> None:
    """A symlink-traversal path escaping ~/.claude must NOT be exempt (realpath, not normpath).

    Adversarial-review PoC: `~/.claude/<symlinked-dir>/../settings.json` collapses
    LEXICALLY under os.path.normpath to `~/.claude/settings.json` (basename + dirname
    both match) and is waved through as settings_exempt -- yet the OS follows the symlink
    and writes an ARBITRARY file outside ~/.claude. os.path.realpath resolves the symlink
    first, so the crafted path resolves to its true out-of-tree target and is denied. This
    test FAILS against the normpath version and PASSES after the realpath fix.
    """
    fake_home = tmp_path / "home"
    claude = fake_home / ".claude"
    claude.mkdir(parents=True)
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    link = claude / "linkdir"
    try:
        os.symlink(elsewhere, link)  # ~/.claude/linkdir -> tmp_path/elsewhere
    except (OSError, NotImplementedError):
        pytest.skip("filesystem does not support symlinks")

    monkeypatch.setenv("HOME", str(fake_home))
    monkeypatch.setenv("WRIT_CACHE_DIR", str(tmp_path / "cache"))
    (tmp_path / "cache").mkdir()
    from writ.session.gates import _can_write_check

    # realpath: linkdir -> elsewhere, then `..` -> tmp_path, so this resolves to
    # tmp_path/settings.json, which is NOT under ~/.claude.
    crafted = os.path.join(str(claude), "linkdir", "..", "settings.json")
    result = _can_write_check(
        "sid-m2-symlink", {"tool_input": {"file_path": crafted}}, skill_dir=str(tmp_path / "other")
    )
    assert result["can_write"] is False, (
        "a symlink-traversal path escaping ~/.claude must not be waved through as settings_exempt"
    )
    wa = _write_attempts(tmp_path / "workflow-friction.log")
    assert not any(e.get("gate_status") == "settings_exempt" for e in wa), (
        "a symlink-traversal impostor must never be logged as settings_exempt"
    )


def test_symlinked_settings_json_not_exempt(tmp_path, monkeypatch) -> None:
    """A ~/.claude/settings.json that is ITSELF a symlink to an out-of-tree file is denied.

    The stronger variant: if settings.json is a symlink to /etc/cron.d/evil, normpath-based
    matching still exempts it. realpath resolves the link to its target, whose basename is
    not in the allowlist, so it falls through to the mode gate. This fail-closes on a
    legitimately-symlinked settings.json, which is the accepted trade-off for closing the
    traversal bypass.
    """
    fake_home = tmp_path / "home"
    claude = fake_home / ".claude"
    claude.mkdir(parents=True)
    evil_target = tmp_path / "evil-target"
    evil_target.write_text("x")
    settings_link = claude / "settings.json"
    try:
        os.symlink(evil_target, settings_link)  # ~/.claude/settings.json -> out-of-tree file
    except (OSError, NotImplementedError):
        pytest.skip("filesystem does not support symlinks")

    monkeypatch.setenv("HOME", str(fake_home))
    monkeypatch.setenv("WRIT_CACHE_DIR", str(tmp_path / "cache"))
    (tmp_path / "cache").mkdir()
    from writ.session.gates import _can_write_check

    target = os.path.join(str(claude), "settings.json")
    result = _can_write_check(
        "sid-m2-symlinked-settings", {"tool_input": {"file_path": target}}, skill_dir=str(tmp_path / "other")
    )
    assert result["can_write"] is False, (
        "a settings.json that is itself a symlink to an out-of-tree file must not be exempt"
    )
    wa = _write_attempts(tmp_path / "workflow-friction.log")
    assert not any(e.get("gate_status") == "settings_exempt" for e in wa)
