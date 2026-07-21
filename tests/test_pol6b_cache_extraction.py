"""POL-6b/6b-2: cache layer -> writ/session/cache.py.

6b extracted the cache I/O; 6b-2 made it resolve WRIT_CACHE_DIR at call time (no cache_dir
parameter, no module global driving I/O). This module covers the cache CONTENT logic
(round-trip, default shape, legacy command_log migration) and the config-constant move; the
call-time/env contract and source-shape live in test_pol6b2_cache_dir_env.py.

Per TEST-TDD-001: skeletons approved before implementation.
"""

from __future__ import annotations

import importlib
import importlib.util
import json
import os
import sys

import pytest

SKILL_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
CACHE_PATH = os.path.join(SKILL_ROOT, "writ", "session", "cache.py")
CONFIG_PATH = os.path.join(SKILL_ROOT, "writ", "session", "config.py")


def _load_cache_module():
    if SKILL_ROOT not in sys.path:
        sys.path.insert(0, SKILL_ROOT)
    return importlib.import_module("writ.session.cache")


class TestCacheModuleExists:
    def test_cache_file_exists(self):
        assert os.path.isfile(CACHE_PATH)

    def test_imports_as_package(self):
        assert _load_cache_module() is not None


class TestCacheContentLogic:
    """The cache default shape, round-trip, and legacy-log migration (dir via WRIT_CACHE_DIR)."""

    def test_write_then_read_roundtrip(self, tmp_path, monkeypatch):
        monkeypatch.setenv("WRIT_CACHE_DIR", str(tmp_path))
        cache = _load_cache_module()
        data = cache._read_cache("rt")
        data["mode"] = "work"
        data["loaded_rule_ids"] = ["FOO-001"]
        cache._write_cache("rt", data)
        again = cache._read_cache("rt")
        assert again["mode"] == "work"
        assert again["loaded_rule_ids"] == ["FOO-001"]

    def test_read_missing_returns_default(self, tmp_path, monkeypatch):
        monkeypatch.setenv("WRIT_CACHE_DIR", str(tmp_path))
        cache = _load_cache_module()
        d = cache._read_cache("nope")
        assert d["mode"] is None
        assert d["loaded_rule_ids"] == []

    def test_migrate_command_log_folds_into_citation_log(self, tmp_path, monkeypatch):
        """A legacy command_log row becomes a command-type citation on read."""
        monkeypatch.setenv("WRIT_CACHE_DIR", str(tmp_path))
        cache = _load_cache_module()
        path = cache._cache_path("legacy")
        with open(path, "w") as f:
            json.dump({"command_log": [{"command": "ls", "output_excerpt": "out", "exit_code": 0, "ts": "t"}]}, f)
        d = cache._read_cache("legacy")
        assert "command_log" not in d
        assert any(c.get("artifact_type") == "command" and c.get("ref") == "ls" for c in d["citation_log"])


class TestSourceShape:
    def test_cache_defines_default_dict(self):
        with open(CACHE_PATH) as f:
            src = f.read()
        # the big _read_cache default dict (a unique key) lives in cache.py
        assert '"always_on_budget": DEFAULT_ALWAYS_ON_CAP' in src

    def test_config_defines_citation_log_max(self):
        with open(CONFIG_PATH) as f:
            src = f.read()
        assert "_CITATION_LOG_MAX" in src, "the citation-bound constant must live in config.py"
