"""Increment 2: surface the systematic-debugging playbook at `mode set debug`.

When a session is in debug mode, writ-rag-inject.sh must fire a second /query
restricted to Playbook+Technique nodes (domain=process) keyed on the user's
prompt, so PBK-PROC-DEBUG-001 (and the diagnose-* classifiers from Increment 3)
surface against the actual symptom. This mirrors the work-mode methodology
companion at writ-rag-inject.sh:749, parameterized by mode.

Contract pinned here:
1. The /query retrieval contract returns PBK-PROC-DEBUG-001 for a debug symptom
   (integration, real server -- unprovable by mocks; TEST-INT-001).
2. End-to-end: a debug-mode hook run logs a rag_query with
   query_source='debug-playbook'.
3. No regression: a work-mode hook run still logs query_source='methodology'.
4. The debug query does NOT fire in conversation mode (TEST-EDGE-001).
5. Structural: the hook source's methodology block references the debug path.

Live-hook tests mirror tests/test_methodology_companion_orchestrator.py and use
the server's cache-dir resolution (WRIT_CACHE_DIR or tempfile.gettempdir()).

W2 (server package split, branch refactor/w2-server-split): the structural
assertion in TestDebugPlaybookStructural reads via writ_server_source()
(tests/conftest.py), which is layout-agnostic -- it scans every *.py under
writ/server/ if that directory exists (post-split: this content is expected in
routes/query.py), else the single writ/server.py file (pre-split).
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
import uuid
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from writ.shared.logging import read_streams, resolve_project  # noqa: E402

from tests.conftest import writ_server_source

# Exercises the router's cwd-based project-scope resolution to a tmp subdir;
# opt out of the autouse WRIT_FRICTION_LOG redirect so rag_query telemetry
# routes to the split per-project streams under WRIT_LOG_ROOT (P1 router).
pytestmark = pytest.mark.no_friction_isolation


from tests._daemon import _port

SKILL_DIR = str(Path(__file__).resolve().parent.parent)
HOOK = f"{SKILL_DIR}/hooks/scripts/writ-rag-inject.sh"
SERVER = f"http://localhost:{_port()}"
DEBUG_SYMPTOM = (
    "A unit test is failing unexpectedly after my change and I need to debug "
    "the root cause -- help me investigate this systematically."
)


def _server_up() -> bool:
    try:
        with urllib.request.urlopen(f"{SERVER}/health", timeout=2):
            return True
    except (urllib.error.URLError, OSError):
        return False


def _seed_cache(cache_dir: str, sid: str, mode: str) -> str:
    """Seed a non-orchestrator session cache in the server's cache dir."""
    path = os.path.join(cache_dir, f"writ-session-{sid}.json")
    with open(path, "w") as f:
        json.dump(
            {
                "mode": mode,
                "is_orchestrator": False,
                "is_subagent": False,
                "current_phase": "implementation" if mode == "work" else None,
                "loaded_rule_ids": [],
                "loaded_rule_ids_by_phase": {},
                "remaining_budget": 8000,
                "context_percent": 0,
                "queries": 0,
                "files_written": [],
                "loaded_rules": [],
            },
            f,
        )
    return path


def _run_hook_events(tmp_path, sid: str, prompt: str) -> tuple[int, str, list[dict]]:
    """Run writ-rag-inject.sh against the live server in a tmp project cwd;
    return (returncode, stderr, parsed rag_query events from the P1 metrics
    stream). rag_query is a `metrics`-stream event; the project scope derives
    from the hook's cwd, resolved the same way the router does."""
    project_root = tmp_path / "proj"
    project_root.mkdir(exist_ok=True)
    (project_root / ".git").mkdir(exist_ok=True)  # marker for router project scope

    envelope = json.dumps({"session_id": sid, "prompt": prompt})
    result = subprocess.run(
        ["bash", HOOK],
        input=envelope,
        capture_output=True,
        text=True,
        cwd=str(project_root),
        timeout=15,
    )
    events = read_streams(resolve_project(str(project_root)), ["metrics"])
    return result.returncode, result.stderr, events


class TestDebugPlaybookRetrievalContract:
    """The /query mechanism the hook relies on surfaces the debug playbook."""

    def test_query_surfaces_debug_playbook(self) -> None:
        if not _server_up():
            pytest.skip("Writ server unreachable")
        req = urllib.request.Request(
            f"{SERVER}/query",
            data=json.dumps({
                "query": DEBUG_SYMPTOM,
                "node_types": ["Playbook", "Technique"],
                "domain": "process",
                "budget_tokens": 2000,
                "top_k": 6,
            }).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            body = json.loads(resp.read())
        ids = [r.get("rule_id") for r in body.get("rules", [])]
        assert "PBK-PROC-DEBUG-001" in ids, (
            f"debug playbook must surface for a debug symptom; got {ids}"
        )


class TestDebugPlaybookInjectionEndToEnd:
    """Run the hook with a seeded debug-mode cache and assert the friction log."""

    def test_debug_mode_fires_debug_playbook_query(self, tmp_path) -> None:
        if not _server_up():
            pytest.skip("Writ server unreachable")
        sid = f"debug-pbk-e2e-{uuid.uuid4().hex[:8]}"
        cache_dir = os.environ.get("WRIT_CACHE_DIR", tempfile.gettempdir())
        cache_path = _seed_cache(cache_dir, sid, "debug")
        try:
            rc, stderr, events = _run_hook_events(tmp_path, sid, DEBUG_SYMPTOM)
        finally:
            try:
                os.unlink(cache_path)
            except FileNotFoundError:
                pass
        assert rc == 0, f"hook returned {rc}; stderr={stderr[:800]}"
        debug_q = [
            e for e in events
            if e.get("event") == "rag_query"
            and e.get("query_source") == "debug-playbook"
        ]
        assert debug_q, (
            "no rag_query with query_source=debug-playbook in debug-mode hook run. "
            f"events:\n{json.dumps(events, indent=2)}"
        )

    def test_work_mode_still_fires_methodology(self, tmp_path) -> None:
        """Regression oracle: parameterizing the block must not break work mode."""
        if not _server_up():
            pytest.skip("Writ server unreachable")
        sid = f"work-method-e2e-{uuid.uuid4().hex[:8]}"
        cache_dir = os.environ.get("WRIT_CACHE_DIR", tempfile.gettempdir())
        cache_path = _seed_cache(cache_dir, sid, "work")
        try:
            rc, stderr, events = _run_hook_events(
                tmp_path, sid,
                "Implement a function that sums a list of integers; plan and "
                "write tests first please.",
            )
        finally:
            try:
                os.unlink(cache_path)
            except FileNotFoundError:
                pass
        assert rc == 0, f"hook returned {rc}; stderr={stderr[:800]}"
        method_q = [
            e for e in events
            if e.get("event") == "rag_query"
            and e.get("query_source") == "methodology"
        ]
        assert method_q, (
            "work-mode methodology companion regressed (no query_source=methodology). "
            f"events:\n{json.dumps(events, indent=2)}"
        )

    def test_conversation_mode_does_not_fire_debug_playbook(self, tmp_path) -> None:
        if not _server_up():
            pytest.skip("Writ server unreachable")
        sid = f"conv-e2e-{uuid.uuid4().hex[:8]}"
        cache_dir = os.environ.get("WRIT_CACHE_DIR", tempfile.gettempdir())
        cache_path = _seed_cache(cache_dir, sid, "conversation")
        try:
            rc, stderr, events = _run_hook_events(tmp_path, sid, DEBUG_SYMPTOM)
        finally:
            try:
                os.unlink(cache_path)
            except FileNotFoundError:
                pass
        assert rc == 0, f"hook returned {rc}; stderr={stderr[:800]}"
        debug_q = [
            e for e in events
            if e.get("event") == "rag_query"
            and e.get("query_source") == "debug-playbook"
        ]
        assert not debug_q, (
            f"debug-playbook query must NOT fire in conversation mode; events:\n"
            f"{json.dumps(events, indent=2)}"
        )


class TestDebugPlaybookStructural:
    """Lint-level guard: the methodology block must handle the debug path so a
    future regression that drops it is caught without a live server."""

    def test_methodology_block_references_debug_playbook(self) -> None:
        # #8: the debug -> debug-playbook query_source map moved into the
        # /prompt-bundle endpoint; the hook delivers the rendered bundle.
        server = writ_server_source()
        assert "debug-playbook" in server, (
            "the /prompt-bundle endpoint must map debug -> 'debug-playbook'"
        )
        # 1.7 CUTOVER: methodology is delivered by /methodology-companion now (the
        # companion serves the debug FLOOR from node-declared floor_modes), not by
        # a mode->node_type /query. Lint guards: the debug case exists and the hook
        # posts to the companion endpoint (behavioral firing proven by the e2e test).
        assert re.search(r'"debug":\s*"debug-playbook"', server), (
            "the endpoint must keep a debug-mode query_source case"
        )
        assert "methodology_companion" in server, (
            "the endpoint must deliver methodology via the methodology_companion handler"
        )
