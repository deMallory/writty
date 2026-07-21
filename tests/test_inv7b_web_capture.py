"""INV-7b: WebFetch/WebSearch auto-capture hook (fail-closed web citations).

The web analog of the 7a Bash-capture hook: in investigate mode, web content the
agent fetches is recorded as url citations in the INV-2 citation_log, so the INV-7a
triangulation-gate enforces over evidence the agent did not hand-curate.

Hermetic: the hook writes to a WRIT_CACHE_DIR temp cache via writ-session.py update;
no server. Synthetic envelopes match parse-hook-stdin.py's contract
({session_id, tool_name, tool_input, tool_output}).
"""
from __future__ import annotations

import json
import os
import subprocess
import uuid
from pathlib import Path

import pytest

SKILL_DIR = Path(__file__).resolve().parent.parent
HOOK = str(SKILL_DIR / "hooks" / "scripts" / "writ-web-capture.sh")
PLUGIN_HOOKS = SKILL_DIR / "hooks" / "hooks.json"


def _seed_cache(cache_dir: Path, sid: str, mode: str) -> None:
    with open(cache_dir / f"writ-session-{sid}.json", "w") as f:
        json.dump({"session_id": sid, "mode": mode, "citation_log": [],
                   "pretool_queried_files": []}, f)


def _run_hook(cache_dir: Path, envelope: dict) -> subprocess.CompletedProcess:
    env = {**os.environ, "WRIT_CACHE_DIR": str(cache_dir)}
    return subprocess.run(["bash", HOOK], input=json.dumps(envelope),
                          capture_output=True, text=True, env=env, timeout=20)


def _url_citations(cache_dir: Path, sid: str) -> list[dict]:
    path = cache_dir / f"writ-session-{sid}.json"
    if not path.exists():
        return []
    cache = json.loads(path.read_text())
    return [r for r in cache.get("citation_log", []) if r.get("artifact_type") == "url"]


def _webfetch_envelope(sid: str, url: str, content: str = "fetched content") -> dict:
    return {"session_id": sid, "tool_name": "WebFetch",
            "tool_input": {"url": url, "prompt": "summarize"}, "tool_output": content}


class TestHookStructure:
    def test_hook_exists(self) -> None:
        assert Path(HOOK).exists(), f"{HOOK} does not exist yet"

    def test_references_web_tools_and_citation_and_mode_gate(self) -> None:
        assert Path(HOOK).exists(), f"{HOOK} does not exist yet"
        body = Path(HOOK).read_text()
        assert "WebFetch" in body and "WebSearch" in body
        assert "--add-citation" in body
        assert "investigate" in body, "capture must be gated on investigate mode"


class TestWebFetchCapture:
    def test_webfetch_records_url_citation(self, tmp_path) -> None:
        sid = f"wf-{uuid.uuid4().hex[:8]}"
        _seed_cache(tmp_path, sid, "investigate")
        r = _run_hook(tmp_path, _webfetch_envelope(sid, "https://a.com/page"))
        assert r.returncode == 0, f"hook rc={r.returncode}; stderr={r.stderr[:600]}"
        urls = _url_citations(tmp_path, sid)
        assert any(u.get("ref") == "https://a.com/page" for u in urls), \
            f"WebFetch url must be captured; got {urls}"

    def test_captured_url_carries_excerpt_hash(self, tmp_path) -> None:
        sid = f"wf-{uuid.uuid4().hex[:8]}"
        _seed_cache(tmp_path, sid, "investigate")
        _run_hook(tmp_path, _webfetch_envelope(sid, "https://a.com/page", "the content"))
        urls = _url_citations(tmp_path, sid)
        assert urls and urls[0].get("excerpt_hash"), "captured url must carry an excerpt_hash (INV-7a)"


class TestWebSearchCapture:
    def test_websearch_records_result_urls(self, tmp_path) -> None:
        sid = f"ws-{uuid.uuid4().hex[:8]}"
        _seed_cache(tmp_path, sid, "investigate")
        envelope = {
            "session_id": sid, "tool_name": "WebSearch",
            "tool_input": {"query": "best practice X"},
            "tool_output": "Results:\nhttps://docs.example.com/x\nhttps://other.org/y\n",
        }
        r = _run_hook(tmp_path, envelope)
        assert r.returncode == 0, f"hook rc={r.returncode}; stderr={r.stderr[:600]}"
        urls = _url_citations(tmp_path, sid)
        assert len(urls) >= 1, f"WebSearch result URLs must be captured; got {urls}"


class TestModeGateAndNonWeb:
    def test_work_mode_does_not_capture(self, tmp_path) -> None:
        sid = f"work-{uuid.uuid4().hex[:8]}"
        _seed_cache(tmp_path, sid, "work")
        r = _run_hook(tmp_path, _webfetch_envelope(sid, "https://a.com/page"))
        assert r.returncode == 0
        assert _url_citations(tmp_path, sid) == [], "capture must be investigate-only"

    def test_non_web_tool_ignored(self, tmp_path) -> None:
        sid = f"read-{uuid.uuid4().hex[:8]}"
        _seed_cache(tmp_path, sid, "investigate")
        envelope = {"session_id": sid, "tool_name": "Read",
                    "tool_input": {"file_path": "/x.py"}, "tool_output": "code"}
        r = _run_hook(tmp_path, envelope)
        assert r.returncode == 0
        assert _url_citations(tmp_path, sid) == [], "non-web tools must not produce url citations"


class TestRegistration:
    def _registers(self, manifest_path: Path) -> bool:
        data = json.loads(manifest_path.read_text())
        post = (data.get("hooks", data)).get("PostToolUse", []) if isinstance(data.get("hooks", data), dict) else data.get("PostToolUse", [])
        for entry in post:
            matcher = entry.get("matcher", "")
            cmds = " ".join(h.get("command", "") for h in entry.get("hooks", []))
            if "WebFetch" in matcher and "writ-web-capture" in cmds:
                return True
        return False

    def test_plugin_hooks_registers_hook(self) -> None:
        assert PLUGIN_HOOKS.exists()
        assert self._registers(PLUGIN_HOOKS), \
            "hooks/hooks.json must register writ-web-capture under a WebFetch|WebSearch matcher"
