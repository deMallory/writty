"""tests/test_peer_prompt_trace.py

Pins plan.md "trace every unrelayed peer approval". The first live relayed approval
failed and left no row anywhere: a peer prompt that does not advance a gate exits
silently for four different reasons, and nothing tells them apart. Every such prompt now
writes one `peer_prompt_unrelayed` friction row naming why.

RED today: `check()` returns no `why`, `trace_row` does not exist, the hook runs the
check only on an exact first-line match and logs nothing on a silent verdict, and the
event is unregistered.

NOT STATED VERBATIM IN plan.md, committed to here as the narrowest reading of it:
  * `check()`'s result gains `why`: "approvers_empty", "header_mismatch" or
    "not_an_approval" on a silent verdict, None otherwise. Approvers are tested first,
    then the header, then the body.
  * `peer_approval.trace_row(payload, approvers, out)` returns {"header_matched",
    "first_line", "approvers_set", "verdict", "check", "why"}; `first_line` is the
    `repr()` of the prompt's first line, cut to 120 characters.
  * The hook's friction row carries those same keys; the no-session-id exit writes
    why "no_session_id" when the payload is a peer prompt.

Fixtures come from tests/test_peer_approval.py, so both suites build one world.
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest

from tests.fixtures.session_state import sandbox_cwd  # noqa: F401
from tests.test_peer_approval import (  # noqa: F401
    ENVELOPE_HEADER,
    HOOK_PATH,
    ORCH_NAME,
    World,
    _closed_port,
    _envelope,
    _mint_cleanup,
    _module,
    _no_leaked_gate_tokens,
    _read_stream_rows,
    _seed_pending_phase_a,
)

pytestmark = pytest.mark.no_friction_isolation

EVENT = "peer_prompt_unrelayed"
TRACE_KEYS = {"header_matched", "first_line", "approvers_set", "verdict", "check", "why"}


def _run(payload: dict, world: World, project: str, approvers: str = ORCH_NAME,
         cwd: Path | None = None):
    env = {**os.environ, "WRIT_CACHE_DIR": str(world.state), "WRIT_HOST": "127.0.0.1",
           "WRIT_PORT": str(_closed_port()), "HOME": str(world.home),
           "WRIT_PEER_APPROVERS": approvers,
           "WRIT_LOG_ROOT": str(world.tmp / "logs"), "WRIT_LOG_PROJECT": project}
    return subprocess.run(["bash", str(HOOK_PATH)], input=json.dumps(payload),
                          cwd=str(cwd or world.tmp), capture_output=True, text=True,
                          env=env, timeout=30)


def _trace_rows(project: str) -> list[dict]:
    return [r for r in _read_stream_rows(project, "friction") if r.get("event") == EVENT]


def _renamed_header_prompt(body: str = "approved") -> str:
    return _envelope(body).replace(ENVELOPE_HEADER, "Another Claude session sent you a message:", 1)


# ---------------------------------------------------------------------------
# The module names why a verdict was silent
# ---------------------------------------------------------------------------


class TestCheckNamesWhy:
    def test_approvers_empty(self, tmp_path):
        world = World(tmp_path, "why-off")
        world.record()
        out = world.check(world.payload(world.transcript()), approvers=())
        assert out["verdict"] == "silent" and out["why"] == "approvers_empty", out

    def test_not_an_approval(self, tmp_path):
        world = World(tmp_path, "why-chat")
        tp = world.transcript(body="how is the build going?")
        out = world.check(world.payload(tp, body="how is the build going?"))
        assert out["verdict"] == "silent" and out["why"] == "not_an_approval", out

    def test_header_mismatch(self, tmp_path):
        world = World(tmp_path, "why-header")
        world.record()
        payload = {**world.payload(world.transcript()), "prompt": _renamed_header_prompt()}
        out = world.check(payload)
        assert out["verdict"] == "silent" and out["why"] == "header_mismatch", out

    def test_a_pass_and_a_refusal_carry_no_why(self, tmp_path):
        world = World(tmp_path, "why-none")
        payload = world.payload(world.transcript())
        refused = world.check(payload)  # no record yet: check 5
        assert refused["verdict"] == "refused" and refused["why"] is None, refused
        world.record()
        passed = world.check(payload)
        assert passed["verdict"] == "pass" and passed["why"] is None, passed


class TestTraceRow:
    def test_has_every_key(self, tmp_path):
        world = World(tmp_path, "row-keys")
        payload = world.payload(world.transcript())
        out = world.check(payload, approvers=())
        row = _module().trace_row(payload, [], out)
        assert set(row) == TRACE_KEYS, row
        assert row["header_matched"] is True and row["approvers_set"] is False, row

    def test_first_line_is_a_repr_cut_at_120(self, tmp_path):
        world = World(tmp_path, "row-repr")
        long_first = "X" * 300 + "\t"
        payload = {**world.payload(world.transcript()),
                   "prompt": long_first + "\n<cross-session-message>approved</cross-session-message>"}
        out = world.check(payload)
        row = _module().trace_row(payload, [ORCH_NAME], out)
        assert row["header_matched"] is False, row
        assert len(row["first_line"]) <= 120, row
        assert row["first_line"].startswith("'XXX"), row


# ---------------------------------------------------------------------------
# The hook writes one row per silent outcome
# ---------------------------------------------------------------------------


class TestHookWritesOneRowPerSilentOutcome:
    def test_approvers_empty(self, tmp_path):
        world = World(tmp_path, "hk-off")
        _seed_pending_phase_a(world.state, world.worker_sid)
        world.record()
        with _mint_cleanup(world.worker_sid):
            _run(world.payload(world.transcript()), world, "hk-off-project", approvers="")
        rows = _trace_rows("hk-off-project")
        assert len(rows) == 1 and rows[0]["why"] == "approvers_empty", rows
        assert TRACE_KEYS <= set(rows[0]), rows[0]

    def test_not_an_approval(self, tmp_path):
        world = World(tmp_path, "hk-chat")
        body = "how is the build going?"
        with _mint_cleanup(world.worker_sid):
            _run(world.payload(world.transcript(body=body), body=body), world, "hk-chat-project")
        rows = _trace_rows("hk-chat-project")
        assert len(rows) == 1 and rows[0]["why"] == "not_an_approval", rows

    def test_header_mismatch_names_the_first_line(self, tmp_path):
        world = World(tmp_path, "hk-header")
        _seed_pending_phase_a(world.state, world.worker_sid)
        world.record()
        payload = {**world.payload(world.transcript()), "prompt": _renamed_header_prompt()}
        with _mint_cleanup(world.worker_sid):
            _run(payload, world, "hk-header-project")
        rows = _trace_rows("hk-header-project")
        assert len(rows) == 1 and rows[0]["why"] == "header_mismatch", rows
        assert "sent you a message" in rows[0]["first_line"], rows[0]
        assert rows[0]["header_matched"] is False, rows[0]

    def test_no_session_id(self, tmp_path):
        world = World(tmp_path, "hk-nosid")
        payload = world.payload(world.transcript())
        payload.pop("session_id")
        _run(payload, world, "hk-nosid-project")
        rows = _trace_rows("hk-nosid-project")
        assert len(rows) == 1 and rows[0]["why"] == "no_session_id", rows


class TestNoTraceWhereNothingWasMissed:
    def test_an_ordinary_prompt_writes_no_trace_row(self, tmp_path):
        world = World(tmp_path, "hk-plain")
        with _mint_cleanup(world.worker_sid):
            _run({"session_id": world.worker_sid, "prompt": "run the tests please"},
                 world, "hk-plain-project")
        assert _trace_rows("hk-plain-project") == []

    def test_detection_is_a_bash_case_before_any_process(self):
        """The cheap filter must stay a shell `case` on the raw payload: this hook runs
        on every prompt, and a python spawn costs about 10ms per turn."""
        src = HOOK_PATH.read_text()
        assert 'case "$STDIN_JSON" in' in src
        assert "*cross-session-message*" in src

    def test_a_refusal_writes_its_audit_row_and_no_trace_row(self, tmp_path):
        world = World(tmp_path, "hk-refused")
        _seed_pending_phase_a(world.state, world.worker_sid)
        with _mint_cleanup(world.worker_sid):  # no record: refused at check 5
            _run(world.payload(world.transcript()), world, "hk-refused-project")
        audit = [r for r in _read_stream_rows("hk-refused-project", "audit")
                 if r.get("event") == "approval_relay_refused"]
        assert len(audit) == 1, audit
        assert _trace_rows("hk-refused-project") == []


# ---------------------------------------------------------------------------
# The live failure's shape: a worker whose cwd is a git worktree
# ---------------------------------------------------------------------------


def _git_worktree(tmp_path: Path) -> Path:
    main = tmp_path / "repo"
    main.mkdir()
    git = ["git", "-c", "user.name=t", "-c", "user.email=t@t", "-c", "commit.gpgsign=false"]
    subprocess.run([*git, "init", "-q", str(main)], check=True)
    (main / "README").write_text("x\n")
    subprocess.run([*git, "-C", str(main), "add", "README"], check=True)
    subprocess.run([*git, "-C", str(main), "commit", "-q", "-m", "init"], check=True)
    wt = main / ".claude" / "worktrees" / "plntr-44"
    subprocess.run([*git, "-C", str(main), "worktree", "add", "-q", str(wt)], check=True)
    return wt


class TestRelayFromAWorktreeCwd:
    def test_all_checks_pass_and_the_gate_advances_with_no_trace_row(self, tmp_path):
        from writ.session.gate_token import gate_token_path

        world = World(tmp_path, "wt-pass")
        wt = _git_worktree(tmp_path)
        _seed_pending_phase_a(world.state, world.worker_sid)
        world.record()
        with _mint_cleanup(world.worker_sid):
            r = _run(world.payload(world.transcript()), world, "wt-pass-project", cwd=wt)
            assert os.path.exists(gate_token_path(world.worker_sid)), r.stdout
        assert _trace_rows("wt-pass-project") == []
