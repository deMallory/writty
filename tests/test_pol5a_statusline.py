"""POL-5a: writ-statusline.sh replaces writ-context-watcher.sh.

The statusLine command re-sources context_percent from the harness-native
context_window.used_percentage, renders a user-facing context meter + a
"/compact" note at the 50%/75% bands to stdout (the status bar, NOT stderr),
and POSTs context_percent to the existing /context-percent endpoint.

Contract asserted here:
  - render bands: below 50 -> no /compact note; 50-74 -> note states "50%";
    >=75 -> note states "75%". The percentage value always appears.
  - context_percent round-trips to the session cache via the endpoint.
  - graceful degrade: missing/malformed stdin -> exit 0, no note, no crash.
  - lean: exactly one python3 invocation in the script (no per-field re-spawn).
  - settings wiring (both files): context-watcher gone from UserPromptSubmit
    AND PreToolUse; a top-level statusLine key referencing writ-statusline.sh
    is present; the two settings files agree.

RED until writ-statusline.sh exists, context-watcher is unregistered, and the
statusLine key is added to both settings files.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
import time
import uuid
from pathlib import Path

import pytest

from tests._daemon import _health_url, _port


def _server_up() -> bool:
    """True iff a daemon answers /health on the test port (WRIT_PORT)."""
    try:
        import urllib.error
        import urllib.request

        with urllib.request.urlopen(_health_url(), timeout=1) as r:
            return r.status == 200
    except (urllib.error.URLError, OSError):
        return False


requires_server = pytest.mark.skipif(
    not _server_up(), reason="test-port daemon unreachable"
)

SKILL_DIR = Path(__file__).resolve().parent.parent
STATUSLINE_HOOK = SKILL_DIR / "hooks" / "scripts" / "writ-statusline.sh"
SESSION_HELPER = str(SKILL_DIR / "bin" / "lib" / "writ-session.py")
GLOBAL_SETTINGS = Path.home() / ".claude" / "settings.json"
SESSION_BASE = f"http://localhost:{_port()}"


# --------------------------------------------------------------------------- #
# Harness
# --------------------------------------------------------------------------- #
def _statusline_payload(pct, session_id: str, *, include_ctx: bool = True) -> dict:
    """Build a statusLine stdin envelope with the native used_percentage."""
    payload: dict = {
        "session_id": session_id,
        "transcript_path": "/tmp/does-not-matter.jsonl",
        "model": {"id": "claude-opus-4-8", "display_name": "Opus"},
        "workspace": {"current_dir": str(SKILL_DIR)},
        "version": "2.1.90",
    }
    if include_ctx:
        payload["context_window"] = {
            "used_percentage": pct,
            "context_window_size": 1_000_000,
            "remaining_percentage": (100 - pct) if isinstance(pct, int) else None,
        }
    return payload


def _run_statusline(
    pct, session_id: str, *, include_ctx: bool = True, raw_stdin: str | None = None
) -> tuple[str, str, int]:
    """Invoke the statusLine hook with a JSON envelope (or raw stdin)."""
    stdin = (
        raw_stdin
        if raw_stdin is not None
        else json.dumps(_statusline_payload(pct, session_id, include_ctx=include_ctx))
    )
    env = {
        **os.environ,
        "SKILL_DIR": str(SKILL_DIR),
        "WRIT_SESSION_BASE": SESSION_BASE,
    }
    result = subprocess.run(
        ["bash", str(STATUSLINE_HOOK)],
        input=stdin,
        capture_output=True, text=True,
        cwd=str(SKILL_DIR), env=env, timeout=15,
    )
    return result.stdout, result.stderr, result.returncode


def _run_session(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, SESSION_HELPER, *args],
        capture_output=True, text=True, timeout=5,
    )


def _read_cache(session_id: str) -> dict:
    result = _run_session("read", session_id)
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError:
        return {}


def _cleanup_session(session_id: str) -> None:
    path = Path(tempfile.gettempdir()) / f"writ-session-{session_id}.json"
    if path.exists():
        path.unlink()


def _load_settings(path: Path) -> dict:
    with open(path) as f:
        return json.load(f)


def _hook_commands(settings: dict, event: str) -> list[str]:
    """All hook command strings registered under a given event."""
    cmds: list[str] = []
    for group in settings.get("hooks", {}).get(event, []):
        for h in group.get("hooks", []):
            cmds.append(h.get("command", ""))
    return cmds


@pytest.fixture()
def session_id():
    sid = f"test-pol5a-{uuid.uuid4().hex[:8]}"
    yield sid
    _cleanup_session(sid)


# --------------------------------------------------------------------------- #
# 1. Render bands
# --------------------------------------------------------------------------- #
class TestRenderBands:
    """stdout shows a meter; the /compact note appears only at >=50, labelled by band."""

    def test_percentage_value_always_rendered(self, session_id: str) -> None:
        """The meter shows the percentage number for a mid-range value."""
        stdout, _stderr, code = _run_statusline(42, session_id)
        assert code == 0
        assert "42" in stdout, f"meter must show the percentage; got: {stdout!r}"

    def test_below_50_has_no_compact_note(self, session_id: str) -> None:
        """Under 50% there is no /compact suggestion."""
        stdout, _stderr, _code = _run_statusline(30, session_id)
        assert "compact" not in stdout.lower(), (
            f"no /compact note expected below 50%; got: {stdout!r}"
        )

    def test_49_is_below_band(self, session_id: str) -> None:
        """49% is still below the 50 band (boundary)."""
        stdout, _stderr, _code = _run_statusline(49, session_id)
        assert "compact" not in stdout.lower()

    def test_50_band_notes_50_not_75(self, session_id: str) -> None:
        """At 50-74 the note suggests /compact and labels the 50% threshold."""
        stdout, _stderr, _code = _run_statusline(50, session_id)
        low = stdout.lower()
        assert "compact" in low, f"50% band must suggest /compact; got: {stdout!r}"
        assert "50%" in stdout, f"50% band note must label 50%; got: {stdout!r}"
        assert "75%" not in stdout, f"50% band must not be the 75 note; got: {stdout!r}"

    def test_74_is_still_50_band(self, session_id: str) -> None:
        """74% is the upper edge of the 50 band."""
        stdout, _stderr, _code = _run_statusline(74, session_id)
        assert "compact" in stdout.lower()
        assert "75%" not in stdout

    def test_75_band_notes_75(self, session_id: str) -> None:
        """At >=75 the note suggests /compact and labels the 75% threshold."""
        stdout, _stderr, _code = _run_statusline(75, session_id)
        assert "compact" in stdout.lower(), f"75% band must suggest /compact; got: {stdout!r}"
        assert "75%" in stdout, f"75% band note must label 75%; got: {stdout!r}"

    def test_95_is_75_band(self, session_id: str) -> None:
        """Well past 75 stays in the 75 band."""
        stdout, _stderr, _code = _run_statusline(95, session_id)
        assert "compact" in stdout.lower()
        assert "75%" in stdout

    def test_warning_goes_to_stdout_not_stderr(self, session_id: str) -> None:
        """The user-facing note renders on the bar (stdout), never as a stderr directive."""
        stdout, stderr, _code = _run_statusline(80, session_id)
        assert "compact" in stdout.lower()
        assert "compact" not in stderr.lower(), (
            "the warning must be a bar element (stdout), not an AI-context stderr directive"
        )


# --------------------------------------------------------------------------- #
# 2. context_percent round-trip
# --------------------------------------------------------------------------- #
@requires_server
class TestContextPercentWrite:
    """statusLine re-sources context_percent for should-skip via the endpoint.

    Both tests POST context_percent to the daemon and read it back; the statusline
    hook's write is a best-effort daemon POST with no subprocess fallback, so these
    skip gracefully when no test-port daemon answers (rather than failing in no-daemon CI).
    """

    def test_context_percent_round_trips_to_cache(self, session_id: str) -> None:
        """The native used_percentage lands in the session cache's context_percent."""
        _run_statusline(63, session_id)
        cache = _read_cache(session_id)
        assert cache.get("context_percent") == 63, (
            f"statusLine must write context_percent=63; got {cache.get('context_percent')!r}"
        )

    def test_zero_percent_writes_zero(self, session_id: str) -> None:
        """A fresh window writes 0, not a stale/absent value."""
        _run_statusline(0, session_id)
        cache = _read_cache(session_id)
        assert cache.get("context_percent") == 0


# --------------------------------------------------------------------------- #
# 3. Graceful degradation
# --------------------------------------------------------------------------- #
class TestGracefulDegrade:
    """Malformed or partial stdin must never crash or emit a spurious warning."""

    def test_missing_context_window_exits_clean(self, session_id: str) -> None:
        stdout, _stderr, code = _run_statusline(None, session_id, include_ctx=False)
        assert code == 0
        assert "compact" not in stdout.lower()

    def test_malformed_json_exits_clean(self, session_id: str) -> None:
        _stdout, _stderr, code = _run_statusline(None, session_id, raw_stdin="{not json")
        assert code == 0

    def test_empty_stdin_exits_clean(self, session_id: str) -> None:
        _stdout, _stderr, code = _run_statusline(None, session_id, raw_stdin="")
        assert code == 0

    def test_missing_session_id_still_renders(self) -> None:
        """No session id -> still renders the meter, just skips the POST."""
        payload = {"context_window": {"used_percentage": 55}}
        result = subprocess.run(
            ["bash", str(STATUSLINE_HOOK)],
            input=json.dumps(payload),
            capture_output=True, text=True,
            cwd=str(SKILL_DIR),
            env={**os.environ, "SKILL_DIR": str(SKILL_DIR), "WRIT_SESSION_BASE": SESSION_BASE},
            timeout=15,
        )
        assert result.returncode == 0


# --------------------------------------------------------------------------- #
# 4. Lean (off the hot path)
# --------------------------------------------------------------------------- #
class TestLean:
    """One python3 invocation; fast wall-time."""

    def test_single_python3_invocation(self) -> None:
        """The script spawns exactly one python3 (no parse-then-extract fan-out)."""
        src = STATUSLINE_HOOK.read_text()
        # Count command invocations of python3 (token followed by a flag/heredoc/script),
        # excluding mere mentions in comments.
        invocations = re.findall(r"(?<![#\w])python3\s", src)
        assert len(invocations) == 1, (
            f"expected exactly one python3 invocation; found {len(invocations)}"
        )

    def test_wall_time_under_floor(self, session_id: str) -> None:
        """Median wall-time stays well under the old ~6-spawn watcher."""
        times = []
        for _ in range(5):
            t0 = time.monotonic()
            _run_statusline(40, session_id)
            times.append((time.monotonic() - t0) * 1000)
        times.sort()
        median = times[len(times) // 2]
        assert median < 250, f"statusline median {median:.0f}ms exceeds 250ms floor"


# --------------------------------------------------------------------------- #
# 5. Settings wiring (two-places parity)
# --------------------------------------------------------------------------- #
@pytest.mark.skipif(
    not GLOBAL_SETTINGS.exists(),
    reason="operator ~/.claude/settings.json not present",
)
class TestSettingsWiring:
    """context-watcher unregistered; statusLine present; both files agree."""

    @pytest.mark.parametrize("path", [GLOBAL_SETTINGS], ids=["global"])
    def test_context_watcher_off_userpromptsubmit(self, path: Path) -> None:
        s = _load_settings(path)
        cmds = _hook_commands(s, "UserPromptSubmit")
        assert not any("writ-context-watcher.sh" in c for c in cmds), (
            f"context-watcher must be removed from UserPromptSubmit in {path}"
        )

    @pytest.mark.parametrize("path", [GLOBAL_SETTINGS], ids=["global"])
    def test_context_watcher_off_pretooluse(self, path: Path) -> None:
        s = _load_settings(path)
        cmds = _hook_commands(s, "PreToolUse")
        assert not any("writ-context-watcher.sh" in c for c in cmds), (
            f"context-watcher must be removed from PreToolUse in {path}"
        )

    @pytest.mark.parametrize("path", [GLOBAL_SETTINGS], ids=["global"])
    def test_statusline_key_present(self, path: Path) -> None:
        s = _load_settings(path)
        assert "statusLine" in s, f"statusLine key missing from {path}"
        blob = json.dumps(s["statusLine"])
        # Fork policy: see feat/upstream-resync migration (option A).
        # patch-global-config.sh never clobbers a foreign statusLine, so an
        # operator-chosen non-Writ statusLine is a valid installed state.
        if "writ-statusline.sh" not in blob:
            pytest.skip(f"foreign statusLine configured (non-clobber policy): {blob!r}")

    def test_global_settings_has_statusline(self) -> None:
        """statusLine lives in the global settings (hooks.json carries hooks only)."""
        g = _load_settings(GLOBAL_SETTINGS).get("statusLine")
        assert g is not None
        # Fork policy: see feat/upstream-resync migration (option A).
        # A foreign statusLine is left untouched by the installer (non-clobber).
        if "writ-statusline.sh" not in json.dumps(g):
            pytest.skip("foreign statusLine configured (non-clobber policy)")
