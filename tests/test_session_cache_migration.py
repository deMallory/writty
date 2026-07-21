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
import time
import uuid

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


# ===========================================================================
# Phase 1f: parent_session_id + agent_type fields + merge helpers
# Capabilities from plan.md Phase 1f / capabilities.md
# ===========================================================================

# ---------------------------------------------------------------------------
# cmd_update --parent-session-id and --agent-type handlers
# Capabilities:
#   [1f-flag-1] cmd_update --parent-session-id <id> writes cache["parent_session_id"]
#   [1f-flag-2] cmd_update --agent-type <t> writes cache["agent_type"]
# ---------------------------------------------------------------------------

class TestParentSessionIdAndAgentTypeFlags:
    """Caps [1f-flag-1], [1f-flag-2].

    --parent-session-id and --agent-type must be registered in _UPDATE_HANDLERS
    and must write the corresponding cache fields when invoked via cmd_update.

    RED: both handlers do not yet exist in budget_tracking._UPDATE_HANDLERS
    (KeyError on lookup) or they are not forwarded by the dispatcher.
    """

    def test_parent_session_id_handler_registered(self) -> None:
        # [1f-flag-1]: --parent-session-id must be a key in _UPDATE_HANDLERS.
        # RED: key absent from _UPDATE_HANDLERS (KeyError / assertion failure).
        from writ.session.budget_tracking import _UPDATE_HANDLERS

        assert "--parent-session-id" in _UPDATE_HANDLERS, (
            "--parent-session-id must be registered in _UPDATE_HANDLERS"
        )

    def test_agent_type_handler_registered(self) -> None:
        # [1f-flag-2]: --agent-type must be a key in _UPDATE_HANDLERS.
        # RED: key absent from _UPDATE_HANDLERS (KeyError / assertion failure).
        from writ.session.budget_tracking import _UPDATE_HANDLERS

        assert "--agent-type" in _UPDATE_HANDLERS, (
            "--agent-type must be registered in _UPDATE_HANDLERS"
        )

    def test_cmd_update_parent_session_id_writes_cache(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # [1f-flag-1]: calling cmd_update with --parent-session-id sets
        # cache["parent_session_id"] to the given value.
        # RED: handler absent (KeyError in dispatcher) -> cmd_update returns
        # without writing the key -> cache["parent_session_id"] == "" or absent.
        monkeypatch.setenv("WRIT_CACHE_DIR", str(tmp_path))
        sid = f"1f-psid-{uuid.uuid4().hex[:8]}"

        result = _run_subprocess(
            str(tmp_path), "update", sid,
            "--parent-session-id", "parent-session-abc",
        )
        assert result.returncode == 0, (
            f"cmd_update --parent-session-id must exit 0; stderr={result.stderr}"
        )

        read = _run_subprocess(str(tmp_path), "read", sid)
        cache = json.loads(read.stdout)
        assert cache.get("parent_session_id") == "parent-session-abc", (
            f"cache['parent_session_id'] must be 'parent-session-abc' after "
            f"--parent-session-id; got {cache.get('parent_session_id')!r}"
        )

    def test_cmd_update_agent_type_writes_cache(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # [1f-flag-2]: calling cmd_update with --agent-type sets
        # cache["agent_type"] to the given value.
        # RED: handler absent -> key missing or empty.
        monkeypatch.setenv("WRIT_CACHE_DIR", str(tmp_path))
        sid = f"1f-atype-{uuid.uuid4().hex[:8]}"

        result = _run_subprocess(
            str(tmp_path), "update", sid,
            "--agent-type", "test-writer",
        )
        assert result.returncode == 0, (
            f"cmd_update --agent-type must exit 0; stderr={result.stderr}"
        )

        read = _run_subprocess(str(tmp_path), "read", sid)
        cache = json.loads(read.stdout)
        assert cache.get("agent_type") == "test-writer", (
            f"cache['agent_type'] must be 'test-writer' after --agent-type; "
            f"got {cache.get('agent_type')!r}"
        )

    def test_cmd_update_combined_parent_session_id_and_agent_type(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Both flags in one call; the dispatcher must keep parsing after each.
        # RED: either handler absent or wrong arity causes the dispatcher to skip
        # the second flag.
        monkeypatch.setenv("WRIT_CACHE_DIR", str(tmp_path))
        sid = f"1f-combined-{uuid.uuid4().hex[:8]}"

        result = _run_subprocess(
            str(tmp_path), "update", sid,
            "--parent-session-id", "session-xyz",
            "--agent-type", "implementer",
        )
        assert result.returncode == 0, (
            f"combined --parent-session-id + --agent-type must exit 0; "
            f"stderr={result.stderr}"
        )

        read = _run_subprocess(str(tmp_path), "read", sid)
        cache = json.loads(read.stdout)
        assert cache.get("parent_session_id") == "session-xyz", (
            f"parent_session_id must be 'session-xyz'; got {cache.get('parent_session_id')!r}"
        )
        assert cache.get("agent_type") == "implementer", (
            f"agent_type must be 'implementer'; got {cache.get('agent_type')!r}"
        )


# ---------------------------------------------------------------------------
# Fresh cache defaults + legacy migration for parent_session_id / agent_type
# Capabilities:
#   [1f-default-1] a fresh (file-absent) cache carries parent_session_id == "" and agent_type == ""
#   [1f-default-2] a legacy cache lacking the keys gains both defaults on load
#   [1f-default-3] a legacy cache that already carries parent_session_id or agent_type is NOT clobbered
# ---------------------------------------------------------------------------

class TestParentSessionIdAgentTypeDefaults:
    """Caps [1f-default-1], [1f-default-2], [1f-default-3].

    RED: parent_session_id and agent_type are not yet in the _read_cache default
    dict or setdefault block (key absent from fresh/migrated cache).
    """

    def test_fresh_cache_has_parent_session_id_empty(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # [1f-default-1]: a freshly created session (no file on disk) must carry
        # parent_session_id == "".
        # RED: key absent from the default dict in _read_cache (KeyError / missing key).
        monkeypatch.setenv("WRIT_CACHE_DIR", str(tmp_path))
        from writ.session.cache import _read_cache

        sid = f"1f-fresh-psid-{uuid.uuid4().hex[:8]}"
        data = _read_cache(sid)
        assert "parent_session_id" in data, (
            "fresh session cache must contain 'parent_session_id'"
        )
        assert data["parent_session_id"] == "", (
            f"fresh cache 'parent_session_id' must default to ''; "
            f"got {data['parent_session_id']!r}"
        )

    def test_fresh_cache_has_agent_type_empty(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # [1f-default-1]: a freshly created session must carry agent_type == "".
        # RED: key absent from the default dict in _read_cache.
        monkeypatch.setenv("WRIT_CACHE_DIR", str(tmp_path))
        from writ.session.cache import _read_cache

        sid = f"1f-fresh-atype-{uuid.uuid4().hex[:8]}"
        data = _read_cache(sid)
        assert "agent_type" in data, (
            "fresh session cache must contain 'agent_type'"
        )
        assert data["agent_type"] == "", (
            f"fresh cache 'agent_type' must default to ''; got {data['agent_type']!r}"
        )

    def test_legacy_cache_gains_parent_session_id_on_load(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # [1f-default-2]: an existing cache file without parent_session_id gets it
        # added as "" via setdefault on _read_cache.
        # RED: setdefault for parent_session_id not yet in _read_cache (key absent).
        monkeypatch.setenv("WRIT_CACHE_DIR", str(tmp_path))
        sid = f"1f-legacy-psid-{uuid.uuid4().hex[:8]}"
        legacy = {"loaded_rule_ids": [], "mode": None, "is_subagent": False}
        cache_path = tmp_path / f"writ-session-{sid}.json"
        cache_path.write_text(json.dumps(legacy))

        from writ.session.cache import _read_cache
        data = _read_cache(sid)
        assert "parent_session_id" in data, (
            "legacy cache must gain 'parent_session_id' via setdefault on load"
        )
        assert data["parent_session_id"] == "", (
            f"migrated 'parent_session_id' must be ''; got {data['parent_session_id']!r}"
        )

    def test_legacy_cache_gains_agent_type_on_load(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # [1f-default-2]: an existing cache file without agent_type gets it added
        # as "" via setdefault on _read_cache.
        # RED: setdefault for agent_type not yet in _read_cache.
        monkeypatch.setenv("WRIT_CACHE_DIR", str(tmp_path))
        sid = f"1f-legacy-atype-{uuid.uuid4().hex[:8]}"
        legacy = {"loaded_rule_ids": [], "mode": None, "is_subagent": False}
        cache_path = tmp_path / f"writ-session-{sid}.json"
        cache_path.write_text(json.dumps(legacy))

        from writ.session.cache import _read_cache
        data = _read_cache(sid)
        assert "agent_type" in data, (
            "legacy cache must gain 'agent_type' via setdefault on load"
        )
        assert data["agent_type"] == "", (
            f"migrated 'agent_type' must be ''; got {data['agent_type']!r}"
        )

    def test_existing_parent_session_id_not_clobbered_on_load(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # [1f-default-3]: a cache file that already has a non-empty parent_session_id
        # must NOT have it overwritten by setdefault (setdefault only fills absent keys).
        # RED: setdefault not yet added (so the field is absent -> KeyError is a
        # different failure, but the no-clobber contract is the real invariant here).
        monkeypatch.setenv("WRIT_CACHE_DIR", str(tmp_path))
        sid = f"1f-noclobber-psid-{uuid.uuid4().hex[:8]}"
        existing = {
            "loaded_rule_ids": [],
            "mode": None,
            "is_subagent": False,
            "parent_session_id": "pre-existing-parent-123",
        }
        cache_path = tmp_path / f"writ-session-{sid}.json"
        cache_path.write_text(json.dumps(existing))

        from writ.session.cache import _read_cache
        data = _read_cache(sid)
        assert data.get("parent_session_id") == "pre-existing-parent-123", (
            "_read_cache must NOT clobber an existing non-empty parent_session_id; "
            f"expected 'pre-existing-parent-123', got {data.get('parent_session_id')!r}"
        )

    def test_existing_agent_type_not_clobbered_on_load(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # [1f-default-3]: a cache file that already has a non-empty agent_type must
        # NOT have it overwritten on load.
        # RED: setdefault not yet added (absent key is distinct from clobber, but
        # the contract covers both).
        monkeypatch.setenv("WRIT_CACHE_DIR", str(tmp_path))
        sid = f"1f-noclobber-atype-{uuid.uuid4().hex[:8]}"
        existing = {
            "loaded_rule_ids": [],
            "mode": None,
            "is_subagent": False,
            "agent_type": "reviewer",
        }
        cache_path = tmp_path / f"writ-session-{sid}.json"
        cache_path.write_text(json.dumps(existing))

        from writ.session.cache import _read_cache
        data = _read_cache(sid)
        assert data.get("agent_type") == "reviewer", (
            "_read_cache must NOT clobber an existing non-empty agent_type; "
            f"expected 'reviewer', got {data.get('agent_type')!r}"
        )


# ---------------------------------------------------------------------------
# _merge_queried_by_file pure helper
# Capabilities:
#   [1f-merge-1] _merge_queried_by_file unions disjoint path keys
#   [1f-merge-2] _merge_queried_by_file dedups and sorts rule ids for overlapping key
#   [1f-merge-3] _merge_queried_by_file returns non-empty side when other is empty
#   [1f-merge-4] _merge_queried_by_file does not mutate its inputs
# ---------------------------------------------------------------------------

class TestMergeQueriedByFile:
    """Caps [1f-merge-1] through [1f-merge-4].

    _merge_queried_by_file is a pure helper in writ.session.cache.
    RED: function does not yet exist (ImportError / AttributeError).
    """

    def _merge(self, a: dict, b: dict) -> dict:
        from writ.session.cache import _merge_queried_by_file
        return _merge_queried_by_file(a, b)

    def test_disjoint_keys_union(self) -> None:
        # [1f-merge-1]: non-overlapping path keys in a and b appear together in result.
        # RED: ImportError, _merge_queried_by_file does not exist yet.
        result = self._merge(
            {"a.py": ["R1"]},
            {"b.py": ["R2"]},
        )
        assert set(result.keys()) == {"a.py", "b.py"}, (
            f"disjoint keys must all appear in result; got {set(result.keys())}"
        )
        assert result["a.py"] == ["R1"]
        assert result["b.py"] == ["R2"]

    def test_overlapping_key_deduped_and_sorted(self) -> None:
        # [1f-merge-2]: the same path key in both maps -> result value is
        # sorted(set(a_ids) | set(b_ids)), no duplicates.
        # RED: ImportError.
        result = self._merge(
            {"a.py": ["R2", "R1"]},
            {"a.py": ["R1", "R3"]},
        )
        assert result["a.py"] == ["R1", "R2", "R3"], (
            f"overlapping key must produce sorted deduped union; got {result['a.py']!r}"
        )

    def test_empty_a_returns_b(self) -> None:
        # [1f-merge-3]: empty left side -> result equals right side (as a NEW dict).
        # RED: ImportError.
        b = {"a.py": ["R1"]}
        result = self._merge({}, b)
        assert result == {"a.py": ["R1"]}, (
            f"empty a must produce result equal to b; got {result!r}"
        )

    def test_empty_b_returns_a(self) -> None:
        # [1f-merge-3]: empty right side -> result equals left side (as a NEW dict).
        # RED: ImportError.
        a = {"a.py": ["R1"]}
        result = self._merge(a, {})
        assert result == {"a.py": ["R1"]}, (
            f"empty b must produce result equal to a; got {result!r}"
        )

    def test_inputs_not_mutated(self) -> None:
        # [1f-merge-4]: neither a nor b is modified by the merge.
        # RED: ImportError, function absent.
        a = {"a.py": ["R1"]}
        b = {"a.py": ["R2"], "b.py": ["R3"]}
        a_copy = {k: list(v) for k, v in a.items()}
        b_copy = {k: list(v) for k, v in b.items()}

        self._merge(a, b)

        assert a == a_copy, (
            f"a must not be mutated; before={a_copy!r}, after={a!r}"
        )
        assert b == b_copy, (
            f"b must not be mutated; before={b_copy!r}, after={b!r}"
        )

    def test_both_empty_returns_empty(self) -> None:
        # Edge case: merging two empty dicts -> empty dict.
        # RED: ImportError.
        result = self._merge({}, {})
        assert result == {}, f"merging two empty dicts must yield {{}}; got {result!r}"


# ---------------------------------------------------------------------------
# _collect_subagent_queried_rules helper
# Capabilities:
#   [1f-collect-1] unions two matching sub-agent caches
#   [1f-collect-2] excludes a cache with a mismatched parent_session_id
#   [1f-collect-3] excludes a cache with is_subagent falsey
#   [1f-collect-4] returns {} when no cache matches
#   [1f-collect-5] skips a corrupt-JSON child cache without raising
# ---------------------------------------------------------------------------

class TestCollectSubagentQueriedRules:
    """Caps [1f-collect-1] through [1f-collect-5].

    Uses monkeypatch on WRIT_CACHE_DIR (tmp_path) so the glob sees only
    the fixture files written in each test.

    RED: _collect_subagent_queried_rules does not yet exist in
    writ.session.cache (ImportError / AttributeError).
    """

    def _write_child_cache(
        self, cache_dir: Path, agent_id: str, payload: dict
    ) -> None:
        """Write a child session cache file under writ-session-<agent_id>.json."""
        path = cache_dir / f"writ-session-{agent_id}.json"
        path.write_text(json.dumps(payload))

    def _collect(self, parent_id: str, monkeypatch: pytest.MonkeyPatch, cache_dir: Path) -> dict:
        monkeypatch.setenv("WRIT_CACHE_DIR", str(cache_dir))
        from writ.session.cache import _collect_subagent_queried_rules
        return _collect_subagent_queried_rules(parent_id)

    def test_two_matching_child_caches_union(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # [1f-collect-1]: two child caches with the correct parent_session_id and
        # is_subagent=True; their queried_rules_by_file entries must be unioned.
        # RED: ImportError, function does not exist.
        parent_id = "parent-session-collect-1"
        self._write_child_cache(tmp_path, "child-a", {
            "parent_session_id": parent_id,
            "is_subagent": True,
            "queried_rules_by_file": {"a.py": ["R1", "R2"]},
        })
        self._write_child_cache(tmp_path, "child-b", {
            "parent_session_id": parent_id,
            "is_subagent": True,
            "queried_rules_by_file": {"b.py": ["R3"]},
        })

        result = self._collect(parent_id, monkeypatch, tmp_path)

        assert "a.py" in result, f"a.py must be in union; got {set(result.keys())}"
        assert "b.py" in result, f"b.py must be in union; got {set(result.keys())}"
        assert set(result["a.py"]) == {"R1", "R2"}, (
            f"a.py ids must be {{R1, R2}}; got {result['a.py']}"
        )
        assert result["b.py"] == ["R3"], (
            f"b.py ids must be [R3]; got {result['b.py']}"
        )

    def test_mismatched_parent_session_id_excluded(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # [1f-collect-2]: a cache whose parent_session_id does not match is skipped.
        # RED: ImportError.
        parent_id = "parent-session-collect-2"
        self._write_child_cache(tmp_path, "child-match", {
            "parent_session_id": parent_id,
            "is_subagent": True,
            "queried_rules_by_file": {"a.py": ["R1"]},
        })
        self._write_child_cache(tmp_path, "child-mismatch", {
            "parent_session_id": "some-other-parent",
            "is_subagent": True,
            "queried_rules_by_file": {"b.py": ["R2"]},
        })

        result = self._collect(parent_id, monkeypatch, tmp_path)

        assert "a.py" in result, "matching child must contribute a.py"
        assert "b.py" not in result, (
            "mismatched parent_session_id child must be excluded; "
            f"got keys {set(result.keys())}"
        )

    def test_is_subagent_false_excluded(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # [1f-collect-3]: a cache with is_subagent=False is excluded even if
        # parent_session_id matches.
        # RED: ImportError.
        parent_id = "parent-session-collect-3"
        self._write_child_cache(tmp_path, "child-notsubagent", {
            "parent_session_id": parent_id,
            "is_subagent": False,
            "queried_rules_by_file": {"a.py": ["R1"]},
        })

        result = self._collect(parent_id, monkeypatch, tmp_path)

        assert result == {}, (
            f"cache with is_subagent=False must be excluded; got {result!r}"
        )

    def test_no_match_returns_empty(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # [1f-collect-4]: when no cache file matches, return {}.
        # RED: ImportError.
        result = self._collect("parent-with-no-children", monkeypatch, tmp_path)
        assert result == {}, (
            f"no-match must return {{}}; got {result!r}"
        )

    def test_corrupt_json_file_skipped_not_raised(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # [1f-collect-5]: a corrupt (unparseable) cache file must be skipped
        # without raising; the rest of the caches are still processed.
        # RED: ImportError.
        parent_id = "parent-session-collect-5"
        # Write a corrupt file with the right naming pattern.
        corrupt_path = tmp_path / "writ-session-child-corrupt.json"
        corrupt_path.write_text("{this is not valid json")
        # Write one good matching child.
        self._write_child_cache(tmp_path, "child-good", {
            "parent_session_id": parent_id,
            "is_subagent": True,
            "queried_rules_by_file": {"a.py": ["R1"]},
        })

        # Must not raise; the good child's contribution must still appear.
        result = self._collect(parent_id, monkeypatch, tmp_path)

        assert "a.py" in result, (
            "good child must still contribute despite corrupt sibling"
        )

    def test_empty_parent_session_id_returns_empty(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Edge case: empty parent_session_id -> fast-path return {}.
        # RED: ImportError.
        result = self._collect("", monkeypatch, tmp_path)
        assert result == {}, (
            "empty parent_session_id must return {} immediately; got {result!r}"
        )


# ===========================================================================
# Path + recency merge: _collect_subagent_queried_rules signature change
# Capabilities from plan.md "robust sub-agent queried-rule merge" section
#
#   [path-recency-1] non-matching parent sub-agent contributes when committed_keys
#                    includes its key and cache mtime >= since_ts
#   [path-recency-2] same sub-agent EXCLUDED when since_ts is set above its mtime
#   [path-recency-3] only committed_keys are attached; uncovered paths are absent
#   [path-recency-4] parent fast-path bypasses recency (matching parent contributes
#                    even with aged mtime and since_ts > mtime)
#   [path-recency-5] backward-compat: _collect(parent) with committed_keys omitted
#                    returns the parent-only union exactly as before (REGRESSION GUARD)
#   [path-recency-6] fail-open still holds: corrupt child skipped with new params
# ===========================================================================

class TestCollectSubagentQueriedRulesPathRecency:
    """Path + recency capabilities for the extended _collect_subagent_queried_rules.

    Every test uses _write_cache (the same atomic-rename writer production uses)
    rather than raw json.dump so fixture files go through the same serialization
    path as real caches. WRIT_CACHE_DIR is monkeypatched to tmp_path for each
    test (TEST-ISOLATE-001).

    RED reason for [path-recency-1] through [path-recency-4] and [path-recency-6]:
    the current _collect_subagent_queried_rules signature is
        _collect_subagent_queried_rules(parent_session_id: str) -> dict
    Passing committed_keys or since_ts raises TypeError immediately. The tests
    fail for that exact reason before the implementation change.

    [path-recency-5] is a REGRESSION GUARD: it calls the old one-argument form
    and must PASS both before and after the change.
    """

    def _write_child_via_cache(
        self,
        cache_dir: Path,
        agent_id: str,
        payload: dict,
        monkeypatch: pytest.MonkeyPatch,
    ) -> Path:
        """Write a child cache via _write_cache under the monkeypatched WRIT_CACHE_DIR.

        Returns the on-disk path so callers can os.utime it.
        """
        monkeypatch.setenv("WRIT_CACHE_DIR", str(cache_dir))
        from writ.session.cache import _write_cache
        _write_cache(agent_id, payload)
        return cache_dir / f"writ-session-{agent_id}.json"

    def _collect_with_keys(
        self,
        parent_id: str,
        committed_keys: set,
        since_ts: float,
        cache_dir: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> dict:
        monkeypatch.setenv("WRIT_CACHE_DIR", str(cache_dir))
        from writ.session.cache import _collect_subagent_queried_rules
        # RED: current signature is _collect(parent_session_id) so passing two
        # extra kwargs raises TypeError.
        return _collect_subagent_queried_rules(
            parent_id,
            committed_keys=committed_keys,
            since_ts=since_ts,
        )

    def test_path_recency_1_non_matching_parent_contributes_when_key_and_recent(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """[path-recency-1]: a sub-agent whose parent_session_id does NOT match the
        queried parent contributes its queried rules when:
          - committed_keys includes its key, AND
          - its cache mtime is at or after since_ts.

        Right-reason RED: current _collect takes only parent_session_id ->
        TypeError on the extra keyword args (committed_keys, since_ts).
        """
        child_id = f"pr1-child-{uuid.uuid4().hex[:8]}"
        key = "writ/session/cache.py"
        rule_ids = ["ENF-PR1-001", "PERF-PR1-002"]

        # Write child with a DIFFERENT parent_session_id than we will query with.
        cache_path = self._write_child_via_cache(
            tmp_path,
            child_id,
            {
                "parent_session_id": "some-other-session-pr1",
                "is_subagent": True,
                "queried_rules_by_file": {key: rule_ids},
            },
            monkeypatch,
        )
        # since_ts set well before the file was written (mtime >= since_ts is True).
        since_ts = os.path.getmtime(str(cache_path)) - 10.0

        result = self._collect_with_keys(
            "querying-parent-pr1",
            committed_keys={key},
            since_ts=since_ts,
            cache_dir=tmp_path,
            monkeypatch=monkeypatch,
        )

        assert key in result, (
            f"[path-recency-1] non-matching-parent sub-agent must contribute "
            f"when committed_keys includes its key and mtime >= since_ts; "
            f"got keys={set(result.keys())!r}"
        )
        assert set(result[key]) == set(rule_ids), (
            f"[path-recency-1] contributed ids must match the child's rule_ids; "
            f"expected={set(rule_ids)!r}, got={set(result[key])!r}"
        )

    def test_path_recency_2_excluded_when_since_ts_above_mtime(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """[path-recency-2]: the SAME sub-agent from [path-recency-1] is EXCLUDED
        when since_ts is set ABOVE its mtime (i.e., the file is too old).

        Uses os.utime to age the cache file to an old timestamp, then passes
        since_ts=time.time() to force the exclusion.

        Right-reason RED: TypeError on extra kwargs.
        """
        child_id = f"pr2-child-{uuid.uuid4().hex[:8]}"
        key = "writ/session/cache.py"

        cache_path = self._write_child_via_cache(
            tmp_path,
            child_id,
            {
                "parent_session_id": "some-other-session-pr2",
                "is_subagent": True,
                "queried_rules_by_file": {key: ["ENF-PR2-001"]},
            },
            monkeypatch,
        )
        # Age the file: set mtime to 1000 seconds in the past.
        old_ts = time.time() - 1000.0
        os.utime(str(cache_path), (old_ts, old_ts))

        # since_ts is NOW, which is after the aged mtime -> cache should be excluded.
        since_ts = time.time()

        result = self._collect_with_keys(
            "querying-parent-pr2",
            committed_keys={key},
            since_ts=since_ts,
            cache_dir=tmp_path,
            monkeypatch=monkeypatch,
        )

        assert key not in result, (
            f"[path-recency-2] sub-agent with aged mtime must be EXCLUDED when "
            f"since_ts is above its mtime; got result={result!r}"
        )

    def test_path_recency_3_only_committed_keys_attached(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """[path-recency-3]: a sub-agent holding keys A and B, called with
        committed_keys={A}, contributes ONLY key A; key B is absent from the result.

        Right-reason RED: TypeError on extra kwargs.
        """
        child_id = f"pr3-child-{uuid.uuid4().hex[:8]}"
        key_a = "writ/session/cache.py"
        key_b = "writ/session/budget_tracking.py"

        cache_path = self._write_child_via_cache(
            tmp_path,
            child_id,
            {
                "parent_session_id": "some-other-session-pr3",
                "is_subagent": True,
                "queried_rules_by_file": {
                    key_a: ["ENF-PR3-A"],
                    key_b: ["ENF-PR3-B"],
                },
            },
            monkeypatch,
        )
        since_ts = os.path.getmtime(str(cache_path)) - 10.0

        result = self._collect_with_keys(
            "querying-parent-pr3",
            committed_keys={key_a},
            since_ts=since_ts,
            cache_dir=tmp_path,
            monkeypatch=monkeypatch,
        )

        assert key_a in result, (
            f"[path-recency-3] committed key_a must be in result; "
            f"got keys={set(result.keys())!r}"
        )
        assert key_b not in result, (
            f"[path-recency-3] non-committed key_b must NOT be attached even "
            f"though the child cache holds it; got result={result!r}"
        )

    def test_path_recency_4_parent_fast_path_bypasses_recency(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """[path-recency-4]: a sub-agent whose parent_session_id MATCHES the queried
        parent contributes even when:
          - its mtime is aged (well below since_ts), AND
          - committed_keys is given, AND
          - since_ts is set to time.time() (so recency would normally exclude it).

        The parent fast-path (parent_match=True) must bypass the recency check.

        Right-reason RED: TypeError on extra kwargs.
        """
        parent_id = "matching-parent-pr4"
        child_id = f"pr4-child-{uuid.uuid4().hex[:8]}"
        key = "writ/session/cache.py"

        cache_path = self._write_child_via_cache(
            tmp_path,
            child_id,
            {
                "parent_session_id": parent_id,
                "is_subagent": True,
                "queried_rules_by_file": {key: ["ENF-PR4-001"]},
            },
            monkeypatch,
        )
        # Age the file to 1000 seconds in the past.
        old_ts = time.time() - 1000.0
        os.utime(str(cache_path), (old_ts, old_ts))

        # since_ts is NOW -> recency check would exclude if it ran.
        since_ts = time.time()

        result = self._collect_with_keys(
            parent_id,
            committed_keys={key},
            since_ts=since_ts,
            cache_dir=tmp_path,
            monkeypatch=monkeypatch,
        )

        assert key in result, (
            f"[path-recency-4] sub-agent with MATCHING parent must contribute "
            f"even with aged mtime + since_ts=now (parent fast-path bypasses recency); "
            f"got keys={set(result.keys())!r}"
        )
        assert "ENF-PR4-001" in result.get(key, []), (
            f"[path-recency-4] rule id must be present; got result[key]={result.get(key)!r}"
        )

    def test_path_recency_7_parent_match_attaches_only_committed_keys(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """[path-recency-7]: a parent-matched sub-agent that wrote BOTH a committed
        file and a non-committed file contributes ONLY the committed file's rules.
        The contrib filter narrows even the parent fast-path to committed_keys, so a
        FileChange is never annotated with rules for files outside the commit.
        """
        parent_id = "matching-parent-pr7"
        child_id = f"pr7-child-{uuid.uuid4().hex[:8]}"
        committed = "writ/session/cache.py"
        other = "writ/session/other.py"

        self._write_child_via_cache(
            tmp_path,
            child_id,
            {
                "parent_session_id": parent_id,
                "is_subagent": True,
                "queried_rules_by_file": {
                    committed: ["ENF-COMMITTED-001"],
                    other: ["ENF-OTHER-001"],
                },
            },
            monkeypatch,
        )

        result = self._collect_with_keys(
            parent_id,
            committed_keys={committed},
            since_ts=0.0,
            cache_dir=tmp_path,
            monkeypatch=monkeypatch,
        )

        assert result.get(committed) == ["ENF-COMMITTED-001"], (
            f"[path-recency-7] committed key's rules must be attached; "
            f"got {result.get(committed)!r}"
        )
        assert other not in result, (
            f"[path-recency-7] non-committed key must NOT be attached even on a "
            f"parent match; got keys={set(result.keys())!r}"
        )

    def test_path_recency_5_backward_compat_parent_only_union(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """[path-recency-5] REGRESSION GUARD: calling _collect_subagent_queried_rules
        with only parent_session_id (committed_keys and since_ts omitted) returns the
        parent-only union exactly as before.

        This test PASSES now (with the old single-arg signature) and must continue to
        PASS after the signature is extended. If it starts failing after the change it
        indicates the default-arg backward-compat path is broken.
        """
        parent_id = f"compat-parent-pr5-{uuid.uuid4().hex[:8]}"
        child_id_a = f"pr5-child-a-{uuid.uuid4().hex[:8]}"
        child_id_b = f"pr5-child-b-{uuid.uuid4().hex[:8]}"
        unrelated_id = f"pr5-unrelated-{uuid.uuid4().hex[:8]}"

        monkeypatch.setenv("WRIT_CACHE_DIR", str(tmp_path))
        from writ.session.cache import _write_cache, _collect_subagent_queried_rules

        _write_cache(child_id_a, {
            "parent_session_id": parent_id,
            "is_subagent": True,
            "queried_rules_by_file": {"a.py": ["R-COMPAT-1"]},
        })
        _write_cache(child_id_b, {
            "parent_session_id": parent_id,
            "is_subagent": True,
            "queried_rules_by_file": {"b.py": ["R-COMPAT-2"]},
        })
        _write_cache(unrelated_id, {
            "parent_session_id": "completely-different-parent",
            "is_subagent": True,
            "queried_rules_by_file": {"c.py": ["R-UNRELATED"]},
        })

        # Old call form: one positional arg only.
        result = _collect_subagent_queried_rules(parent_id)

        assert "a.py" in result, (
            "[path-recency-5] backward-compat: a.py from child-a must appear"
        )
        assert "b.py" in result, (
            "[path-recency-5] backward-compat: b.py from child-b must appear"
        )
        assert "c.py" not in result, (
            "[path-recency-5] backward-compat: c.py from unrelated child must NOT appear"
        )
        assert "R-COMPAT-1" in result.get("a.py", []), (
            "[path-recency-5] R-COMPAT-1 must be in result['a.py']"
        )
        assert "R-COMPAT-2" in result.get("b.py", []), (
            "[path-recency-5] R-COMPAT-2 must be in result['b.py']"
        )

    def test_path_recency_6_fail_open_corrupt_child_skipped_with_new_params(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """[path-recency-6]: fail-open still holds with the extended signature.

        A corrupt child JSON file is skipped without raising when committed_keys
        and since_ts are provided. The good sibling still contributes.

        Right-reason RED: TypeError on extra kwargs before the implementation change.
        """
        key = "writ/session/cache.py"
        parent_id = "fail-open-pr6-parent"
        good_child_id = f"pr6-good-{uuid.uuid4().hex[:8]}"

        # Write a corrupt file with the writ-session naming pattern.
        corrupt_path = tmp_path / f"writ-session-pr6-corrupt-{uuid.uuid4().hex[:8]}.json"
        corrupt_path.write_text("{not valid json at all }")

        # Write a good matching child (matching via key + recency, not parent_session_id).
        good_cache_path = self._write_child_via_cache(
            tmp_path,
            good_child_id,
            {
                "parent_session_id": "some-other-session-pr6",
                "is_subagent": True,
                "queried_rules_by_file": {key: ["ENF-PR6-001"]},
            },
            monkeypatch,
        )
        since_ts = os.path.getmtime(str(good_cache_path)) - 10.0

        # Must not raise; good child must still contribute.
        result = self._collect_with_keys(
            parent_id,
            committed_keys={key},
            since_ts=since_ts,
            cache_dir=tmp_path,
            monkeypatch=monkeypatch,
        )

        assert key in result, (
            "[path-recency-6] good child must still contribute despite corrupt sibling; "
            f"got keys={set(result.keys())!r}"
        )
        assert "ENF-PR6-001" in result.get(key, []), (
            f"[path-recency-6] rule id must be present; got result[key]={result.get(key)!r}"
        )
