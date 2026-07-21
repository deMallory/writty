"""PIECE 3: _collect_subagent_queried_rules admits a recent rotated NON-subagent
(main) cache via the existing recency + path-overlap fallback.

Contract (plan.md):
  - The `is_subagent` guard at cache.py:209 currently `continue`s on ANY non-subagent
    cache. It is loosened: a non-subagent cache is no longer skipped outright -- it
    becomes eligible ONLY through the path+recency fallback (mtime >= since_ts AND
    queried_rules_by_file keys intersect committed_keys).
  - The `parent_session_id` fast path stays is_subagent-ONLY and unchanged: a
    non-subagent cache can only be admitted via path_match, never parent_match.
  - A stale main cache (mtime < since_ts) is still excluded.
  - A non-overlapping main cache (no committed_keys intersection) is still excluded.
  - Return shape is unchanged: {} when nothing matches, else the unioned
    queried_rules_by_file dict restricted to committed_keys.

This relaxation does not exist yet -- cache.py:209's `data.get("is_subagent")` guard
still `continue`s unconditionally on any non-subagent cache. This file is RED until
PIECE 3 lands. Per TEST-TDD-001: skeletons approved before implementation.

Hermetic: WRIT_CACHE_DIR -> tmp_path (matches test_pol6b2_cache_dir_env.py); mtimes are
set explicitly via os.utime so recency comparisons are deterministic, never real-clock-
dependent.
"""

from __future__ import annotations

import os

import pytest

from writ.session import cache


@pytest.fixture(autouse=True)
def _isolated_cache_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("WRIT_CACHE_DIR", str(tmp_path))
    yield


def _seed_main_cache(session_id: str, *, queried_rules_by_file: dict, mtime: float) -> None:
    """Write a NON-subagent (main-session) cache with an explicit mtime."""
    data = cache._read_cache(session_id)
    data["is_subagent"] = False
    data["queried_rules_by_file"] = queried_rules_by_file
    cache._write_cache(session_id, data)
    path = cache._cache_path(session_id)
    os.utime(path, (mtime, mtime))


def _seed_subagent_cache(
    session_id: str, *, parent_session_id: str, queried_rules_by_file: dict, mtime: float
) -> None:
    data = cache._read_cache(session_id)
    data["is_subagent"] = True
    data["parent_session_id"] = parent_session_id
    data["queried_rules_by_file"] = queried_rules_by_file
    cache._write_cache(session_id, data)
    path = cache._cache_path(session_id)
    os.utime(path, (mtime, mtime))


class TestRotatedMainCacheAdmitted:
    def test_recent_overlapping_main_cache_is_admitted_via_path_fallback(self):
        _seed_main_cache(
            "rotated-main-sid",
            queried_rules_by_file={"src/foo.py": ["RULE-A", "RULE-B"]},
            mtime=2000.0,
        )

        result = cache._collect_subagent_queried_rules(
            "committing-sid",
            committed_keys={"src/foo.py"},
            since_ts=1000.0,
        )

        assert result == {"src/foo.py": ["RULE-A", "RULE-B"]}

    def test_admitted_main_cache_contributes_only_committed_keys(self):
        _seed_main_cache(
            "rotated-main-sid-2",
            queried_rules_by_file={
                "src/foo.py": ["RULE-A"],
                "src/unrelated.py": ["RULE-Z"],
            },
            mtime=2000.0,
        )

        result = cache._collect_subagent_queried_rules(
            "committing-sid-2",
            committed_keys={"src/foo.py"},
            since_ts=1000.0,
        )

        assert result == {"src/foo.py": ["RULE-A"]}
        assert "src/unrelated.py" not in result

    def test_admitted_main_cache_unions_with_a_real_subagent_cache(self):
        _seed_main_cache(
            "rotated-main-sid-3",
            queried_rules_by_file={"src/foo.py": ["RULE-A"]},
            mtime=2000.0,
        )
        _seed_subagent_cache(
            "subagent-sid-3",
            parent_session_id="committing-sid-3",
            queried_rules_by_file={"src/foo.py": ["RULE-B"]},
            mtime=2000.0,
        )

        result = cache._collect_subagent_queried_rules(
            "committing-sid-3",
            committed_keys={"src/foo.py"},
            since_ts=1000.0,
        )

        assert result == {"src/foo.py": ["RULE-A", "RULE-B"]}


class TestStaleMainCacheExcluded:
    def test_main_cache_older_than_since_ts_is_excluded(self):
        _seed_main_cache(
            "stale-main-sid",
            queried_rules_by_file={"src/foo.py": ["RULE-A"]},
            mtime=500.0,  # older than since_ts
        )

        result = cache._collect_subagent_queried_rules(
            "committing-sid-4",
            committed_keys={"src/foo.py"},
            since_ts=1000.0,
        )

        assert result == {}

    def test_main_cache_exactly_at_since_ts_boundary_is_included(self):
        _seed_main_cache(
            "boundary-main-sid",
            queried_rules_by_file={"src/foo.py": ["RULE-A"]},
            mtime=1000.0,  # mtime >= since_ts is inclusive per the docstring contract
        )

        result = cache._collect_subagent_queried_rules(
            "committing-sid-5",
            committed_keys={"src/foo.py"},
            since_ts=1000.0,
        )

        assert result == {"src/foo.py": ["RULE-A"]}


class TestNonOverlappingMainCacheExcluded:
    def test_main_cache_with_no_committed_key_intersection_is_excluded(self):
        _seed_main_cache(
            "non-overlapping-main-sid",
            queried_rules_by_file={"src/other_file.py": ["RULE-A"]},
            mtime=2000.0,
        )

        result = cache._collect_subagent_queried_rules(
            "committing-sid-6",
            committed_keys={"src/foo.py"},
            since_ts=1000.0,
        )

        assert result == {}

    def test_main_cache_is_excluded_when_committed_keys_is_none(self):
        _seed_main_cache(
            "no-committed-keys-main-sid",
            queried_rules_by_file={"src/foo.py": ["RULE-A"]},
            mtime=2000.0,
        )

        result = cache._collect_subagent_queried_rules(
            "committing-sid-7",
            committed_keys=None,
            since_ts=1000.0,
        )

        assert result == {}


class TestParentSessionIdFastPathStaysSubagentOnly:
    def test_non_subagent_cache_with_matching_parent_session_id_is_not_admitted_via_fast_path(self):
        """A non-subagent cache must not be admitted through parent_match, even when
        its parent_session_id field happens to equal the committing session id -- it
        can ONLY be reached through the path+recency fallback, so a stale/non-
        overlapping non-subagent cache with a matching parent_session_id is still
        excluded."""
        data = cache._read_cache("fake-main-with-parent-id")
        data["is_subagent"] = False
        data["parent_session_id"] = "committing-sid-8"
        data["queried_rules_by_file"] = {"src/unrelated.py": ["RULE-A"]}
        cache._write_cache("fake-main-with-parent-id", data)
        path = cache._cache_path("fake-main-with-parent-id")
        os.utime(path, (500.0, 500.0))  # stale, and non-overlapping

        result = cache._collect_subagent_queried_rules(
            "committing-sid-8",
            committed_keys={"src/foo.py"},
            since_ts=1000.0,
        )

        assert result == {}

    def test_real_subagent_cache_still_admitted_via_parent_match_regardless_of_recency(self):
        """The parent_session_id fast path bypasses recency for TRUE sub-agent
        caches (is_subagent=True) -- this must remain unchanged by the PIECE 3
        relaxation."""
        _seed_subagent_cache(
            "old-subagent-sid",
            parent_session_id="committing-sid-9",
            queried_rules_by_file={"src/anything.py": ["RULE-A"]},
            mtime=1.0,  # very old, would fail any recency check
        )

        result = cache._collect_subagent_queried_rules(
            "committing-sid-9",
            committed_keys={"src/anything.py"},
            since_ts=999999.0,  # since_ts far in the future of the cache's mtime
        )

        assert result == {"src/anything.py": ["RULE-A"]}


class TestReturnShapeUnchanged:
    def test_returns_empty_dict_when_nothing_matches_at_all(self):
        result = cache._collect_subagent_queried_rules(
            "committing-sid-10", committed_keys={"src/foo.py"}, since_ts=1000.0
        )
        assert result == {}

    def test_corrupt_cache_file_is_skipped_without_raising(self):
        path = cache._cache_path("corrupt-sid")
        with open(path, "w") as f:
            f.write("{not valid json")
        os.utime(path, (2000.0, 2000.0))

        result = cache._collect_subagent_queried_rules(
            "committing-sid-11", committed_keys={"src/foo.py"}, since_ts=1000.0
        )

        assert result == {}
