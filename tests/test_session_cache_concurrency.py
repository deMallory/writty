"""Regression tests for the session-cache write race (TEST-EDGE-003).

`_write_cache` previously wrote every writer's payload to the same
deterministic temp name (`<path>.tmp`) before renaming it over the cache.
Two concurrent writers -- the FastAPI server via asyncio.to_thread and any
hook CLI invocation -- would open the same temp file; whichever renamed
first deleted it out from under the other, whose os.rename then raised
FileNotFoundError (seen in production via POST /session/{id}/context-percent).

The fix gives each writer a unique tempfile.mkstemp name in the cache
directory and promotes it with os.replace.
"""

from __future__ import annotations

import importlib.util
import json
import os
import threading
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent.parent
WRIT_SESSION_PY = f"{SKILL_DIR}/bin/lib/writ-session.py"


def _load_writ_session():
    """Load writ-session.py as a module without installing it."""
    spec = importlib.util.spec_from_file_location("writ_session_concurrency", WRIT_SESSION_PY)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class TestWriteCacheConcurrency:
    def test_parallel_writers_no_exception(self, tmp_path, monkeypatch):
        """50 threads writing the same session cache: no writer may crash."""
        monkeypatch.setenv("WRIT_CACHE_DIR", str(tmp_path))
        mod = _load_writ_session()
        session_id = "concurrency-test"
        errors: list[BaseException] = []
        barrier = threading.Barrier(10)

        def writer(i: int) -> None:
            try:
                barrier.wait(timeout=10)
                for j in range(20):
                    mod._write_cache(session_id, {"writer": i, "iteration": j})
            except BaseException as exc:  # noqa: BLE001 -- collecting for assertion
                errors.append(exc)

        threads = [threading.Thread(target=writer, args=(i,)) for i in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=30)

        assert errors == [], f"concurrent _write_cache raised: {errors!r}"

    def test_final_cache_is_valid_json(self, tmp_path, monkeypatch):
        """After parallel writes the cache is one intact writer's payload."""
        monkeypatch.setenv("WRIT_CACHE_DIR", str(tmp_path))
        mod = _load_writ_session()
        session_id = "concurrency-json-test"

        def writer(i: int) -> None:
            mod._write_cache(session_id, {"writer": i, "payload": ["x"] * 50})

        threads = [threading.Thread(target=writer, args=(i,)) for i in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=30)

        with open(mod._cache_path(session_id)) as f:
            data = json.load(f)
        assert data["payload"] == ["x"] * 50

    def test_no_orphan_temp_files(self, tmp_path, monkeypatch):
        """mkstemp temps are promoted or cleaned, never left behind."""
        monkeypatch.setenv("WRIT_CACHE_DIR", str(tmp_path))
        mod = _load_writ_session()
        session_id = "concurrency-orphan-test"

        threads = [
            threading.Thread(target=mod._write_cache, args=(session_id, {"n": i}))
            for i in range(20)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=30)

        cache_name = os.path.basename(mod._cache_path(session_id))
        leftovers = [p.name for p in tmp_path.iterdir() if p.name != cache_name]
        assert leftovers == [], f"orphan temp files: {leftovers}"
