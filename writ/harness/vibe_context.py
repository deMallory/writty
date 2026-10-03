"""Writ's state file in a Vibe session's scratchpad.

Vibe has no prompt hook, so nothing hands the model Writ's state at the start of a turn.
The scratchpad is the one channel Vibe re-reads every user turn: it re-states
`$VIBE_HOME/logs/session/unified/<sid>/scratchpad/` to the model whenever the files change
(2.25.8, vibe/app_server/_unified_scratchpad.py). The bridge rewrites `0-writ.md` there
after each tool call, and vibe_user.py after each `!mistty` command.

Vibe reads the files in name order and cuts the block at 8,000 characters, so the name
sorts first and the text stays short. Vibe frames the block as the model's own saved data,
never instructions, so the rules go in the mistty home's AGENTS.md (vibe_install.py) and
this file carries only the state.

Stdlib-only and Python 3.9-safe, like the bridge.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
from collections.abc import Mapping
from typing import Any

from writ.shared.state_root import session_dir

WRIT_FILE = "0-writ.md"

_SAFE_ID = re.compile(r"^[A-Za-z0-9_-]{1,128}$")
_PHASE_TIMEOUT_S = 10

_HEADER = (
    "Writ state for this session. Writ rewrites this file after each tool call and each\n"
    "`!mistty` command. It is Writ's file: keep your own notes in other files."
)
_APPROVE = "The user approves with `!mistty approve`."
_MODES = "`!mistty mode work`, `debug`, `review`, `conversation` or `investigate`"


def scratchpad_dir(vibe_home: str, sid: str) -> str:
    """Vibe's scratchpad for one unified-harness session. Vibe's storage root is its
    session_logging.save_dir, `$VIBE_HOME/logs/session`."""
    return os.path.join(vibe_home, "logs", "session", "unified", sid, "scratchpad")


def read_session_cache(sid: str) -> dict:
    """The session's Writ cache, or {} when it is missing, unreadable or the id is unsafe."""
    if not _SAFE_ID.match(sid):
        return {}
    try:
        with open(os.path.join(session_dir(), f"writ-session-{sid}.json")) as handle:
            cache = json.load(handle)
    except (OSError, ValueError):
        return {}
    return cache if isinstance(cache, dict) else {}


def _plan_folder(project_root: str | None, sid: str) -> str:
    # writ.session.locators.plan_dir, which the bridge cannot import: that module needs
    # Python 3.10 and the shim runs under any python3. A test pins the two together.
    if not project_root or not _SAFE_ID.match(sid):
        return ""
    return os.path.join(project_root.rstrip("/") or "/", ".claude", "plans", sid)


def _next_step(mode: str | None, pending: str | None) -> str:
    if mode is None:
        return f"Writ refuses every write. Ask the user to set a mode: {_MODES}."
    if mode == "work":
        if pending == "phase-a":
            return ("Write plan.md in the plan folder in one write, with four sections: "
                    "## Files (one line per file: - `path` (change) -- reason, where change "
                    "is create, modify or delete), ## Analysis (the design and why), "
                    "## Rules Applied (only rule IDs Writ showed you this session, or exactly "
                    "\"No matching rules\"), ## Capabilities (one unchecked - [ ] line per "
                    "behavior). Writ checks plan.md each time you save it. Then write "
                    f"capabilities.md, present both, and stop. {_APPROVE}")
        if pending == "test-skeletons":
            return f"Write the test files the plan names, present them, and stop. {_APPROVE}"
        if pending:
            return f"`{pending}` is pending. {_APPROVE}"
        return ("Plan and tests are approved: implement the files the plan lists. "
                "A plan change needs the user's `!mistty replan`.")
    return {
        "debug": ("Source edits stay refused until debug.md records the root cause. "
                  "Writ's refusal names the file."),
        "review": "Evaluate code against Writ's rules and report findings per file.",
        "conversation": "No code changes are expected.",
    }.get(mode, "")


def render_state(phase: Mapping[str, Any], sid: str, project_root: str | None) -> str:
    """The state file's text, from what `writ-session.py current-phase <sid>` prints.

    The pending gate comes from that command, which derives it the way the approval path
    does, plan fingerprint included, so the bridge never re-derives it.
    """
    mode = phase.get("mode") or None
    lines = [_HEADER, "", f"Mode: {mode or 'none'}"]
    if mode == "work":
        gates = phase.get("gates_approved")
        approved = ", ".join(map(str, gates)) if isinstance(gates, list) else ""
        lines += [
            f"Phase: {phase.get('phase') or 'unclassified'}",
            f"Approved gates: {approved or 'none'}",
            f"Pending gate: {phase.get('next_gate') or 'none'}",
        ]
        folder = _plan_folder(project_root, sid)
        if folder:
            lines.append(f"Plan folder: {folder}/")
    step = _next_step(mode, phase.get("next_gate") or None)
    if step:
        lines.append(f"Next: {step}")
    return "\n".join(lines) + "\n"


def _current_phase(sid: str, plugin_root: str, base_env: Mapping[str, str] | None) -> dict | None:
    helper = os.path.join(plugin_root, "bin", "lib", "writ-session.py")
    try:
        proc = subprocess.run([sys.executable, helper, "current-phase", sid],
                              capture_output=True, text=True, timeout=_PHASE_TIMEOUT_S,
                              env=dict(os.environ if base_env is None else base_env))
    except (OSError, subprocess.SubprocessError):
        return None
    if proc.returncode != 0:
        return None
    try:
        phase = json.loads(proc.stdout)
    except ValueError:
        return None
    return phase if isinstance(phase, dict) else None


def _refresh(sid: str, plugin_root: str, vibe_home: str | None,
             base_env: Mapping[str, str] | None) -> bool:
    if not _SAFE_ID.match(sid):
        return False
    home = vibe_home or os.environ.get("VIBE_HOME") or os.path.expanduser("~/.vibe")
    directory = scratchpad_dir(home, sid)
    session = os.path.dirname(directory)
    # Vibe creates this folder for a unified-harness session. Without it the session is a
    # legacy one, which has no scratchpad, or the home is wrong; neither gets a folder.
    if not os.path.isdir(session):
        return False
    phase = _current_phase(sid, plugin_root, base_env)
    if phase is None:
        return False
    root = read_session_cache(sid).get("project_root")
    text = render_state(phase, sid, root if isinstance(root, str) else None)
    path = os.path.join(directory, WRIT_FILE)
    try:
        with open(path) as handle:
            if handle.read() == text:
                return True
    except OSError:
        pass
    os.makedirs(directory, mode=0o700, exist_ok=True)
    # The temp file sits in the session folder, not the scratchpad, so a turn that starts
    # mid-write never lists it.
    fd, tmp = tempfile.mkstemp(dir=session, prefix=".writ-state.")
    try:
        with os.fdopen(fd, "w") as handle:
            handle.write(text)
        os.replace(tmp, path)
    except BaseException:
        os.unlink(tmp)
        raise
    return True


def refresh(sid: str, *, plugin_root: str, vibe_home: str | None = None,
            base_env: Mapping[str, str] | None = None) -> bool:
    """Rewrite the session's state file. True when it now holds the current state.

    Never raises: the callers run it after their own work is done, and a failure here must
    cost them nothing. False leaves any older file as it was.
    """
    try:
        return _refresh(sid, plugin_root, vibe_home, base_env)
    except Exception:  # noqa: BLE001 -- best effort is the contract
        return False
