"""tests/test_peer_approval.py

Pins plan.md "relayed gate approvals from an orchestrator session". David types
`approved <worker>` in an orchestrator session; its own approval hook records that in Writ
gate state; the orchestrator forwards `approved` to the worker with SendMessage; the
worker's approval hook accepts it as an exact approval only when all six checks pass.

RED today: `bin/lib/peer_approval.py` does not exist, the hook has no relay branch, the
event `approval_relay_refused` is unregistered, and neither write gate covers
`~/.claude/sessions/`.

NOT STATED VERBATIM IN plan.md, committed to here as the narrowest reading of it:
  * `peer_approval.record(state_dir, session_id, worker, now=None)` writes
    `<state_dir>/writ-relay-<session_id>.json` as {"worker", "ts"}.
  * `peer_approval.check(payload, state_dir, approvers, sessions_dir, now=None)` returns
    {"verdict": "pass" | "silent" | "refused", "check": int | None, "reason": str}.
  * The worker's request timestamp is the ISO `timestamp` of the assistant row check 4
    found; a row with no timestamp fails check 6.

Isolation follows tests/test_approval_evidence.py: a uuid-suffixed session id per test,
HOME and WRIT_CACHE_DIR in tmp_path, WRIT_PORT a closed port, `_mint_cleanup` around every
hook run that can mint, and audit rows read back through `read_streams` against an
isolated WRIT_LOG_ROOT/WRIT_LOG_PROJECT.
"""

from __future__ import annotations

import contextlib
import importlib.util
import json
import os
import subprocess
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

import pytest

pytestmark = pytest.mark.no_friction_isolation

SKILL_ROOT = Path(__file__).resolve().parent.parent
HOOK_PATH = SKILL_ROOT / "hooks" / "scripts" / "auto-approve-gate.sh"
STATE_HOOK = SKILL_ROOT / "hooks" / "scripts" / "writ-state-write-gate.sh"
BASH_HOOK = SKILL_ROOT / "hooks" / "scripts" / "writ-bash-write-gate.sh"
PEER_APPROVAL_PY = SKILL_ROOT / "bin" / "lib" / "peer_approval.py"

sys.path.insert(0, str(SKILL_ROOT / "bin" / "lib"))

from tests.fixtures.session_state import (  # noqa: E402
    sandbox_cwd,  # noqa: F401, autouse cwd pin, imported per this repo's convention
    user_row,
    write_transcript_jsonl,
)

ORCH_PID = 73880
ORCH_NAME = "paulinator-monitoring_1"
WORKER_PID = 51234
WORKER_NAME = "worker_1"
ENVELOPE_HEADER = "Another Claude session sent a message:"


def _sid(label: str) -> str:
    return f"relay-{label}-{uuid.uuid4().hex[:8]}"


def _iso(epoch: float) -> str:
    return datetime.fromtimestamp(epoch, timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def _module():
    spec = importlib.util.spec_from_file_location("peer_approval", str(PEER_APPROVAL_PY))
    if spec is None or spec.loader is None or not PEER_APPROVAL_PY.exists():
        pytest.fail(f"bin/lib/peer_approval.py does not exist yet at {PEER_APPROVAL_PY}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _request_row(text: str, epoch: float) -> dict:
    return {"type": "assistant", "timestamp": _iso(epoch),
            "message": {"content": [{"type": "text", "text": text}]}}


def _peer_row(body, epoch: float, name: str = ORCH_NAME, pid: int = ORCH_PID) -> dict:
    origin = {"kind": "peer", "from": f"uds:/tmp/claude/cc-socks/{pid}.sock",
              "verifiedPeerPid": pid, "msg_id": uuid.uuid4().hex, "name": name,
              "fromMode": "prompting"}
    if body is not None:
        origin["body"] = body
    return {"type": "user", "timestamp": _iso(epoch), "isMeta": True,
            "promptSource": "system", "turnOrigin": "peer", "origin": origin,
            "message": {"role": "user", "content": _envelope(body or "", name, pid)}}


def _envelope(body: str, name: str = ORCH_NAME, pid: int = ORCH_PID) -> str:
    return (f"{ENVELOPE_HEADER}\n<cross-session-message from=\"uds:/tmp/claude/cc-socks/{pid}.sock\" "
            f"from-name=\"{name}\" from-mode=\"prompting\">\n{body}\n</cross-session-message>")


class World:
    """One orchestrator and one worker on disk: sessions files, a relay record, a
    worker transcript. Every piece can be removed or altered to fail one check."""

    def __init__(self, tmp_path: Path, label: str):
        self.tmp = tmp_path
        self.home = tmp_path / "home"
        self.sessions = self.home / ".claude" / "sessions"
        self.sessions.mkdir(parents=True)
        self.state = tmp_path / "cache"
        self.state.mkdir()
        self.worker_sid = _sid(f"{label}-worker")
        self.orch_sid = _sid(f"{label}-orch")
        self.now = time.time()
        self._sessions_file(WORKER_PID, self.worker_sid, WORKER_NAME)
        self._sessions_file(ORCH_PID, self.orch_sid, ORCH_NAME)

    def _sessions_file(self, pid: int, sid: str, name: str) -> None:
        (self.sessions / f"{pid}.json").write_text(json.dumps(
            {"pid": pid, "sessionId": sid, "name": name, "kind": "interactive"}))

    def record(self, worker: str = WORKER_NAME, ts: float | None = None) -> Path:
        path = self.state / f"writ-relay-{self.orch_sid}.json"
        path.write_text(json.dumps({"worker": worker, "ts": self.now - 5 if ts is None else ts}))
        return path

    def transcript(self, rows: list | None = None, body="approved") -> str:
        if rows is None:
            rows = [_request_row("Plan written. Say approved to proceed.", self.now - 30),
                    _peer_row(body, self.now - 1)]
        return write_transcript_jsonl(self.tmp, rows)

    def payload(self, transcript_path: str, body: str = "approved") -> dict:
        return {"session_id": self.worker_sid, "transcript_path": transcript_path,
                "prompt": _envelope(body)}

    def check(self, payload: dict, approvers=(ORCH_NAME,)) -> dict:
        return _module().check(payload, str(self.state), list(approvers), str(self.sessions),
                               now=self.now)


def _read_stream_rows(project: str, stream: str) -> list[dict]:
    from writ.shared.logging import read_streams

    return read_streams(project, [stream])


def _closed_port() -> int:
    import socket

    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]
    finally:
        s.close()


def _seed_pending_phase_a(cache_dir: Path, sid: str) -> None:
    (cache_dir / f"writ-session-{sid}.json").write_text(
        json.dumps({"mode": "work", "current_phase": "planning", "gates_approved": []}))


def _run_hook(payload: dict, world: World, project: str, approvers: str = ORCH_NAME):
    env = {**os.environ, "WRIT_CACHE_DIR": str(world.state), "WRIT_HOST": "127.0.0.1",
           "WRIT_PORT": str(_closed_port()), "HOME": str(world.home),
           "WRIT_PEER_APPROVERS": approvers,
           "WRIT_LOG_ROOT": str(world.tmp / "logs"), "WRIT_LOG_PROJECT": project}
    return subprocess.run(["bash", str(HOOK_PATH)], input=json.dumps(payload),
                          cwd=str(world.tmp), capture_output=True, text=True, env=env,
                          timeout=30)


@contextlib.contextmanager
def _mint_cleanup(sid: str):
    from writ.session.gate_token import gate_token_path

    try:
        yield
    finally:
        try:
            os.remove(gate_token_path(sid))
        except OSError:
            pass


@pytest.fixture(autouse=True)
def _no_leaked_gate_tokens():
    from tests._gate_token_leak import confined_leak_sweep, live_snapshot, warn_about_left_alone

    before = live_snapshot()
    yield
    removed, left_alone = confined_leak_sweep(before)
    warn_about_left_alone(left_alone)
    assert not removed, f"test leaked gate token file(s) (now removed): {sorted(removed)}"


# ---------------------------------------------------------------------------
# Orchestrator side: the hook records a human `approved <worker>`
# ---------------------------------------------------------------------------


class TestOrchestratorRecordsTheHumanApproval:
    def test_approved_with_a_worker_name_writes_a_record_and_mints_nothing(self, tmp_path):
        from writ.session.gate_token import gate_token_path

        world = World(tmp_path, "rec")
        with _mint_cleanup(world.orch_sid):
            r = _run_hook({"session_id": world.orch_sid, "prompt": "approved worker_1"},
                          world, "rec-project")
            assert not os.path.exists(gate_token_path(world.orch_sid)), r.stdout
        record = json.loads((world.state / f"writ-relay-{world.orch_sid}.json").read_text())
        assert record["worker"] == WORKER_NAME
        assert abs(record["ts"] - time.time()) < 60
        assert "worker_1" in r.stdout and "SendMessage" in r.stdout

    @pytest.mark.parametrize("prompt", ["approved anyway", "replan approved", "approved"])
    def test_existing_phrases_and_a_bare_approved_write_no_record(self, tmp_path, prompt):
        world = World(tmp_path, "norec")
        with _mint_cleanup(world.orch_sid):
            _run_hook({"session_id": world.orch_sid, "prompt": prompt}, world, "norec-project")
        assert not (world.state / f"writ-relay-{world.orch_sid}.json").exists()

    def test_approved_anyway_still_classifies_as_override(self):
        from approval_match import classify

        assert classify("approved anyway") == "override"

    def test_a_peer_envelope_never_writes_a_record(self, tmp_path):
        world = World(tmp_path, "envrec")
        with _mint_cleanup(world.orch_sid):
            _run_hook({"session_id": world.orch_sid, "prompt": _envelope("approved worker_1")},
                      world, "envrec-project")
        assert not (world.state / f"writ-relay-{world.orch_sid}.json").exists()

    def test_record_api_writes_worker_and_timestamp(self, tmp_path):
        mod = _module()
        mod.record(str(tmp_path), "orch-sid", WORKER_NAME, now=1000.0)
        assert json.loads((tmp_path / "writ-relay-orch-sid.json").read_text()) == {
            "worker": WORKER_NAME, "ts": 1000.0}


# ---------------------------------------------------------------------------
# Worker side: the happy path, through the real hook
# ---------------------------------------------------------------------------


class TestRelayedApprovalHappyPath:
    def test_all_checks_pass_in_the_module(self, tmp_path):
        world = World(tmp_path, "pass")
        world.record()
        out = world.check(world.payload(world.transcript()))
        assert out["verdict"] == "pass", out

    def test_the_hook_mints_a_phase_a_token_and_logs_a_relay_confirmation(self, tmp_path):
        from writ.session.gate_token import gate_token_path

        world = World(tmp_path, "hookpass")
        _seed_pending_phase_a(world.state, world.worker_sid)
        world.record()
        tp = world.transcript()
        with _mint_cleanup(world.worker_sid):
            r = _run_hook(world.payload(tp), world, "hookpass-project")
            assert os.path.exists(gate_token_path(world.worker_sid)), r.stdout
            lines = Path(gate_token_path(world.worker_sid)).read_text().split("\n")
            assert lines[1] == "phase-a", lines
        rows = _read_stream_rows("hookpass-project", "friction")
        matches = [x for x in rows if x.get("event") == "approval_pattern_match"]
        assert len(matches) == 1, rows
        assert matches[0]["confirmation_source"] == "relay", matches[0]

    def test_a_passed_relay_spends_the_record(self, tmp_path):
        world = World(tmp_path, "spend")
        record = world.record()
        payload = world.payload(world.transcript())
        assert world.check(payload)["verdict"] == "pass"
        assert not record.exists()
        second = world.check(payload)
        assert second["verdict"] == "refused" and second["check"] == 5, second


# ---------------------------------------------------------------------------
# Worker side: one test per check
# ---------------------------------------------------------------------------


class TestEachCheckRefuses:
    def test_feature_off_when_no_approvers_is_silent(self, tmp_path):
        world = World(tmp_path, "off")
        world.record()
        out = world.check(world.payload(world.transcript()), approvers=())
        assert out["verdict"] == "silent", out

    def test_feature_off_at_the_hook_mints_nothing_and_writes_no_row(self, tmp_path):
        from writ.session.gate_token import gate_token_path

        world = World(tmp_path, "offhook")
        _seed_pending_phase_a(world.state, world.worker_sid)
        world.record()
        with _mint_cleanup(world.worker_sid):
            _run_hook(world.payload(world.transcript()), world, "off-project", approvers="")
            assert not os.path.exists(gate_token_path(world.worker_sid))
        rows = _read_stream_rows("off-project", "audit")
        assert [x for x in rows if x.get("event") == "approval_relay_refused"] == []

    def test_check_1_newest_user_row_is_not_a_peer_row(self, tmp_path):
        world = World(tmp_path, "c1")
        world.record()
        tp = world.transcript([
            _request_row("Say approved to proceed.", world.now - 30),
            user_row(_envelope("approved")),
        ])
        out = world.check(world.payload(tp))
        assert out["verdict"] == "refused" and out["check"] == 1, out

    def test_check_2_sender_not_in_approvers(self, tmp_path):
        world = World(tmp_path, "c2")
        world.record()
        out = world.check(world.payload(world.transcript()), approvers=("someone-else",))
        assert out["verdict"] == "refused" and out["check"] == 2, out

    def test_check_3_a_non_approval_body_is_silent(self, tmp_path):
        world = World(tmp_path, "c3")
        world.record()
        tp = world.transcript(body="here is the status report")
        out = world.check(world.payload(tp, body="here is the status report"))
        assert out["verdict"] == "silent", out

    def test_check_3_a_missing_body_is_silent(self, tmp_path):
        world = World(tmp_path, "c3b")
        world.record()
        out = world.check(world.payload(world.transcript(body=None)))
        assert out["verdict"] == "silent", out

    def test_check_4_the_turn_before_did_not_ask(self, tmp_path):
        world = World(tmp_path, "c4")
        world.record()
        tp = world.transcript([
            _request_row("I refactored the parser.", world.now - 30),
            _peer_row("approved", world.now - 1),
        ])
        out = world.check(world.payload(tp))
        assert out["verdict"] == "refused" and out["check"] == 4, out

    def test_check_5_no_sender_sessions_file(self, tmp_path):
        world = World(tmp_path, "c5a")
        world.record()
        (world.sessions / f"{ORCH_PID}.json").unlink()
        out = world.check(world.payload(world.transcript()))
        assert out["verdict"] == "refused" and out["check"] == 5, out

    def test_check_5_no_record(self, tmp_path):
        world = World(tmp_path, "c5b")
        out = world.check(world.payload(world.transcript()))
        assert out["verdict"] == "refused" and out["check"] == 5, out

    def test_check_5_record_names_another_worker(self, tmp_path):
        world = World(tmp_path, "c5c")
        world.record(worker="worker_2")
        out = world.check(world.payload(world.transcript()))
        assert out["verdict"] == "refused" and out["check"] == 5, out

    def test_check_5_record_older_than_600_seconds(self, tmp_path):
        world = World(tmp_path, "c5d")
        world.record(ts=world.now - 601)
        tp = world.transcript([
            _request_row("Say approved to proceed.", world.now - 700),
            _peer_row("approved", world.now - 1),
        ])
        out = world.check(world.payload(tp))
        assert out["verdict"] == "refused" and out["check"] == 5, out

    def test_check_6_record_older_than_the_request(self, tmp_path):
        world = World(tmp_path, "c6")
        world.record(ts=world.now - 60)
        tp = world.transcript([
            _request_row("Say approved to proceed.", world.now - 30),
            _peer_row("approved", world.now - 1),
        ])
        out = world.check(world.payload(tp))
        assert out["verdict"] == "refused" and out["check"] == 6, out

    def test_check_6_request_row_without_timestamp(self, tmp_path):
        world = World(tmp_path, "c6b")
        world.record()
        row = _request_row("Say approved to proceed.", world.now - 30)
        del row["timestamp"]
        tp = world.transcript([row, _peer_row("approved", world.now - 1)])
        out = world.check(world.payload(tp))
        assert out["verdict"] == "refused" and out["check"] == 6, out


class TestRefusalAtTheHook:
    def test_a_refusal_mints_nothing_and_writes_one_audit_row_naming_the_check(self, tmp_path):
        from writ.session.gate_token import gate_token_path

        world = World(tmp_path, "hookrefuse")
        _seed_pending_phase_a(world.state, world.worker_sid)
        world.record(worker="worker_2")
        with _mint_cleanup(world.worker_sid):
            r = _run_hook(world.payload(world.transcript()), world, "refuse-project")
            assert not os.path.exists(gate_token_path(world.worker_sid)), r.stdout
        rows = _read_stream_rows("refuse-project", "audit")
        matches = [x for x in rows if x.get("event") == "approval_relay_refused"]
        assert len(matches) == 1, rows
        assert matches[0]["check"] == 5, matches[0]
        after = json.loads((world.state / f"writ-session-{world.worker_sid}.json").read_text())
        assert after.get("gates_approved") == []


class TestFailClosed:
    def test_missing_transcript_refuses_without_raising(self, tmp_path):
        world = World(tmp_path, "fc1")
        world.record()
        out = world.check(world.payload(str(tmp_path / "nope.jsonl")))
        assert out["verdict"] == "refused" and out["check"] == 1, out

    def test_garbled_sessions_file_refuses_without_raising(self, tmp_path):
        world = World(tmp_path, "fc2")
        world.record()
        (world.sessions / f"{ORCH_PID}.json").write_text("{not json")
        out = world.check(world.payload(world.transcript()))
        assert out["verdict"] == "refused" and out["check"] == 5, out

    def test_garbled_record_refuses_without_raising(self, tmp_path):
        world = World(tmp_path, "fc3")
        (world.state / f"writ-relay-{world.orch_sid}.json").write_text("{not json")
        out = world.check(world.payload(world.transcript()))
        assert out["verdict"] == "refused" and out["check"] == 5, out


# ---------------------------------------------------------------------------
# The guard on ~/.claude/sessions/
# ---------------------------------------------------------------------------


def _gate_env(tmp_path: Path) -> dict:
    env = {k: v for k, v in os.environ.items() if k != "WRIT_CACHE_DIR"}
    env.update({"HOME": str(tmp_path / "home"), "XDG_STATE_HOME": str(tmp_path / "xdg"),
                "WRIT_LOG_ROOT": str(tmp_path / "logs"),
                "WRIT_FRICTION_LOG": str(tmp_path / "friction.log"),
                "WRIT_PORT": str(_closed_port()), "WRIT_HOST": "localhost",
                "WRIT_NO_AUTOSTART": "1"})
    return env


def _gate(hook: Path, tool: str, tool_input: dict, tmp_path: Path) -> tuple[str, str]:
    envelope = {"session_id": "relay-guard", "hook_event_name": "PreToolUse",
                "tool_name": tool, "tool_input": tool_input}
    r = subprocess.run(["bash", str(hook)], input=json.dumps(envelope), env=_gate_env(tmp_path),
                       capture_output=True, text=True, timeout=60, cwd=str(tmp_path))
    assert r.returncode == 0, r.stderr
    for line in r.stdout.splitlines():
        try:
            out = json.loads(line).get("hookSpecificOutput") or {}
        except ValueError:
            continue
        if out.get("permissionDecision"):
            return out["permissionDecision"], out.get("permissionDecisionReason", "")
    return "allow", ""


class TestSessionsDirectoryGuard:
    @pytest.mark.parametrize("tool", ["Write", "Edit"])
    def test_write_and_edit_into_claude_sessions_are_refused(self, tmp_path, tool):
        target = tmp_path / "home" / ".claude" / "sessions" / "51234.json"
        decision, why = _gate(STATE_HOOK, tool, {"file_path": str(target), "content": "x",
                                                 "old_string": "a", "new_string": "b"}, tmp_path)
        assert decision == "deny" and "ENF-GATE-STATE" in why

    def test_a_sibling_claude_directory_is_not_refused(self, tmp_path):
        target = tmp_path / "home" / ".claude" / "notes" / "x.md"
        assert _gate(STATE_HOOK, "Write", {"file_path": str(target), "content": "x"},
                     tmp_path)[0] == "allow"

    def test_a_bash_write_into_claude_sessions_is_refused(self, tmp_path):
        decision, why = _gate(BASH_HOOK, "Bash",
                              {"command": "echo '{}' > ~/.claude/sessions/51234.json"}, tmp_path)
        assert decision == "deny" and "ENF-GATE-STATE" in why

    def test_a_plain_cat_of_claude_sessions_is_allowed(self, tmp_path):
        assert _gate(BASH_HOOK, "Bash", {"command": "cat ~/.claude/sessions/51234.json"},
                     tmp_path)[0] == "allow"
