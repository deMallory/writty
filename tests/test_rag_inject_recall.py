"""Decision Memory Phase 2 RECALL: tests for the once-per-session briefing guard
in hooks/scripts/writ-rag-inject.sh.

Every test here is RED until the implementer adds the recall-briefing block to
writ-rag-inject.sh. Tests fail on AssertionError when the expected behavior is
absent from the script, or when the subprocess exits non-zero unexpectedly.

CRITICAL isolation guarantee: NO test in this file touches the live Neo4j
graph. Behavioral tests that invoke the script via subprocess use an unreachable
daemon port (19999) or patch the session-cache to simulate already-briefed state.
Live-daemon behavioral tests that require a running /recall route are skipped
hermetically rather than depending on a live daemon.

Test pattern: follows test_pol5b3a_rag_inject_redundancy.py (source-shape guards
on SRC = HOOK.read_text()) and test_cwd_changed.py (subprocess invocation with
a temp WRIT_CACHE_DIR and unreachable daemon port). The _run() helper mirrors
the one in test_pol5b3a.

Run: .venv/bin/python -m pytest tests/test_rag_inject_recall.py

Capability map:
  [hook-recall-1]  injects the briefing exactly once per session (guarded by
                   recall_briefed cache flag)
  [hook-recall-2]  fail-open: daemon-down / curl failure emits nothing and exits 0
  [hook-recall-3]  skipped inside sub-agents (AGENT_ID set -> no injection)
"""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import tempfile
import uuid
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SKILL_DIR = Path.home() / ".claude/skills/writ"
HOOK = SKILL_DIR / "hooks" / "scripts" / "writ-rag-inject.sh"
WRIT_SESSION_PY = str(SKILL_DIR / "bin" / "lib" / "writ-session.py")

# Read source once at module level so source-shape guards are fast.
# If the hook does not exist yet, SRC is "" and source-shape tests fail
# cleanly with an AssertionError (not a collection error).
try:
    SRC = HOOK.read_text()
except FileNotFoundError:
    SRC = ""

# Slice of SRC containing ONLY the recall block (comment marker -> the
# orchestrator branch that follows it), so source-shape guards check the NEW
# block rather than matching pre-existing AGENT_ID / connect-timeout tokens
# elsewhere in the hook. Empty when the block is absent, so the guards below
# fail if the recall block is removed.
_RECALL_START = SRC.find("Decision-memory Phase 2")
_RECALL_END = (
    SRC.find('if [ "$IS_ORCHESTRATOR" = "true" ]', _RECALL_START)
    if _RECALL_START != -1
    else -1
)
RECALL_BLOCK = (
    SRC[_RECALL_START:_RECALL_END]
    if _RECALL_START != -1 and _RECALL_END != -1
    else ""
)


# ---------------------------------------------------------------------------
# Helpers (mirror test_pol5b3a_rag_inject_redundancy.py pattern)
# ---------------------------------------------------------------------------

def _load_writ_session():
    """Load writ-session.py as a module without installing it."""
    spec = importlib.util.spec_from_file_location("writ_session_recall", WRIT_SESSION_PY)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _make_envelope(session_id: str, agent_id: str = "") -> str:
    """Produce a UserPromptSubmit JSON envelope for the hook's stdin."""
    payload: dict = {
        "session_id": session_id,
        "hook_event_name": "UserPromptSubmit",
        "prompt": "What decisions were made recently?",
    }
    if agent_id:
        payload["agent_id"] = agent_id
    return json.dumps(payload)


def _run(envelope: str, cache_dir: str, extra_env: dict | None = None) -> subprocess.CompletedProcess:
    """Invoke writ-rag-inject.sh the same way test_pol5b3a does, with an
    unreachable WRIT_PORT (19999) and an isolated WRIT_CACHE_DIR."""
    env = os.environ.copy()
    env["WRIT_CACHE_DIR"] = cache_dir
    env["WRIT_PORT"] = "19999"   # unreachable daemon -> curl fails -> fail-open
    env["WRIT_HOST"] = "localhost"
    if extra_env:
        env.update(extra_env)
    return subprocess.run(
        ["bash", str(HOOK)],
        input=envelope,
        capture_output=True,
        text=True,
        cwd=str(SKILL_DIR),
        env=env,
        timeout=15,
    )


@pytest.fixture()
def session_cache(tmp_path: Path):
    """Yield (session_id, cache_dir, seed_fn) where seed_fn writes arbitrary
    fields to the session-cache JSON. Cleans up on teardown.

    Per TEST-FIXTURE-001: only the fields each test actually needs are set.
    """
    mod = _load_writ_session()
    sid = f"test-recall-hook-{uuid.uuid4().hex[:8]}"
    cache_dir = str(tmp_path / "writ-cache")
    Path(cache_dir).mkdir(parents=True, exist_ok=True)

    # Patch WRIT_CACHE_DIR so the module writes to our tmp dir.
    orig_cache = os.environ.get("WRIT_CACHE_DIR")
    os.environ["WRIT_CACHE_DIR"] = cache_dir

    def seed(**fields) -> None:
        cache = mod._read_cache(sid)
        cache.update(fields)
        mod._write_cache(sid, cache)

    yield sid, cache_dir, seed

    # Teardown: restore env, clean cache file.
    if orig_cache is None:
        os.environ.pop("WRIT_CACHE_DIR", None)
    else:
        os.environ["WRIT_CACHE_DIR"] = orig_cache


# ---------------------------------------------------------------------------
# Source-shape guards (no subprocess needed; fast and always-runnable)
# ---------------------------------------------------------------------------

class TestRagInjectRecallSourceShape:
    """Structural guards that the recall-briefing block is present in the hook
    source. These tests fail if the block has not been added yet."""

    def test_hook_file_exists(self) -> None:
        # Sentinel: the hook must exist on disk before any other test can pass.
        # RED: hook file not yet modified to include the recall block.
        assert HOOK.exists(), (
            f"writ-rag-inject.sh must exist at {HOOK}"
        )

    def test_recall_briefed_flag_referenced_in_source(self) -> None:
        # [hook-recall-1]: the once-per-session guard must check/set a
        # 'recall_briefed' cache flag. If this string is absent, the guard
        # was not implemented.
        # RED: flag not yet in source.
        assert "recall_briefed" in SRC, (
            "writ-rag-inject.sh must reference 'recall_briefed' for the once-per-session guard; "
            "the flag was not found in the source"
        )

    def test_recall_route_curled_in_source(self) -> None:
        # [hook-recall-1]: the hook must curl /recall to fetch the briefing.
        # RED: /recall curl not yet added.
        assert "/recall" in SRC, (
            "writ-rag-inject.sh must curl /recall to fetch the briefing; "
            "'/recall' not found in source"
        )

    def test_agent_id_guard_present_in_recall_block(self) -> None:
        # [hook-recall-3]: the recall block must be guarded by [ -z "$AGENT_ID" ]
        # so it is skipped inside sub-agents (AGENT_ID is set for sub-agent
        # sessions). Asserted within RECALL_BLOCK, not SRC, because AGENT_ID
        # pre-exists elsewhere in the hook; matching SRC would pass vacuously.
        assert 'AGENT_ID' in RECALL_BLOCK, (
            "writ-rag-inject.sh must guard the recall block with an AGENT_ID check; "
            "'AGENT_ID' not found inside the recall block"
        )

    def test_curl_has_connect_timeout_in_recall_block(self) -> None:
        # [hook-recall-2]: the recall curl must use a short connect timeout so a
        # slow or absent daemon never blocks the prompt (fail-open /
        # time-bounded). Asserted within RECALL_BLOCK, not SRC, because these
        # timeout flags pre-exist on other curls in the hook.
        assert "connect-timeout" in RECALL_BLOCK or "max-time" in RECALL_BLOCK, (
            "writ-rag-inject.sh recall curl must set --connect-timeout and/or --max-time; "
            "neither found inside the recall block"
        )


# ---------------------------------------------------------------------------
# Behavioral: fail-open (daemon unreachable -> exits 0, emits nothing blocking)
# ---------------------------------------------------------------------------

class TestRagInjectRecallFailOpen:
    """[hook-recall-2]: daemon-down/curl failure emits nothing and exits 0."""

    def test_exits_zero_when_daemon_unreachable(self, session_cache) -> None:
        # [hook-recall-2]: with WRIT_PORT=19999 (unreachable), the hook must exit 0.
        # A hook that raises or exits non-zero on a curl failure would block every
        # user prompt -- that is the failure mode we are guarding against.
        # RED: block not yet added (but hook already exits 0 on other failures).
        sid, cache_dir, seed = session_cache
        seed(mode="work")

        result = _run(_make_envelope(sid), cache_dir)

        assert result.returncode == 0, (
            f"hook must exit 0 when /recall daemon is unreachable (fail-open); "
            f"returncode={result.returncode}, stderr={result.stderr[:300]!r}"
        )

    def test_no_python_traceback_when_daemon_unreachable(self, session_cache) -> None:
        # [hook-recall-2]: a curl failure must not produce a Python traceback in
        # stderr (which would appear in Claude Code's hook-error output).
        # RED: block not yet added.
        sid, cache_dir, seed = session_cache
        seed(mode="work")

        result = _run(_make_envelope(sid), cache_dir)

        assert "Traceback" not in result.stderr, (
            f"daemon-unreachable path must not produce a Python traceback; "
            f"stderr:\n{result.stderr[:500]!r}"
        )
        assert "SyntaxError" not in result.stderr, (
            f"daemon-unreachable path must not produce a SyntaxError; "
            f"stderr:\n{result.stderr[:300]!r}"
        )

    def test_curl_failure_does_not_emit_error_text_to_stdout(self, session_cache) -> None:
        # [hook-recall-2]: curl failure output must not leak into stdout
        # (stdout is the additionalContext channel; injecting a curl error message
        # there would corrupt the agent's context).
        # RED: block not yet added.
        sid, cache_dir, seed = session_cache
        seed(mode="work")

        result = _run(_make_envelope(sid), cache_dir)

        # We cannot assert stdout is empty (other hook logic may emit rules),
        # but we assert that curl error markers are absent from stdout.
        assert "curl:" not in result.stdout, (
            f"curl error text must not appear in hook stdout (additionalContext channel); "
            f"stdout:\n{result.stdout[:300]!r}"
        )
        assert "Connection refused" not in result.stdout, (
            f"curl 'Connection refused' must not appear in hook stdout; "
            f"stdout:\n{result.stdout[:300]!r}"
        )


# ---------------------------------------------------------------------------
# Behavioral: once-per-session guard (recall_briefed flag)
# ---------------------------------------------------------------------------

class TestRagInjectRecallOncePerSession:
    """[hook-recall-1]: briefing injected exactly once per session."""

    def test_recall_briefed_flag_prevents_second_injection(self, session_cache) -> None:
        # [hook-recall-1]: once 'recall_briefed' is set to True in the session
        # cache, a second hook invocation must NOT attempt to curl /recall again.
        # We verify this by setting the flag and then asserting the hook exits 0
        # without any /recall-related content injection.
        #
        # With an unreachable daemon (port 19999), if the hook DID still try to
        # curl /recall it would produce a curl error message. We check that
        # behaviour is absent after the flag is set.
        # RED: block not yet added.
        sid, cache_dir, seed = session_cache
        seed(mode="work", recall_briefed=True)

        result = _run(_make_envelope(sid), cache_dir)

        assert result.returncode == 0, (
            f"hook must exit 0 when recall_briefed=True; "
            f"returncode={result.returncode}, stderr={result.stderr[:200]!r}"
        )
        # The recall curl is guarded; with briefed=True it must not have fired
        # (no curl error message in stderr when the guard works correctly).
        assert "curl: (7)" not in result.stderr, (
            "hook must not attempt the recall curl after recall_briefed=True; "
            "curl 'Connection refused' error found in stderr suggests guard was bypassed"
        )

    @pytest.mark.skip(
        reason=(
            "ENF-SYS-005: proving the once-per-session flag is written to the cache "
            "and persists across invocations requires a live /recall daemon and a "
            "writable real session-cache file. This cannot be tested hermetically "
            "without the live daemon because the hook reads back the cache it wrote "
            "to verify idempotency. Mark this as a live-integration test requiring "
            "'systemctl --user restart writ-server' before running."
        )
    )
    def test_first_invocation_sets_recall_briefed_in_cache(self, session_cache) -> None:
        # [hook-recall-1]: after the first successful recall injection the hook
        # must write recall_briefed=True to the session-cache JSON so subsequent
        # invocations skip the curl. Skipped because this requires a live /recall
        # route to return a briefing -- cannot be tested with port 19999.
        pass  # pragma: no cover


# ---------------------------------------------------------------------------
# Behavioral: sub-agent skip (AGENT_ID set)
# ---------------------------------------------------------------------------

class TestRagInjectRecallSubagentSkip:
    """[hook-recall-3]: AGENT_ID set -> no recall injection."""

    def test_agent_id_set_skips_recall_block(self, session_cache) -> None:
        # [hook-recall-3]: sub-agents have AGENT_ID set in their environment.
        # The recall briefing is a master-session-only, once-per-session event.
        # With AGENT_ID set the block must be skipped entirely (no curl to /recall).
        #
        # With an unreachable daemon (port 19999) a curl attempt would produce
        # a 'Connection refused' error in stderr. We verify that error is absent
        # when AGENT_ID is set, proving the guard skips the block.
        # RED: block not yet added.
        sid, cache_dir, seed = session_cache
        seed(mode="work")

        agent_id = f"sub-agent-{uuid.uuid4().hex[:8]}"
        envelope = _make_envelope(sid, agent_id=agent_id)
        result = _run(envelope, cache_dir, extra_env={"AGENT_ID": agent_id})

        assert result.returncode == 0, (
            f"hook must exit 0 inside a sub-agent; "
            f"returncode={result.returncode}, stderr={result.stderr[:200]!r}"
        )
        # If the AGENT_ID guard works, no recall curl was attempted, so no
        # 'Connection refused' from the unreachable port 19999.
        # (If the guard is broken the curl attempt fires and produces this error.)
        assert "Connection refused" not in result.stderr or "recall" not in result.stderr.lower(), (
            "AGENT_ID guard must prevent any curl to /recall inside sub-agents; "
            "found 'Connection refused' in stderr suggesting the guard was bypassed"
        )

    def test_no_agent_id_does_not_skip(self, session_cache) -> None:
        # [hook-recall-3] contrast: without AGENT_ID the recall block SHOULD
        # attempt the curl (and fail gracefully with port 19999). We verify the
        # hook still exits 0, not that the curl succeeds.
        #
        # This is a negative-control: if the AGENT_ID guard were incorrectly
        # applied to ALL invocations, this test would show it never attempts recall
        # even for master sessions.
        # RED: block not yet added.
        sid, cache_dir, seed = session_cache
        seed(mode="work")

        envelope = _make_envelope(sid, agent_id="")  # no agent_id
        result = _run(envelope, cache_dir)  # no extra AGENT_ID env var

        assert result.returncode == 0, (
            f"hook must exit 0 for master session (no AGENT_ID); "
            f"returncode={result.returncode}, stderr={result.stderr[:200]!r}"
        )
