"""Run Writ's Claude hook scripts for Mistral Vibe tool calls.

Vibe calls `bin/writ-vibe-hook pre_tool|post_tool` with its own envelope on stdin. This
module translates that envelope to the Claude envelope the scripts in hooks/hooks.json
read, runs the scripts that match, and translates their answers back to Vibe's output.
Every verdict still comes from the scripts, except two Vibe has and Claude lacks: the
user's own `!mistty` commands and typed input to a running process (`process.write`).

Stdlib-only, like envelope.py, so the shim runs under any python3. writ.shared.state_root
imports only os.

Vibe's contract (2.25.8, mistralai_vibe_local_harness/vibe/_foreign_hooks.py): exit 0 and
JSON on stdout. `{"decision": "deny", "reason": ...}` blocks a pre_tool call, and in
post_tool replaces the result the model sees. `hook_specific_output.tool_input` rewrites
pre_tool arguments. `hook_specific_output.additional_context` is read in post_tool only.
"""

from __future__ import annotations

import copy
import fcntl
import glob
import json
import os
import re
import signal
import subprocess
import sys
import tempfile
from collections.abc import Callable, Mapping
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Any

from writ.shared.state_root import session_dir

PRE = "pre_tool"
POST = "post_tool"

DEFAULT_SCRIPT_TIMEOUT_S = 30.0

PLUGIN_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Unified-harness names are qualified, --legacy-harness names are bare. process.start runs
# an arbitrary shell command, so it is gated as Bash.
_TOOLS: dict[str, str] = {
    "file_system.write_file": "Write",
    "write_file": "Write",
    "file_system.search_replace": "Edit",
    "edit": "Edit",
    "file_system.read_file": "Read",
    "read_file": "Read",
    "file_system.bash": "Bash",
    "bash": "Bash",
    "process.start": "Bash",
    "grep": "Grep",
}

# The user's own Writ commands (vibe_user.py) in a model shell call. Vibe gives a `!`
# command and a model shell call the same environment and the same ancestry (both are
# new-session children of the Vibe process), so the command text is the only signal, and
# a command assembled at run time slips past. Case-insensitive because macOS volumes are.
_USER_ONLY = re.compile(r"\bmistty\s+(?:approve|replan|grant|mode)\b|\bvibe_user\b",
                        re.IGNORECASE)
_USER_ONLY_REASON = (
    "`mistty approve`, `replan`, `grant` and `mode` are the user's own Writ commands, so "
    "Writ refuses them to the model. Ask the user to type the one you need themselves, "
    "with the `!` prefix: `!mistty approve`, `!mistty replan`, `!mistty grant manual-test` "
    "or `!mistty mode <mode>`."
)

# process.write types into a process that process.start began. Writ's shell checks read
# shell syntax, so code typed into a REPL, or a command split across writes, passes them.
# The bridge decides it itself, mirroring _can_write_check (writ/session/gates.py): no
# mode, work and debug gate writes, every other mode allows them. Safe keys stop or answer
# a process but cannot type a command; up and down replay shell history, tab completes one.
_PROCESS_WRITE = "process.write"
_SAFE_KEYS = frozenset({"ctrl_c", "ctrl_d", "ctrl_z", "esc", "enter"})
_GATED_MODES = frozenset({"work", "debug"})
# Tools the bridge decides without a Writ script. The installer matches them too.
_BRIDGE_TOOLS = (_PROCESS_WRITE,)

_NO_SESSION_REASON = (
    "Writ could not tell which Vibe session made this call, so it is denied (fail-closed). "
    "Check that this Vibe session's lock is in $VIBE_HOME/logs/session/active."
)

_SAFE_ID = re.compile(r"^[A-Za-z0-9_-]{1,128}$")
_SCRIPT_NAME = re.compile(r"([\w.-]+)\.(?:sh|py)\b")
_MAX_WALK = 30
_MISSING = object()


class _Unmappable(Exception):
    """A script rewrite the bridge cannot express in Vibe's arguments."""


# --------------------------------------------------------------------------- #
# Envelope translation
# --------------------------------------------------------------------------- #
def _as_dict(value: object) -> dict:
    return value if isinstance(value, dict) else {}


def _abs(path: object, cwd: str) -> str:
    # Claude always sends absolute paths and the gates compare them; Vibe sends what the
    # model typed.
    text = str(path or "")
    if not text:
        return ""
    if not os.path.isabs(text) and cwd:
        text = os.path.join(cwd, text)
    return os.path.normpath(text)


def _path_key(args: Mapping) -> str:
    return "file_path" if "file_path" in args else "path"


def _claude_inputs(tool: str, args: dict, cwd: str) -> list[dict]:
    file_path = _abs(args.get(_path_key(args)), cwd)
    if tool == "Write":
        return [{"file_path": file_path, "content": str(args.get("content") or "")}]
    if tool == "Edit":
        blocks = args.get("content")
        if isinstance(blocks, list):
            # One Edit per block: Writ has no MultiEdit matcher, so a MultiEdit envelope
            # would slip past every write gate.
            return [
                {
                    "file_path": file_path,
                    "old_string": str(block.get("old_str") or ""),
                    "new_string": str(block.get("new_str") or ""),
                    "replace_all": bool(block.get("replace_all", False)),
                }
                for block in ([b for b in blocks if isinstance(b, dict)] or [{}])
            ]
        return [{
            "file_path": file_path,
            "old_string": str(args.get("old_string") or ""),
            "new_string": str(args.get("new_string") or ""),
            "replace_all": bool(args.get("replace_all", False)),
        }]
    if tool == "Read":
        read = {"file_path": file_path}
        for key in ("offset", "limit"):
            if key in args:
                read[key] = args[key]
        return [read]
    if tool == "Grep":
        grep = {"pattern": str(args.get("pattern") or "")}
        if "path" in args:
            grep["path"] = _abs(args["path"], cwd)
        return [grep]
    return [{"command": str(args.get("command") or "")}]


def _claude_event(event: str, envelope: Mapping) -> str:
    if event == PRE:
        return "PreToolUse"
    return "PostToolUseFailure" if envelope.get("tool_status") == "failure" else "PostToolUse"


def to_claude(envelope: Mapping, event: str, session_id: str) -> list[dict]:
    """The Claude envelopes for one Vibe envelope, or [] when Writ has no hooks for the tool.

    A multi-block search_replace yields one Edit per block in pre_tool and only the first
    in post_tool, where the scripts look at the file rather than the strings.
    """
    tool = _TOOLS.get(str(envelope.get("tool_name") or ""))
    if tool is None:
        return []
    cwd = str(envelope.get("cwd") or "")
    inputs = _claude_inputs(tool, _as_dict(envelope.get("tool_input")), cwd)
    if event == POST:
        inputs = inputs[:1]
    claude_event = _claude_event(event, envelope)
    base: dict[str, Any] = {
        "session_id": session_id,
        # Vibe's transcript is not Claude JSONL, so a script parsing it would misread it.
        "transcript_path": "",
        "cwd": cwd,
        "hook_event_name": claude_event,
        "tool_name": tool,
        "tool_use_id": str(envelope.get("tool_call_id") or ""),
    }
    result = []
    for tool_input in inputs:
        claude = {**base, "tool_input": tool_input}
        if claude_event == "PostToolUseFailure":
            claude["error"] = str(envelope.get("tool_error") or "")
        elif claude_event == "PostToolUse":
            claude["tool_response"] = envelope.get("tool_output")
            claude["tool_output"] = str(envelope.get("tool_output_text") or "")
        result.append(claude)
    return result


# --------------------------------------------------------------------------- #
# Session id
# --------------------------------------------------------------------------- #
def _ps_parent(pid: int) -> int | None:
    try:
        out = subprocess.run(["ps", "-o", "ppid=", "-p", str(pid)],
                             capture_output=True, text=True, timeout=5).stdout.strip()
        return int(out) if out else None
    except (OSError, ValueError, subprocess.SubprocessError):
        return None


def _lock_owners(active: str) -> dict[int, list[str]]:
    owners: dict[int, list[str]] = {}
    for path in sorted(glob.glob(os.path.join(active, "*.lock.json"))):
        try:
            with open(path) as handle:
                pid = json.load(handle).get("process_id")
        except (OSError, ValueError, AttributeError):
            continue
        if isinstance(pid, int):
            owners.setdefault(pid, []).append(os.path.basename(path)[: -len(".lock.json")])
    return owners


def _is_live(active: str, sid: str) -> bool:
    # Vibe's own session_is_live probe: a live session holds the flock on <sid>.lock.
    try:
        fd = os.open(os.path.join(active, f"{sid}.lock"), os.O_RDONLY)
    except OSError:
        return False
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        return True
    except OSError:
        return False
    else:
        fcntl.flock(fd, fcntl.LOCK_UN)
        return False
    finally:
        os.close(fd)


def resolve_session_id(
    envelope: Mapping,
    *,
    vibe_home: str | None = None,
    start_pid: int | None = None,
    parent_of: Callable[[int], int | None] | None = None,
) -> str | None:
    """The Vibe session that made this call, or None when it cannot be told apart.

    The legacy harness puts `session_id` in the payload. The unified harness does not, so
    walk up the process tree to the first pid that owns a lock in
    $VIBE_HOME/logs/session/active. A spawned subagent's `child-*` lock carries the
    parent's pid, and a lock nobody holds is a dead session, so both are dropped.
    """
    sid = envelope.get("session_id")
    if isinstance(sid, str) and sid:
        return sid
    home = vibe_home or os.environ.get("VIBE_HOME") or os.path.expanduser("~/.vibe")
    active = os.path.join(home, "logs", "session", "active")
    owners = _lock_owners(active)
    if not owners:
        return None
    step = parent_of or _ps_parent
    pid: int | None = os.getppid() if start_pid is None else start_pid
    for _ in range(_MAX_WALK):
        if pid is None or pid <= 1:
            return None
        if pid in owners:
            live = [s for s in owners[pid]
                    if not s.startswith("child-") and _is_live(active, s)]
            return live[0] if len(live) == 1 else None
        pid = step(pid)
    return None


# --------------------------------------------------------------------------- #
# Running scripts
# --------------------------------------------------------------------------- #
def select_commands(config: Mapping, claude_event: str, tool_name: str) -> list[tuple[str, float]]:
    """(command, timeout) for every hooks.json hook whose matcher fullmatches the tool."""
    events = _as_dict(config.get("hooks"))
    selected = []
    for group in events.get(claude_event) or []:
        if not isinstance(group, dict):
            continue
        matcher = str(group.get("matcher") or "")
        if matcher not in ("", "*") and not re.fullmatch(matcher, tool_name):
            continue
        for hook in group.get("hooks") or []:
            if isinstance(hook, dict) and hook.get("command") and hook.get("type", "command") == "command":
                selected.append((str(hook["command"]), float(hook.get("timeout") or DEFAULT_SCRIPT_TIMEOUT_S)))
    return selected


@dataclass
class _Run:
    name: str
    returncode: int | None = None
    stdout: str = ""
    stderr: str = ""
    error: str = ""


def _script_name(command: str) -> str:
    found = _SCRIPT_NAME.findall(command)
    return found[-1] if found else command[:60]


def _run(command: str, stdin: str, *, cwd: str, env: Mapping[str, str], timeout: float) -> _Run:
    name = _script_name(command)
    try:
        # A new session puts the script and its children in one process group, so a
        # timeout kills them all instead of waiting on a grandchild that holds the pipe.
        proc = subprocess.Popen(
            ["bash", "-c", command], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, cwd=cwd or None, env=dict(env), text=True,
            encoding="utf-8", errors="replace", start_new_session=True,
        )
    except OSError as exc:
        return _Run(name, error=f"failed to start ({exc})")
    try:
        stdout, stderr = proc.communicate(stdin, timeout=timeout)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except OSError:
            pass
        try:
            proc.communicate(timeout=2)
        except subprocess.TimeoutExpired:
            pass
        return _Run(name, error=f"timed out after {timeout:g}s")
    return _Run(name, proc.returncode, stdout, stderr)


def _run_all(jobs: list[tuple[dict, str, float]], *, plugin_root: str,
             base_env: Mapping[str, str] | None) -> list[_Run]:
    env = dict(os.environ if base_env is None else base_env)
    env["CLAUDE_PLUGIN_ROOT"] = plugin_root
    env["WRIT_STRICT"] = "1"
    if not jobs:
        return []
    with ThreadPoolExecutor(max_workers=len(jobs)) as pool:
        futures = [
            pool.submit(_run, command, json.dumps(claude), cwd=str(claude.get("cwd") or ""),
                        env=env, timeout=timeout)
            for claude, command, timeout in jobs
        ]
        return [future.result() for future in futures]


# --------------------------------------------------------------------------- #
# Reading answers
# --------------------------------------------------------------------------- #
@dataclass
class _Answer:
    error: str = ""
    deny: str = ""
    block: str = ""
    context: str = ""
    updated_input: dict | None = None
    updated_output: Any = _MISSING


def _read(run: _Run) -> _Answer:
    """One script's answer, by Claude's rules for tool events."""
    if run.error:
        return _Answer(error=f"{run.name} {run.error}")
    if run.returncode == 2:
        return _Answer(block=run.stderr.strip() or f"{run.name} blocked the call")
    if run.returncode != 0:
        detail = run.stderr.strip().splitlines()[-1:] if run.stderr.strip() else []
        return _Answer(error=f"{run.name} exited {run.returncode}"
                       + (f" ({detail[0]})" if detail else ""))
    try:
        parsed = json.loads(run.stdout) if run.stdout.strip() else None
    except ValueError:
        parsed = None
    if not isinstance(parsed, dict):
        return _Answer()
    hso = _as_dict(parsed.get("hookSpecificOutput"))
    answer = _Answer()
    permission = hso.get("permissionDecision")
    reason = str(hso.get("permissionDecisionReason") or parsed.get("reason") or "")
    if permission == "deny":
        answer.deny = reason or f"{run.name} denied the call"
    elif permission == "ask":
        answer.deny = ("Writ asked for your confirmation, but Vibe hooks cannot ask, "
                       f"so this call is denied. {reason}").strip()
    if parsed.get("decision") in ("block", "deny"):
        answer.block = str(parsed.get("reason") or f"{run.name} blocked the call")
    elif parsed.get("continue") is False:
        answer.block = str(parsed.get("stopReason") or f"{run.name} stopped the call")
    if isinstance(hso.get("updatedInput"), dict):
        answer.updated_input = hso["updatedInput"]
    if isinstance(hso.get("additionalContext"), str):
        answer.context = hso["additionalContext"]
    if "updatedToolOutput" in hso:
        answer.updated_output = hso["updatedToolOutput"]
    return answer


def _deny(reason: str) -> str:
    return json.dumps({"decision": "deny", "reason": reason})


# --------------------------------------------------------------------------- #
# Rewrites back to Vibe arguments
# --------------------------------------------------------------------------- #
def _to_vibe_args(envelope: Mapping, claude_inputs: list[dict],
                  rewrites: list[dict]) -> dict | None:
    """The original Vibe arguments with the rewritten keys applied, or None if unchanged."""
    original = claude_inputs[0]
    merged = dict(original)
    for rewrite in rewrites:
        for key, value in rewrite.items():
            if original.get(key, _MISSING) != value:
                merged[key] = value
    changed = {k: v for k, v in merged.items() if original.get(k, _MISSING) != v}
    if not changed:
        return None
    if len(claude_inputs) > 1:
        raise _Unmappable("a Writ hook rewrote one block of a multi-block search_replace")
    args = copy.deepcopy(_as_dict(envelope.get("tool_input")))
    tool = _TOOLS[str(envelope.get("tool_name"))]
    blocks = args.get("content") if tool == "Edit" else None
    if isinstance(blocks, list) and blocks and isinstance(blocks[0], dict):
        target, names = blocks[0], {"old_string": "old_str", "new_string": "new_str",
                                    "replace_all": "replace_all"}
        if "file_path" in changed:
            args["file_path"] = changed.pop("file_path")
    else:
        target = args
        names = {
            "Write": {"file_path": _path_key(args), "content": "content"},
            "Read": {"file_path": _path_key(args), "offset": "offset", "limit": "limit"},
            "Grep": {"pattern": "pattern", "path": "path"},
            "Bash": {"command": "command"},
            "Edit": {"file_path": "file_path", "old_string": "old_string",
                     "new_string": "new_string", "replace_all": "replace_all"},
        }[tool]
    for key, value in changed.items():
        if key not in names:
            raise _Unmappable(f"a Writ hook rewrote {key!r}, which Vibe's {envelope.get('tool_name')} has no argument for")
        target[names[key]] = value
    return args


# --------------------------------------------------------------------------- #
# Deferred pre-tool context
# --------------------------------------------------------------------------- #
def _context_file(context_dir: str, sid: str, call_id: str) -> str | None:
    if not (_SAFE_ID.match(sid) and _SAFE_ID.match(call_id)):
        return None
    return os.path.join(context_dir, sid, f"{call_id}.ctx")


def _store_context(path: str | None, text: str) -> None:
    if path:
        os.makedirs(os.path.dirname(path), mode=0o700, exist_ok=True)
        with open(path, "w") as handle:
            handle.write(text)


def _pop_context(path: str | None) -> str:
    if not path:
        return ""
    try:
        with open(path) as handle:
            text = handle.read()
        os.remove(path)
    except OSError:
        return ""
    return text


def _render(output: Any) -> str:
    # Same `key: value` lines Vibe uses for tool_output_text.
    if isinstance(output, str):
        return output
    if isinstance(output, dict):
        return "\n".join(f"{key}: {output[key]}" for key in sorted(output))
    return json.dumps(output)


# --------------------------------------------------------------------------- #
# Typed input to a running process
# --------------------------------------------------------------------------- #
def _session_mode(sid: str) -> str | None:
    """The session's Writ mode from its cache, or None when unset or unreadable."""
    if not _SAFE_ID.match(sid):
        return None
    try:
        with open(os.path.join(session_dir(), f"writ-session-{sid}.json")) as handle:
            mode = json.load(handle).get("mode")
    except (OSError, ValueError, AttributeError):
        return None
    return mode if isinstance(mode, str) and mode else None


def _process_write(event: str, envelope: dict,
                   session_resolver: Callable[[dict], str | None]) -> str:
    if event != PRE:
        return ""
    args = _as_dict(envelope.get("tool_input"))
    if _USER_ONLY.search(str(args.get("text") or "")):
        return _deny(_USER_ONLY_REASON)
    keys = args.get("control")
    # Vibe reads text first, then control, then bytesBase64, which it requires when the
    # other two are absent.
    if ("text" not in args and "bytesBase64" not in args and isinstance(keys, list)
            and set(map(str, keys)) <= _SAFE_KEYS):
        return ""
    sid = session_resolver(envelope)
    if not sid:
        return _deny(_NO_SESSION_REASON)
    mode = _session_mode(sid)
    if mode is not None and mode not in _GATED_MODES:
        return ""
    where = f"in {mode} mode" if mode else "while no Writ mode is set"
    return _deny(
        f"Writ refuses typed input to a running process {where}: its shell checks cannot "
        "see what the process does with it. Only the keys ctrl_c, ctrl_d, ctrl_z, esc and "
        "enter go through. Pass the input as a flag (`--yes`) or pipe it in through bash "
        "(`printf 'y\\n' | cmd`), which Writ checks."
    )


# --------------------------------------------------------------------------- #
# Entry
# --------------------------------------------------------------------------- #
def _handle(event: str, raw: str, *, plugin_root: str, base_env: Mapping[str, str] | None,
            session_resolver: Callable[[dict], str | None], context_dir: str) -> str:
    if event not in (PRE, POST):
        raise ValueError(f"unknown Vibe hook event {event!r}")
    try:
        envelope = json.loads(raw)
    except ValueError:
        envelope = None
    if not isinstance(envelope, dict):
        if event == PRE:
            return _deny("Writ could not read Vibe's hook input, so this call is denied (fail-closed).")
        return ""
    name = str(envelope.get("tool_name") or "")
    if name == _PROCESS_WRITE:
        return _process_write(event, envelope, session_resolver)
    tool = _TOOLS.get(name)
    if tool is None:
        return ""
    if event == PRE and tool == "Bash":
        command = str(_as_dict(envelope.get("tool_input")).get("command") or "")
        if _USER_ONLY.search(command):
            return _deny(_USER_ONLY_REASON)
    sid = session_resolver(envelope)
    if not sid:
        if event == PRE:
            return _deny(_NO_SESSION_REASON)
        return ""

    claude_envs = to_claude(envelope, event, sid)
    with open(os.path.join(plugin_root, "hooks", "hooks.json")) as handle:
        config = json.load(handle)
    jobs = [
        (claude, command, timeout)
        for claude in claude_envs
        for command, timeout in select_commands(config, claude["hook_event_name"], claude["tool_name"])
    ]
    answers = [_read(run) for run in _run_all(jobs, plugin_root=plugin_root, base_env=base_env)]
    ctx_path = _context_file(context_dir, sid, str(envelope.get("tool_call_id") or ""))

    if event == PRE:
        denies = [f"Writ could not run a check, so this call is denied (fail-closed): {a.error}"
                  if a.error else a.deny or a.block
                  for a in answers if a.error or a.deny or a.block]
        if denies:
            return _deny("\n\n".join(denies))
        rewrites = [a.updated_input for a in answers if a.updated_input is not None]
        try:
            vibe_args = _to_vibe_args(envelope, [c["tool_input"] for c in claude_envs], rewrites) if rewrites else None
        except _Unmappable as exc:
            return _deny(f"Writ could not apply its rewrite of this call, so it is denied: {exc}.")
        contexts = [a.context for a in answers if a.context]
        if contexts:
            # Vibe drops pre_tool additional_context; the matching post_tool delivers it.
            _store_context(ctx_path, "\n\n".join(contexts))
        if vibe_args is not None:
            return json.dumps({"decision": "allow", "hook_specific_output": {"tool_input": vibe_args}})
        return ""

    contexts = [_pop_context(ctx_path)]
    for answer in answers:
        contexts += [answer.context, answer.block, answer.deny]
    context = "\n\n".join(c for c in contexts if c)
    outputs = [a.updated_output for a in answers if a.updated_output is not _MISSING]
    result: dict[str, Any] = {"decision": "allow"}
    if outputs:
        # A post_tool deny is how Vibe replaces the result the model sees.
        result = {"decision": "deny", "reason": _render(outputs[-1])}
    if context:
        result["hook_specific_output"] = {"additional_context": context}
    return json.dumps(result) if len(result) > 1 else ""


def handle(
    event: str,
    raw: str,
    *,
    plugin_root: str = PLUGIN_ROOT,
    base_env: Mapping[str, str] | None = None,
    session_resolver: Callable[[dict], str | None] = resolve_session_id,
    context_dir: str | None = None,
) -> str:
    """Vibe's stdout for one hook call: "" for a plain allow, else one JSON object.

    pre_tool fails closed: any error denies the call. post_tool fails quiet: the tool
    already ran, and blanking its result would hide output the model needs.
    """
    try:
        return _handle(event, raw, plugin_root=plugin_root, base_env=base_env,
                       session_resolver=session_resolver,
                       context_dir=context_dir or os.path.join(tempfile.gettempdir(), "writ-vibe"))
    except Exception as exc:  # noqa: BLE001 -- fail closed is the contract
        if event == PRE:
            return _deny(f"Writ's Vibe bridge failed ({type(exc).__name__}: {exc}), so this "
                         "call is denied (fail-closed).")
        return ""


def _event_from(raw: str) -> str:
    try:
        event = json.loads(raw).get("hook_event_name")
    except (ValueError, AttributeError):
        return ""
    return event if event in (PRE, POST) else ""


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    raw = sys.stdin.read()
    event = args[0] if args and args[0] in (PRE, POST) else _event_from(raw)
    if not event:
        return 0
    out = handle(event, raw)
    if out:
        sys.stdout.write(out + "\n")
    return 0
