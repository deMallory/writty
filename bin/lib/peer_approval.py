"""Relayed gate approvals for auto-approve-gate.sh (stdlib-only).

David runs one orchestrator Claude Code session and several workers. A worker's gate can
be approved from the orchestrator: he types `approved <worker>` there, the orchestrator
forwards `approved` with SendMessage, and the worker's hook accepts it here. He stays the
approver, so nothing the orchestrator AGENT can write may stand in for his words.

THAT IS WHY THE HUMAN APPROVAL IS A RECORD, NOT A TRANSCRIPT READ. The orchestrator's
transcript sits outside every Writ guard, so an agent could append a fake human row to it.
The record is written by the orchestrator's own approval hook, which runs only on a real
prompt, into the session state directory both write gates refuse in every mode; and the
Bash gate already refuses any command naming the hook. `~/.claude/sessions/`, which maps
a pid to a session id and a name, is refused by the same gates for the same reason.

THE SIX CHECKS (plan.md numbers them), all required:
  1. the newest user row of the worker transcript is a peer row (Claude Code writes
     `origin`, including `verifiedPeerPid`, so the agent cannot choose the sender);
  2. `origin.name` is in WRIT_PEER_APPROVERS (empty: the feature is off);
  3. `origin.body` is an exact approval;
  4. the assistant turn before the peer row asked for an approval;
  5. the sender's relay record exists, is fresh and names this worker;
  6. that record is newer than check 4's request, so one human approval clears one gate.

Fail-closed like approval_evidence.py: an unreadable or garbled file is a refusal and
nothing here raises. Silent outcomes (feature off, a peer message that is not an
approval) write no audit row, so ordinary peer chat leaves no trace.
"""

import json
import os
import re
import sys
import time
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from approval_evidence import _assistant_text, has_request_marker  # noqa: E402
from approval_match import OVERRIDE_PHRASE, is_approval  # noqa: E402

ENVELOPE_HEADER = "Another Claude session sent a message:"
RECORD_TTL_SECONDS = 600
_TAIL_LINES = 400
_RELAY_PROMPT_RE = re.compile(r"approved ([a-z0-9][a-z0-9_.-]*)")
# A session id becomes part of a file name, so anything but the uuid alphabet is refused.
_SAFE_ID_RE = re.compile(r"[A-Za-z0-9-]+")


def _record_path(state_dir: str, session_id: str) -> str:
    return os.path.join(state_dir, f"writ-relay-{session_id}.json")


def record(state_dir: str, session_id: str, worker: str, now: float | None = None) -> None:
    """Write the orchestrator's record of a human `approved <worker>`. The newest wins."""
    with open(_record_path(state_dir, session_id), "w", encoding="utf-8") as fh:
        json.dump({"worker": worker, "ts": time.time() if now is None else now}, fh)


def relay_target(prompt: str) -> str:
    """The worker named by a whole prompt `approved <worker>`, or "".

    `approved anyway` keeps its override meaning, so it never names a worker.
    """
    text = (prompt or "").strip().lower()
    if text == OVERRIDE_PHRASE:
        return ""
    match = _RELAY_PROMPT_RE.fullmatch(text)
    return match.group(1) if match else ""


def envelope_body(prompt: str) -> str:
    """The message text inside a peer envelope prompt, "" when it is not one."""
    lines = (prompt or "").split("\n")
    if len(lines) < 2 or lines[0] != ENVELOPE_HEADER:
        return ""
    body = "\n".join(lines[2:])
    return body.split("</cross-session-message>", 1)[0].strip()


def _read_json(path: str):
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:
        return None


def _epoch(stamp) -> float | None:
    try:
        return datetime.fromisoformat(str(stamp).replace("Z", "+00:00")).timestamp()
    except Exception:
        return None


def _transcript_rows(path: str) -> list:
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            lines = fh.readlines()[-_TAIL_LINES:]
    except Exception:
        return []
    rows = []
    for line in lines:
        try:
            row = json.loads(line)
        except Exception:
            continue
        if isinstance(row, dict):
            rows.append(row)
    return rows


def _request_before(rows: list) -> dict | None:
    """The assistant text row immediately before the peer row, if it asked for approval.

    Same adjacency as approval_evidence.evidence_flags with no trailing user row allowed:
    a user row between the request and the peer row means the request was answered.
    """
    for row in reversed(rows):
        kind = row.get("type")
        if kind == "user":
            return None
        if kind == "assistant" and _assistant_text(row):
            return row if has_request_marker(_assistant_text(row)) else None
    return None


def _session_name(sessions_dir: str, session_id: str) -> str:
    try:
        names = os.listdir(sessions_dir)
    except Exception:
        return ""
    for name in names:
        if not name.endswith(".json"):
            continue
        doc = _read_json(os.path.join(sessions_dir, name))
        if isinstance(doc, dict) and doc.get("sessionId") == session_id:
            return str(doc.get("name") or "")
    return ""


def _verdict(verdict: str, check: int | None = None, reason: str = "") -> dict:
    return {"verdict": verdict, "check": check, "reason": reason}


def check(payload: dict, state_dir: str, approvers: list, sessions_dir: str,
          now: float | None = None) -> dict:
    """Decide one relayed approval. Never raises: an internal error is a refusal."""
    try:
        return _check(payload, state_dir, approvers, sessions_dir,
                      time.time() if now is None else now)
    except Exception as exc:
        return _verdict("refused", 0, f"internal error: {type(exc).__name__}")


def _check(payload, state_dir, approvers, sessions_dir, now):
    approvers = [a.strip() for a in approvers if a and a.strip()]
    if not approvers:
        return _verdict("silent")
    # Cheap silent exit for ordinary peer chat, read from the prompt itself, so a message
    # that is not an approval never reaches a check that could write a refusal row.
    if not is_approval(envelope_body(payload.get("prompt") or "").lower()):
        return _verdict("silent")

    rows = _transcript_rows(str(payload.get("transcript_path") or ""))
    users = [i for i, r in enumerate(rows) if r.get("type") == "user"]
    peer = rows[users[-1]] if users else None
    origin = peer.get("origin") if peer else None
    if not isinstance(origin, dict) or origin.get("kind") != "peer":
        return _verdict("refused", 1, "the newest user row in the transcript is not a peer message")

    sender = str(origin.get("name") or "")
    if sender not in approvers:
        return _verdict("refused", 2, f"sender '{sender}' is not in WRIT_PEER_APPROVERS")

    body = origin.get("body")
    if not isinstance(body, str) or not is_approval(body.strip().lower()):
        return _verdict("silent")

    request = _request_before(rows[:users[-1]])
    if request is None:
        return _verdict("refused", 4, "the assistant turn before the relay did not ask for approval")

    sender_doc = _read_json(os.path.join(sessions_dir, f"{origin.get('verifiedPeerPid')}.json"))
    sender_sid = sender_doc.get("sessionId") if isinstance(sender_doc, dict) else None
    if not isinstance(sender_sid, str) or not _SAFE_ID_RE.fullmatch(sender_sid):
        return _verdict("refused", 5, "no session file for the sender's verified pid")
    path = _record_path(state_dir, sender_sid)
    rec = _read_json(path)
    if not isinstance(rec, dict) or not isinstance(rec.get("ts"), (int, float)):
        return _verdict("refused", 5, f"no human approval recorded in '{sender}'")
    worker = _session_name(sessions_dir, str(payload.get("session_id") or ""))
    if not worker or rec.get("worker") != worker:
        return _verdict("refused", 5, f"the approval typed in '{sender}' names "
                                      f"'{rec.get('worker')}', not this session ('{worker}')")
    if now - rec["ts"] > RECORD_TTL_SECONDS:
        return _verdict("refused", 5, "the recorded approval is older than "
                                      f"{RECORD_TTL_SECONDS} seconds")

    asked_at = _epoch(request.get("timestamp"))
    if asked_at is None or rec["ts"] <= asked_at:
        return _verdict("refused", 6, "the recorded approval is older than this session's request")

    # Single use, the gate token's claim-by-rename: a second relay finds no record.
    os.replace(path, path + ".spent")
    return _verdict("pass", None, f"relayed by '{sender}' for '{worker}'")


def main(argv: list) -> int:
    """`record <state_dir>` or `check <state_dir>`, the hook payload on stdin.

    record prints the worker name when one was recorded. check prints the verdict, the
    check number, the reason, and the audit row's JSON, one per line.
    """
    try:
        payload = json.loads(sys.stdin.read())
    except Exception:
        payload = {}
    if not isinstance(payload, dict) or len(argv) != 2:
        return 1
    action, state_dir = argv
    if action == "record":
        worker = relay_target(payload.get("prompt") or "")
        sid = str(payload.get("session_id") or "")
        if worker and _SAFE_ID_RE.fullmatch(sid):
            record(state_dir, sid, worker)
            print(worker)
        return 0
    if action == "check":
        sessions_dir = os.path.join(os.path.expanduser("~"), ".claude", "sessions")
        approvers = os.environ.get("WRIT_PEER_APPROVERS", "").split(",")
        out = check(payload, state_dir, approvers, sessions_dir)
        print(out["verdict"])
        print("" if out["check"] is None else out["check"])
        print(out["reason"].replace("\n", " "))
        print(json.dumps({"check": out["check"], "reason": out["reason"]}))
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
