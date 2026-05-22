"""Always-on bundle budget tracking -- session cache schema migration.

Context: the always-on bundle (~500-800 tokens/turn when populated) is
re-injected on every UserPromptSubmit. Without independent budget
tracking, cumulative cost is opaque. This adds `always_on_budget` (cap)
and `always_on_tokens_used` (running total) to the session cache, plus
a `--add-always-on-tokens N` flag.

The schema-migration tests mirror tests/test_session_cache_migration.py
to prevent the same silent-KeyError pattern that broke RAG dedupe.
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
DEFAULT_CAP = 5000


def _legacy_cache(extra: dict | None = None) -> dict:
    """Pre-Part-C cache shape -- has the standard fields but lacks the
    new always-on tracking pair."""
    base = {
        "loaded_rules": [],
        "loaded_rule_ids": [],
        "remaining_budget": 8000,
        "context_percent": 0,
        "queries": 0,
        "mode": "work",
        "is_subagent": False,
        "files_written": [],
        "loaded_rule_ids_by_phase": {},
        "current_phase": "implementation",
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


class TestAlwaysOnBudgetSchemaMigration:
    """Legacy caches must back-fill the new fields via _read_cache
    setdefault, mirroring the legacy_rule_ids hotfix pattern."""

    def test_legacy_cache_gets_always_on_budget_default(
        self, tmp_path
    ) -> None:
        sid = "ao-legacy-1"
        _write_legacy(str(tmp_path), sid, _legacy_cache())

        result = _run_subprocess(str(tmp_path), "read", sid)

        assert result.returncode == 0, result.stderr
        cache = json.loads(result.stdout)
        assert cache.get("always_on_budget") == DEFAULT_CAP
        assert cache.get("always_on_tokens_used") == 0

    def test_legacy_cache_preserves_existing_always_on_budget(
        self, tmp_path
    ) -> None:
        """If the field is already set (e.g. from a prior decrement),
        _read_cache must not clobber it."""
        sid = "ao-legacy-2"
        _write_legacy(
            str(tmp_path),
            sid,
            _legacy_cache({"always_on_budget": 1234, "always_on_tokens_used": 76}),
        )

        result = _run_subprocess(str(tmp_path), "read", sid)

        assert result.returncode == 0, result.stderr
        cache = json.loads(result.stdout)
        assert cache["always_on_budget"] == 1234
        assert cache["always_on_tokens_used"] == 76


class TestAddAlwaysOnTokens:
    """The new --add-always-on-tokens flag increments used + decrements
    budget, clamped at 0."""

    def test_add_always_on_tokens_decrements_budget(self, tmp_path) -> None:
        sid = "ao-update-1"
        _write_legacy(str(tmp_path), sid, _legacy_cache())

        r = _run_subprocess(
            str(tmp_path), "update", sid, "--add-always-on-tokens", "100"
        )
        assert r.returncode == 0, r.stderr

        read = _run_subprocess(str(tmp_path), "read", sid)
        cache = json.loads(read.stdout)
        assert cache["always_on_tokens_used"] == 100
        assert cache["always_on_budget"] == DEFAULT_CAP - 100

    def test_add_always_on_tokens_accumulates_across_calls(
        self, tmp_path
    ) -> None:
        sid = "ao-update-2"
        _write_legacy(str(tmp_path), sid, _legacy_cache())

        for n in (50, 75, 25):
            r = _run_subprocess(
                str(tmp_path), "update", sid, "--add-always-on-tokens", str(n)
            )
            assert r.returncode == 0, r.stderr

        read = _run_subprocess(str(tmp_path), "read", sid)
        cache = json.loads(read.stdout)
        assert cache["always_on_tokens_used"] == 150
        assert cache["always_on_budget"] == DEFAULT_CAP - 150

    def test_add_always_on_tokens_clamps_budget_at_zero(
        self, tmp_path
    ) -> None:
        """Over-spending must clamp the remaining budget at 0 rather
        than going negative; tokens_used keeps incrementing for
        observability."""
        sid = "ao-update-3"
        _write_legacy(str(tmp_path), sid, _legacy_cache())

        r = _run_subprocess(
            str(tmp_path),
            "update",
            sid,
            "--add-always-on-tokens",
            str(DEFAULT_CAP + 500),
        )
        assert r.returncode == 0, r.stderr

        read = _run_subprocess(str(tmp_path), "read", sid)
        cache = json.loads(read.stdout)
        assert cache["always_on_budget"] == 0
        assert cache["always_on_tokens_used"] == DEFAULT_CAP + 500
