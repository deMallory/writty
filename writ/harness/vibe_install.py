"""Install Writ for Mistral Vibe into a Vibe home of its own (default ~/.mistty).

`bin/mistty` starts Vibe with VIBE_HOME pointing at that home, so Writ's hooks govern
those sessions only. Plain `vibe` and ~/.vibe stay ungoverned for non-coding use. The
home shares `.env` and `config.toml` with ~/.vibe by symlink and nothing else.

The home's AGENTS.md tells the model how Writ governs the session. Vibe loads it into the
system instructions once, when a session starts, and caps nothing, so it also carries
Writ's always-on rules: they need the authority of instructions and twice the room the
scratchpad has (vibe_context.py carries the per-turn state). The rules are a snapshot
taken from the daemon at install time; a rule change reaches mistty on the next bootstrap.

Every conflict is found before the first write, so a refused install leaves no trace.
Run it through scripts/bootstrap-vibe.sh. Stdlib-only, like the bridge.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import tomllib
from pathlib import Path

from writ.harness.vibe import (
    _BRIDGE_TOOLS,
    _TOOLS,
    AGENT,
    PLUGIN_ROOT,
    POST,
    PRE,
    PROMPT,
    START,
    STOP_SCRIPT_TIMEOUT_S,
)
from writ.harness.vibe_context import WRIT_FILE
from writ.retrieval.prompt_bundle import render_always_on

sys.path.insert(0, os.path.join(PLUGIN_ROOT, "bin", "lib"))
import writ_daemon_client  # type: ignore[import-not-found]  # noqa: E402

HOOK = Path(PLUGIN_ROOT) / "bin" / "writ-vibe-hook"
LAUNCHER = Path(PLUGIN_ROOT) / "bin" / "mistty"
SHARED = (".env", "config.toml")
_OWNED = "writ-"
AGENTS_MARKER = "<!-- Written by writty's scripts/bootstrap-vibe.sh, which owns this file. -->"
_RULES_TIMEOUT_S = 5.0
# Vibe accepts the turn when its own timeout fires, so it waits past the bridge's.
_STOP_TIMEOUT_S = STOP_SCRIPT_TIMEOUT_S + 20

_AGENTS = f"""\
{AGENTS_MARKER}
# Writ governs this session

mistty is Mistral Vibe under Writ. Writ checks each file write, edit and shell command
before it runs, and refuses the ones the session's mode and gates do not allow yet.

## Modes

With no mode set, Writ refuses every write. Set the mode the task needs yourself: run
`mistty mode <mode>` in your shell, or the `writ mode set <mode> <session_id>` that
Writ's context names. Setting a mode restarts its workflow, so never set the mode already
in force. The user can also type `!mistty mode <mode>`.

- `work`: plan, then tests, then code. Write plan.md and capabilities.md in the session's
  plan folder and stop for approval. Then write the test files the plan names and stop for
  approval. Only then edit source files.
- `debug`: source edits stay refused until the session's debug.md records the root cause.
- `review`: evaluate code against Writ's rules and report findings.
- `conversation`: no code changes are expected.
- `investigate`: explore, audit or research, with every finding grounded in evidence.

## Only the user moves the gates

Writ advances when the user types one of these in mistty:

- `!mistty approve`: approve the pending gate (the plan, then the tests).
- `!mistty replan`: send a session in implementation back to planning.
- `!mistty grant manual-test`: concede manual testing for 30 minutes.

You cannot run them: Writ refuses them in your shell calls. When you need one, stop and
ask the user to type it.

The user can also approve the pending gate in chat, by replying `approved` to your
request. Writ counts that reply only when your previous message asked for it, so end the
message that presents the plan or the tests with `Say approved to proceed.` Writ advances
the gate before your turn starts and says so in its context for that prompt.

## Writ's state

`{WRIT_FILE}` in your scratchpad holds the session's mode, phase, pending gate, plan
folder and next step. Writ rewrites it after each prompt, each tool call and each
`!mistty` command. Read it there and never write it; keep your own notes in other
scratchpad files. A new session has none until its first prompt.

## End of turn

When your turn ends, Writ runs its end-of-turn checks: unresolved rule violations,
failing tests for the files you changed, and work its quality review scored below 3. A
failing check sends your turn back with Writ's reason as a user message. Fix what it
names before you finish. Vibe sends a turn back at most 3 times.

## Subagents

Vibe runs no hook inside a subagent, so Writ cannot check a subagent's tool calls. In
work mode, in debug mode and with no mode set, Writ refuses `subagent.spawn` and
`subagent.send_message`: do the work yourself, and do not retry a refused call. In the
other modes subagents run, and Writ's rules still apply to the work you give them.

## Refusals

A direct tool call that Writ refuses fails with Writ's reason. Inside `run_typescript`, a
refused call fails as `tool_skipped: Tool execution was skipped by Runtime policy.` and
Vibe drops the reason. Treat it as a Writ refusal: do not work around it with another
call. To see the reason, make the same call directly, outside `run_typescript`, or tell
the user what was refused.

`process.write` text is refused in work mode, in debug mode and with no mode set. Pass
the input as a flag (`--yes`) or pipe it in through bash (`printf 'y\\n' | cmd`).
"""

# Runs under Vibe's own interpreter: the same loader a session uses, in strict mode.
_LOAD = (
    "import json, sys\n"
    "from pathlib import Path\n"
    "from vibe.core.hooks.config import load_hooks_file\n"
    "r = load_hooks_file(Path(sys.argv[1]), strict=True)\n"
    "print(json.dumps({'issues': [i.message for i in r.issues],"
    " 'names': [h.name for h in r.hooks]}))\n"
)


def matcher() -> str:
    """Exactly the tools the bridge maps or decides itself. Vibe fullmatches `re:` patterns,
    ignoring case, so a tool the bridge would pass through never pays for starting it."""
    return "re:" + "|".join(re.escape(name) for name in sorted({*_TOOLS, *_BRIDGE_TOOLS}))


def render_hooks() -> str:
    # json.dumps output is a valid TOML basic string, backslashes included.
    match = json.dumps(matcher())
    out = "# Written by writty's scripts/bootstrap-vibe.sh, which owns every writ-* entry.\n"
    for name, event, strict in (("writ-pre", PRE, True), ("writ-post", POST, False)):
        out += (f'\n[[hooks]]\nname = "{name}"\ntype = "{event}"\nmatch = {match}\n'
                f"command = {json.dumps(f'{shlex.quote(str(HOOK))} {event}')}\n")
        if strict:
            # A bridge that crashes before printing still denies the call.
            out += "strict = true\n"
    # Vibe's loader refuses match and strict on post_agent, user_prompt and session_start.
    out += (f'\n[[hooks]]\nname = "writ-stop"\ntype = "{AGENT}"\n'
            f"command = {json.dumps(f'{shlex.quote(str(HOOK))} {AGENT}')}\n"
            f"timeout = {_STOP_TIMEOUT_S}\n")
    # Vibe's default timeout, 60 s, outlasts the bridge's 30 s per script.
    for name, event in (("writ-prompt", PROMPT), ("writ-session-start", START)):
        out += (f'\n[[hooks]]\nname = "{name}"\ntype = "{event}"\n'
                f"command = {json.dumps(f'{shlex.quote(str(HOOK))} {event}')}\n")
    return out


def _conflicts(home: Path, bin_dir: Path) -> list[str]:
    found = []
    hooks = home / "hooks.toml"
    if hooks.exists():
        try:
            entries = tomllib.loads(hooks.read_text()).get("hooks", [])
        except (OSError, UnicodeDecodeError, tomllib.TOMLDecodeError) as e:
            found.append(f"{hooks} is unreadable ({e}); move it aside and rerun")
        else:
            names = [e.get("name") if isinstance(e, dict) else None for e in entries]
            foreign = [repr(n) for n in names if not (isinstance(n, str) and n.startswith(_OWNED))]
            if foreign:
                found.append(f"{hooks} holds hooks this installer does not own: "
                             f"{', '.join(foreign)}")
    agents = home / "AGENTS.md"
    if (agents.exists() or agents.is_symlink()) and not _owns_agents(agents):
        found.append(f"{agents} was not written by this installer; move it aside and rerun")
    link = bin_dir / "mistty"
    if (link.exists() or link.is_symlink()) and not _links_to(link, LAUNCHER):
        found.append(f"{link} exists and is not a link to {LAUNCHER}")
    return found


def _owns_agents(path: Path) -> bool:
    try:
        return path.read_text().split("\n", 1)[0] == AGENTS_MARKER
    except (OSError, UnicodeDecodeError):
        return False


def _links_to(link: Path, target: Path) -> bool:
    return link.is_symlink() and Path(os.readlink(link)) == target


def _share(home: Path, source_home: Path, name: str) -> str:
    src, dst = source_home / name, home / name
    if _links_to(dst, src):
        return f"link {name} -> {src}"
    if dst.exists() or dst.is_symlink():
        return f"keep {name}: already present"
    if not src.exists():
        return f"skip {name}: {src} does not exist"
    dst.symlink_to(src)
    return f"link {name} -> {src}"


def _replace(path: Path, text: str) -> None:
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.")
    with os.fdopen(fd, "w") as f:
        f.write(text)
    os.replace(tmp, path)


def _write_hooks(home: Path) -> str:
    path, text = home / "hooks.toml", render_hooks()
    if path.exists() and path.read_text() == text:
        return "keep hooks.toml: up to date"
    _replace(path, text)
    return f"write {path}"


def fetch_rules() -> str | None:
    """Writ's always-on rules, rendered as the prompt hook renders them, or None when the
    daemon gave none."""
    status, body = writ_daemon_client.get_json("/always-on", timeout=_RULES_TIMEOUT_S)
    if status != 200:
        return None
    try:
        bundle = json.loads(body)
    except ValueError:
        return None
    if not isinstance(bundle, dict):
        return None
    return render_always_on(bundle)[0] or None


def render_agents(rules: str | None) -> str:
    if not rules:
        return _AGENTS
    return f"{_AGENTS}\n## Writ's always-active rules\n\n{rules}\n"


def _write_agents(home: Path) -> str:
    path, rules = home / "AGENTS.md", fetch_rules()
    if rules is None and path.exists():
        return f"keep {path}: the Writ daemon gave no rules, so rules not refreshed"
    text = render_agents(rules)
    if path.exists() and path.read_text() == text:
        return "keep AGENTS.md: up to date"
    _replace(path, text)
    if rules is None:
        return f"write {path}: rules skipped, the Writ daemon gave none; rerun once it runs"
    return f"write {path}"


def vibe_python() -> str | None:
    """The interpreter of the `vibe` on PATH, read from its shebang (uv writes an
    absolute path to the tool's venv python)."""
    exe = shutil.which("vibe")
    if not exe:
        return None
    try:
        with open(os.path.realpath(exe), "rb") as f:
            first = f.readline().decode(errors="replace")
    except OSError:
        return None
    parts = first[2:].split() if first.startswith("#!") else []
    return parts[0] if parts and os.access(parts[0], os.X_OK) else None


def _check(path: Path, python: str) -> list[str]:
    try:
        proc = subprocess.run([python, "-c", _LOAD, str(path)],
                              capture_output=True, text=True, timeout=60)
        if proc.returncode != 0:
            detail = proc.stderr.strip().splitlines()[-1:]
            return [f"Vibe's loader exited {proc.returncode}"
                    + (f" ({detail[0]})" if detail else "")]
        return [str(i) for i in json.loads(proc.stdout)["issues"]]
    except (OSError, subprocess.SubprocessError, ValueError, KeyError, TypeError) as e:
        return [f"Vibe's loader did not run ({e})"]


def main(argv: list[str] | None = None) -> int:
    home_default = os.environ.get("MISTTY_HOME") or str(Path.home() / ".mistty")
    parser = argparse.ArgumentParser(
        prog="bootstrap-vibe.sh",
        description="Install Writ's hooks into a separate Vibe home and link `mistty`.")
    parser.add_argument("--home", default=home_default,
                        help="the mistty Vibe home (default: $MISTTY_HOME or ~/.mistty)")
    parser.add_argument("--source-home", default=str(Path.home() / ".vibe"),
                        help="where .env and config.toml come from (default: ~/.vibe)")
    parser.add_argument("--bin-dir", default=str(Path.home() / ".local" / "bin"),
                        help="where the mistty launcher is linked (default: ~/.local/bin)")
    parser.add_argument("--vibe-python",
                        help="interpreter for the loader check (default: from `vibe` on PATH)")
    parser.add_argument("--no-check", action="store_true",
                        help="skip validating hooks.toml with Vibe's loader")
    args = parser.parse_args(argv)
    home, source_home, bin_dir = (Path(p).expanduser().absolute()
                                  for p in (args.home, args.source_home, args.bin_dir))

    conflicts = _conflicts(home, bin_dir)
    if conflicts:
        for c in conflicts:
            print(f"conflict: {c}")
        print("nothing written")
        return 1

    home.mkdir(mode=0o700, parents=True, exist_ok=True)
    home.chmod(0o700)
    for name in SHARED:
        print(_share(home, source_home, name))
    print(_write_hooks(home))
    print(_write_agents(home))
    bin_dir.mkdir(parents=True, exist_ok=True)
    if not _links_to(bin_dir / "mistty", LAUNCHER):
        (bin_dir / "mistty").symlink_to(LAUNCHER)
    print(f"link {bin_dir / 'mistty'} -> {LAUNCHER}")

    if args.no_check:
        return 0
    python = args.vibe_python or vibe_python()
    if not python:
        print("check hooks.toml: skipped, no vibe on PATH")
        return 0
    issues = _check(home / "hooks.toml", python)
    print(f"check hooks.toml: Vibe's loader reports {len(issues)} issues")
    for issue in issues:
        print(f"  {issue}")
    return 1 if issues else 0


if __name__ == "__main__":
    sys.exit(main())
