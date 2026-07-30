"""POL-5d: PostCompact state-rehydration (A) + PreCompact re-document (C).

A: after /compact the next rag-inject only fires on the next user prompt, so an
   autonomously-resuming agent has no workflow bearings. cmd_reset_after_compaction
   now returns mode + phase, and writ-postcompact.sh emits a compact state line.
C: writ-precompact.sh's "reduce footprint before compression" rationale is false
   (the session cache is a /tmp file, not part of the compacted context). Re-document;
   behavior unchanged.

RED until writ-session.py / writ-postcompact.sh / writ-precompact.sh are updated.
"""

from __future__ import annotations

import importlib.util
import io
import json
import os
import subprocess
import tempfile
import uuid
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

import pytest

SKILL_DIR = Path(__file__).resolve().parent.parent
WRIT_SESSION_PY = str(SKILL_DIR / "bin" / "lib" / "writ-session.py")
PRECOMPACT = SKILL_DIR / "hooks" / "scripts" / "writ-precompact.sh"
POSTCOMPACT = SKILL_DIR / "hooks" / "scripts" / "writ-postcompact.sh"

PRECOMPACT_SRC = PRECOMPACT.read_text()
WRIT_SESSION_SRC = Path(WRIT_SESSION_PY).read_text()
# POL-6g-3: cmd_clear_rules_for_compaction moved to writ/session/session_lifecycle.py.
SESSION_LIFECYCLE_SRC = (SKILL_DIR / "writ" / "session" / "session_lifecycle.py").read_text()

MISLEADING = "footprint before compression"
CORRECTED = "not part of the compacted context"
BYTES_NOTE = "bytes_freed is cache-file bytes, not context tokens"


def _load_writ_session():
    spec = importlib.util.spec_from_file_location("writ_session_5d", WRIT_SESSION_PY)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _server_up() -> bool:
    try:
        import urllib.request

        from tests._daemon import _health_url

        with urllib.request.urlopen(_health_url(), timeout=1) as r:
            return r.status == 200
    except Exception:
        return False


requires_server = pytest.mark.skipif(not _server_up(), reason="writ server not running")


# --------------------------------------------------------------------------- #
# A. cmd_reset_after_compaction returns mode + phase (unit)
# --------------------------------------------------------------------------- #
class TestResetReturnsModeAndPhase:
    def setup_method(self) -> None:
        self.mod = _load_writ_session()
        self._tmp = tempfile.mkdtemp()
        self._env_patch = mock.patch.dict(os.environ, {"WRIT_CACHE_DIR": self._tmp})
        self._env_patch.start()

    def teardown_method(self) -> None:
        self._env_patch.stop()
        import shutil

        shutil.rmtree(self._tmp, ignore_errors=True)

    def _run(self, sid: str, cache: dict) -> dict:
        with open(self.mod._cache_path(sid), "w") as f:
            json.dump(cache, f)
        buf = io.StringIO()
        with redirect_stdout(buf):
            self.mod.cmd_reset_after_compaction(sid)
        return json.loads(buf.getvalue().strip())

    def test_result_includes_mode_and_phase(self) -> None:
        sid = "test-5d-unit"
        cache = {"mode": "work", "current_phase": "implementation",
                 "loaded_rule_ids_by_phase": {"implementation": ["X"]}, "remaining_budget": 500}
        result = self._run(sid, cache)
        assert result.get("mode") == "work", f"mode missing/wrong: {result}"
        assert result.get("phase") == "implementation", f"phase missing/wrong: {result}"

    def test_existing_keys_preserved(self) -> None:
        sid = "test-5d-unit2"
        cache = {"mode": "work", "current_phase": "implementation",
                 "loaded_rule_ids_by_phase": {"implementation": ["X"]}, "remaining_budget": 500}
        result = self._run(sid, cache)
        assert "rules_cleared" in result and result["budget_reset"] is True


# --------------------------------------------------------------------------- #
# A. writ-postcompact.sh emits the state line (behavioral)
# --------------------------------------------------------------------------- #
@requires_server
class TestPostCompactStateLine:
    @pytest.fixture()
    def seeded(self):
        mod = _load_writ_session()
        sid = f"test-5d-{uuid.uuid4().hex[:8]}"

        def seed(**fields):
            cache = mod._read_cache(sid)
            cache.update(fields)
            mod._write_cache(sid, cache)
            return sid

        yield sid, seed
        p = Path(tempfile.gettempdir()) / f"writ-session-{sid}.json"
        if p.exists():
            p.unlink()

    def _run_hook(self, sid: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            ["bash", str(POSTCOMPACT)],
            input=json.dumps({"session_id": sid, "event": "compact"}),
            capture_output=True, text=True, cwd=str(SKILL_DIR),
            env={**os.environ, "WRIT_HOST": "localhost"}, timeout=20,
        )

    def test_state_line_emitted_for_work_session(self, seeded) -> None:
        sid, seed = seeded
        seed(mode="work", current_phase="implementation")
        r = self._run_hook(sid)
        assert r.returncode == 0, f"exit {r.returncode}; stderr={r.stderr[:300]!r}"
        assert "post-compact workflow state" in r.stdout, f"state line missing: {r.stdout[:400]!r}"
        assert "mode=work" in r.stdout
        assert "implementation" in r.stdout

    def test_verification_directive_still_emitted(self, seeded) -> None:
        sid, seed = seeded
        seed(mode="work", current_phase="implementation")
        r = self._run_hook(sid)
        assert "fresh evidence" in r.stdout.lower()
        assert "STOP" in r.stdout

    def test_no_state_line_when_mode_unset(self) -> None:
        # unseeded session -> daemon returns default mode (None); no state line,
        # but the verification directive still emits (back-compat with phase4c).
        sid = f"test-5d-nomode-{uuid.uuid4().hex[:8]}"
        try:
            r = subprocess.run(
                ["bash", str(POSTCOMPACT)],
                input=json.dumps({"session_id": sid, "event": "compact"}),
                capture_output=True, text=True, cwd=str(SKILL_DIR),
                env={**os.environ, "WRIT_HOST": "localhost"}, timeout=20,
            )
            assert r.returncode == 0, f"exit {r.returncode}; stderr={r.stderr[:300]!r}"
            assert "post-compact workflow state" not in r.stdout, (
                f"state line must not emit without a mode: {r.stdout[:300]!r}"
            )
            assert "fresh evidence" in r.stdout.lower(), "directive must still emit"
        finally:
            p = Path(tempfile.gettempdir()) / f"writ-session-{sid}.json"
            if p.exists():
                p.unlink()


# --------------------------------------------------------------------------- #
# C. PreCompact re-documented (source-shape + behavioral)
# --------------------------------------------------------------------------- #
class TestPreCompactRedocumented:
    def test_misleading_footprint_claim_gone(self) -> None:
        assert MISLEADING not in PRECOMPACT_SRC, (
            "writ-precompact.sh must drop the false 'reduce footprint before "
            "compression' rationale (the cache is not in the compacted context)"
        )

    def test_corrected_statement_present(self) -> None:
        assert CORRECTED in PRECOMPACT_SRC, (
            "writ-precompact.sh must state that the session cache is not part of "
            "the compacted context"
        )

    def test_clear_rules_docstring_corrected(self) -> None:
        # the cmd carries a note that bytes_freed is cache bytes, not context tokens
        assert BYTES_NOTE in SESSION_LIFECYCLE_SRC, (
            "cmd_clear_rules_for_compaction must note bytes_freed is cache-file bytes, "
            "not context tokens"
        )

    def test_precompact_hook_still_exits_zero(self) -> None:
        r = subprocess.run(
            ["bash", str(PRECOMPACT)], input="", capture_output=True, text=True,
            cwd=str(SKILL_DIR), timeout=15,
        )
        assert r.returncode == 0, f"precompact must still exit 0; stderr={r.stderr[:200]!r}"
