"""Increment 4: debug-mode source-edit gate.

In debug mode, `_can_write_check` blocks Write/Edit to SOURCE files until a
debug.md with a populated `## Root cause` exists -- the diagnostic analogue of
Work mode's plan gate. Presence-only (never a truth check); Evidence/
Falsification/Triangulation stay advisory.

Tested by calling `_can_write_check` directly (the live `skill_dir` bypass means
this cannot be a live-session test), mirroring tests/test_pre_write_dispatch.py.
"""
from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
from typing import Any

import pytest

SID = "test-debug-gate"
SKILL_DIR = str(Path(__file__).resolve().parent.parent)
WRIT_SESSION_PY = f"{SKILL_DIR}/bin/lib/writ-session.py"
TEMPLATE = Path(SKILL_DIR) / "templates" / "debug.md"

POPULATED_DEBUG_MD = (
    "## Symptom\nSaves are slow for one SKU pattern.\n\n"
    "## Root cause\nThe fan-out fires once per attribute because the guard "
    "compares the wrong field, so 8 writes happen instead of 1.\n\n"
    "## Fix\nCompare the canonical field before fanning out.\n"
)
EMPTY_ROOT_CAUSE_MD = "## Symptom\nSomething is slow.\n\n## Root cause\n\n## Fix\n\n"
NO_ROOT_CAUSE_MD = "## Symptom\nSomething is slow.\n\n## Hypothesis\nMaybe the cache.\n"


def _load_writ_session():
    spec = importlib.util.spec_from_file_location("writ_session_debug_gate", WRIT_SESSION_PY)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _debug_cache(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "session_id": SID,
        "mode": "debug",
        "is_subagent": False,
        "current_phase": None,
        "remaining_budget": 5000,
        "context_percent": 30,
        "loaded_rule_ids": [],
        "loaded_rules": [],
        "loaded_rule_ids_by_phase": {},
        "queries": 0,
        "gates_approved": [],
        "denial_counts": {},
    }
    base.update(overrides)
    return base


def _check(monkeypatch, mod, tmp_path: Path, cache: dict, *, file_relpath: str = "src/app.py",
           debug_md_body: str | None = None) -> dict:
    """Seed the cache, build a tmp project (with .git marker and optional
    debug.md), and run _can_write_check on a source-file write."""
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir(exist_ok=True)
    monkeypatch.setenv("WRIT_CACHE_DIR", str(cache_dir))
    with open(mod._cache_path(SID), "w") as f:
        json.dump(cache, f)

    proj = tmp_path / "proj"
    (proj / ".git").mkdir(parents=True, exist_ok=True)
    if debug_md_body is not None:
        (proj / "debug.md").write_text(debug_md_body)
    target = proj / file_relpath
    target.parent.mkdir(parents=True, exist_ok=True)
    return mod._can_write_check(SID, {"tool_input": {"file_path": str(target)}})


class TestDebugGateHelpers:
    """The two new helpers exist and behave (presence-only)."""

    def test_find_debug_md_exists(self) -> None:
        mod = _load_writ_session()
        assert hasattr(mod, "_find_debug_md") and callable(mod._find_debug_md)

    def test_validate_root_cause_exists(self) -> None:
        mod = _load_writ_session()
        assert hasattr(mod, "_validate_root_cause") and callable(mod._validate_root_cause)

    def test_validate_root_cause_passes_when_populated(self, tmp_path: Path) -> None:
        mod = _load_writ_session()
        assert hasattr(mod, "_validate_root_cause"), "_validate_root_cause not defined yet"
        p = tmp_path / "debug.md"
        p.write_text(POPULATED_DEBUG_MD)
        assert mod._validate_root_cause(str(p)) is None

    def test_validate_root_cause_fails_when_empty(self, tmp_path: Path) -> None:
        mod = _load_writ_session()
        assert hasattr(mod, "_validate_root_cause"), "_validate_root_cause not defined yet"
        p = tmp_path / "debug.md"
        p.write_text(EMPTY_ROOT_CAUSE_MD)
        assert mod._validate_root_cause(str(p)) is not None

    def test_validate_root_cause_fails_when_missing(self, tmp_path: Path) -> None:
        mod = _load_writ_session()
        assert hasattr(mod, "_validate_root_cause"), "_validate_root_cause not defined yet"
        p = tmp_path / "debug.md"
        p.write_text(NO_ROOT_CAUSE_MD)
        assert mod._validate_root_cause(str(p)) is not None


class TestDebugSourceEditGate:
    """The gate denies/allows source writes in debug mode per root-cause state."""

    def test_source_denied_when_no_debug_md(self, tmp_path: Path, monkeypatch) -> None:
        mod = _load_writ_session()
        result = _check(monkeypatch, mod, tmp_path, _debug_cache(), debug_md_body=None)
        assert result["can_write"] is False
        assert "DEBUG-GATE-ROOT-CAUSE" in (result.get("reason") or "")

    def test_source_allowed_when_root_cause_populated(self, tmp_path: Path, monkeypatch) -> None:
        mod = _load_writ_session()
        result = _check(monkeypatch, mod, tmp_path, _debug_cache(), debug_md_body=POPULATED_DEBUG_MD)
        assert result["can_write"] is True, result.get("reason")

    def test_source_denied_when_root_cause_empty(self, tmp_path: Path, monkeypatch) -> None:
        mod = _load_writ_session()
        result = _check(monkeypatch, mod, tmp_path, _debug_cache(), debug_md_body=EMPTY_ROOT_CAUSE_MD)
        assert result["can_write"] is False
        assert "DEBUG-GATE-ROOT-CAUSE" in (result.get("reason") or "")

    def test_debug_md_itself_always_writable(self, tmp_path: Path, monkeypatch) -> None:
        """Anti-deadlock: the agent must be able to author debug.md."""
        mod = _load_writ_session()
        result = _check(monkeypatch, mod, tmp_path, _debug_cache(), file_relpath="debug.md", debug_md_body=None)
        assert result["can_write"] is True, result.get("reason")

    def test_excluded_path_writable_for_evidence(self, tmp_path: Path, monkeypatch) -> None:
        """Test files (exclusions) stay writable so evidence/repro can be recorded."""
        mod = _load_writ_session()
        result = _check(monkeypatch, mod, tmp_path, _debug_cache(),
                        file_relpath="tests/test_repro.py", debug_md_body=None)
        assert result["can_write"] is True, result.get("reason")

    def test_subagent_bypasses_debug_gate(self, tmp_path: Path, monkeypatch) -> None:
        mod = _load_writ_session()
        result = _check(monkeypatch, mod, tmp_path, _debug_cache(is_subagent=True), debug_md_body=None)
        assert result["can_write"] is True, result.get("reason")


class TestDebugGateRegression:
    """Work / conversation / no-mode write behavior is unchanged."""

    def test_work_mode_source_still_gated(self, tmp_path: Path, monkeypatch) -> None:
        mod = _load_writ_session()
        result = _check(monkeypatch, mod, tmp_path, _debug_cache(mode="work", gates_approved=[],
                                                    current_phase="planning"), debug_md_body=None)
        assert result["can_write"] is False
        assert "ENF-GATE-PLAN" in (result.get("reason") or "")

    def test_conversation_mode_allows_source(self, tmp_path: Path, monkeypatch) -> None:
        mod = _load_writ_session()
        result = _check(monkeypatch, mod, tmp_path, _debug_cache(mode="conversation"), debug_md_body=None)
        assert result["can_write"] is True, result.get("reason")

    def test_no_mode_denies_source(self, tmp_path: Path, monkeypatch) -> None:
        mod = _load_writ_session()
        result = _check(monkeypatch, mod, tmp_path, _debug_cache(mode=None), debug_md_body=None)
        assert result["can_write"] is False
        assert "ENF-GATE-MODE" in (result.get("reason") or "")


class TestDebugTemplate:
    """The debug.md scaffold the deny directive points to."""

    def test_template_exists_with_root_cause_section(self) -> None:
        assert TEMPLATE.exists(), f"{TEMPLATE} must exist"
        body = TEMPLATE.read_text()
        assert "## Root cause" in body, "template must include the gated ## Root cause section"
        for advisory in ("## Evidence", "## Falsification", "## Triangulation"):
            assert advisory in body, f"template should include advisory section {advisory}"