"""Regression tests for legacy session-cache schema migration.

Context: hooks call `python3 writ-session.py update <sid> --add-rules ...`
on every UserPromptSubmit and PostToolUse:Write. If the on-disk cache
file lacks a key the new code expects (`loaded_rule_ids`, etc.),
`cmd_update` raises `KeyError` and the hook -- which redirects stderr
to /dev/null -- swallows the failure. The result is silent dedupe
breakage and runaway RAG re-injection.

These tests pin the migration contract: `_read_cache` must populate
the four keys on legacy files, and `cmd_update` must not raise on
caches that still slipped through.

Per TEST-TDD-001 / TEST-ISO-001.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys

import pytest
from pathlib import Path

SKILL_DIR = str(Path.home() / ".claude/skills/writ")
WRIT_SESSION_PY = f"{SKILL_DIR}/bin/lib/writ-session.py"


def _legacy_cache(extra: dict | None = None) -> dict:
    """A cache shaped like the pre-migration schema -- has `loaded_rules`
    (objects), but lacks `loaded_rule_ids`, `remaining_budget`,
    `context_percent`, `queries`."""
    base = {
        "loaded_rules": [],
        "mode": None,
        "is_subagent": False,
        "files_written": [],
        "loaded_rule_ids_by_phase": {},
        "current_phase": None,
    }
    if extra:
        base.update(extra)
    return base


def _write_legacy(cache_dir: str, session_id: str, payload: dict) -> str:
    path = os.path.join(cache_dir, f"writ-session-{session_id}.json")
    with open(path, "w") as f:
        json.dump(payload, f)
    return path


def _run_subprocess(
    cache_dir: str, *args: str
) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["WRIT_CACHE_DIR"] = cache_dir
    return subprocess.run(
        [sys.executable, WRIT_SESSION_PY, *args],
        capture_output=True,
        text=True,
        env=env,
    )


class TestLegacyCacheMigration:
    """Schema-migration safety net for sessions persisted before the
    rename to `loaded_rule_ids` (and the budget/queries split)."""

    def test_read_cache_adds_loaded_rule_ids_to_legacy_cache(
        self, tmp_path
    ) -> None:
        sid = "legacy-sess-1"
        _write_legacy(str(tmp_path), sid, _legacy_cache())

        result = _run_subprocess(str(tmp_path), "read", sid)

        assert result.returncode == 0, result.stderr
        cache = json.loads(result.stdout)
        assert "loaded_rule_ids" in cache
        assert cache["loaded_rule_ids"] == []

    def test_read_cache_adds_remaining_budget_to_legacy_cache(
        self, tmp_path
    ) -> None:
        sid = "legacy-sess-2"
        _write_legacy(str(tmp_path), sid, _legacy_cache())

        result = _run_subprocess(str(tmp_path), "read", sid)

        assert result.returncode == 0, result.stderr
        cache = json.loads(result.stdout)
        assert "remaining_budget" in cache
        assert isinstance(cache["remaining_budget"], int)
        assert cache["remaining_budget"] > 0

    def test_read_cache_adds_context_percent_and_queries_to_legacy_cache(
        self, tmp_path
    ) -> None:
        sid = "legacy-sess-3"
        _write_legacy(str(tmp_path), sid, _legacy_cache())

        result = _run_subprocess(str(tmp_path), "read", sid)

        assert result.returncode == 0, result.stderr
        cache = json.loads(result.stdout)
        assert cache.get("context_percent") == 0
        assert cache.get("queries") == 0

    def test_cmd_update_succeeds_on_legacy_cache_missing_loaded_rule_ids(
        self, tmp_path
    ) -> None:
        sid = "legacy-sess-4"
        _write_legacy(str(tmp_path), sid, _legacy_cache())

        result = _run_subprocess(
            str(tmp_path),
            "update",
            sid,
            "--add-rules",
            json.dumps(["TEST-RULE-001"]),
            "--cost",
            "0",
            "--inc-queries",
        )

        assert result.returncode == 0, (
            f"cmd_update raised on legacy cache: stderr={result.stderr}"
        )

        read = _run_subprocess(str(tmp_path), "read", sid)
        cache = json.loads(read.stdout)
        assert "TEST-RULE-001" in cache["loaded_rule_ids"]
        by_phase = cache.get("loaded_rule_ids_by_phase", {})
        assert any(
            "TEST-RULE-001" in ids for ids in by_phase.values()
        ), f"rule not landed in any phase bucket: {by_phase}"

    def test_cmd_update_accumulates_across_calls_on_legacy_cache(
        self, tmp_path
    ) -> None:
        """Pin the dedupe-relevant invariant: repeated --add-rules
        calls accumulate, so subsequent inject hooks see the
        accumulated set as exclude_rule_ids."""
        sid = "legacy-sess-5"
        _write_legacy(str(tmp_path), sid, _legacy_cache())

        for rid in ("R1", "R2", "R3"):
            r = _run_subprocess(
                str(tmp_path),
                "update",
                sid,
                "--add-rules",
                json.dumps([rid]),
            )
            assert r.returncode == 0, r.stderr

        read = _run_subprocess(str(tmp_path), "read", sid)
        cache = json.loads(read.stdout)
        assert set(cache["loaded_rule_ids"]) >= {"R1", "R2", "R3"}
