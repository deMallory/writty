"""Writ commands for the user of a mistty session.

Typed inside Vibe as `!mistty approve`, `!mistty replan`, `!mistty grant manual-test` or
`!mistty mode <mode>`. Vibe runs a `!` command as a child of the session's process, fires
no hook, and shows the output to the model. So each command stands in for the Claude
prompt turn it replaces: it hands Writ's own UserPromptSubmit hook the phrase the user
would have typed there, or runs Writ's mode command. Every decision stays in those scripts.
Then it rewrites Writ's state file in the session's scratchpad (vibe_context.py).

Vibe keeps no Claude transcript, so `approve` sends the override phrase: the hook skips its
"did the assistant ask" check and logs approval_evidence_override. The bridge (vibe.py)
refuses all but `mode` to the model, which sets the mode itself as it does under Claude
Code. Stdlib-only, like the bridge.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from collections.abc import Callable, Mapping

from writ.harness import vibe, vibe_context

sys.path.insert(0, os.path.join(vibe.PLUGIN_ROOT, "bin", "lib"))
# The phrases come from the modules that match them, so a drift cannot send one that no
# longer fires.
import approval_match  # type: ignore[import-not-found]  # noqa: E402
import manual_test_grant  # type: ignore[import-not-found]  # noqa: E402

APPROVE_HOOK = "auto-approve-gate"
GRANT_HOOK = "writ-manual-test-grant"

_PROMPTS: dict[str, tuple[str, str]] = {
    "approve": (APPROVE_HOOK, approval_match.OVERRIDE_PHRASE),
    "replan": (APPROVE_HOOK, approval_match.REPLAN_PHRASE),
    "grant": (GRANT_HOOK, manual_test_grant.GRANT_PHRASES[0]),
}


def _prompt_hook(script: str, phrase: str, sid: str, *, plugin_root: str,
                 base_env: Mapping[str, str] | None) -> tuple[int, str]:
    """Run one hooks.json UserPromptSubmit script as if the user had typed `phrase`.

    Only that script runs: writ-rag-inject.sh would print its whole RAG block into the
    `!` output, and context reaches Vibe through its own channel.
    """
    with open(os.path.join(plugin_root, "hooks", "hooks.json")) as handle:
        config = json.load(handle)
    commands = [(command, timeout)
                for command, timeout in vibe.select_commands(config, "UserPromptSubmit", "")
                if vibe._script_name(command) == script]
    if not commands:
        return 1, f"mistty: hooks/hooks.json lists no {script} hook, so nothing was run.\n"
    # cwd is where the `!` command runs; the approval hook sends it to the daemon, which
    # finds the project root, and so the plan, from it.
    envelope = {"session_id": sid, "prompt": phrase, "transcript_path": "",
                "cwd": os.getcwd(), "hook_event_name": "UserPromptSubmit"}
    command, timeout = commands[0]
    [run] = vibe._run_all([(envelope, command, timeout)], plugin_root=plugin_root,
                          base_env=base_env)
    if run.error:
        return 1, f"{run.stdout}mistty: {run.name} {run.error}.\n"
    if run.returncode != 0:
        return 1, f"{run.stdout}{run.stderr}mistty: {run.name} exited {run.returncode}.\n"
    return 0, run.stdout


def _mode(mode: str, sid: str, *, plugin_root: str,
          base_env: Mapping[str, str] | None) -> tuple[int, str]:
    helper = os.path.join(plugin_root, "bin", "lib", "writ-session.py")
    try:
        proc = subprocess.run([sys.executable, helper, "mode", "set", mode, sid],
                              capture_output=True, text=True, timeout=30,
                              env=dict(os.environ if base_env is None else base_env))
    except (OSError, subprocess.SubprocessError) as exc:
        return 1, f"mistty: Writ's mode command did not run ({exc}).\n"
    return proc.returncode, proc.stdout + proc.stderr


def main(
    argv: list[str] | None = None,
    *,
    plugin_root: str = vibe.PLUGIN_ROOT,
    base_env: Mapping[str, str] | None = None,
    session_resolver: Callable[[], str | None] | None = None,
) -> int:
    parser = argparse.ArgumentParser(
        prog="mistty",
        description="Writ commands for the user of a mistty session. "
                    "Type them inside mistty as `!mistty <command>`.")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("approve", help="approve the pending Writ gate")
    sub.add_parser("replan", help="return a work session in implementation to planning")
    grant = sub.add_parser("grant", help="concede manual testing for 30 minutes")
    grant.add_argument("what", choices=["manual-test"])
    mode = sub.add_parser("mode", help="set the Writ mode, which restarts its workflow")
    mode.add_argument("mode")
    args = parser.parse_args(argv)

    sid = (session_resolver or (lambda: vibe.resolve_session_id({})))()
    if not sid:
        print("mistty: no live mistty session owns this process, so nothing was run. "
              f"Type it inside mistty as `!mistty {args.command}`.")
        return 1
    print(f"[mistty: Vibe session {sid}]")
    if args.command == "mode":
        rc, out = _mode(args.mode, sid, plugin_root=plugin_root, base_env=base_env)
    else:
        script, phrase = _PROMPTS[args.command]
        rc, out = _prompt_hook(script, phrase, sid, plugin_root=plugin_root, base_env=base_env)
        if rc == 0 and args.command == "grant" and not out.strip():
            # The grant hook prints only after it reads a minted grant back from disk.
            rc, out = 1, "mistty: no manual-testing grant was minted; Writ's gate log has the reason.\n"
    sys.stdout.write(out)
    # A `!` command runs between turns, so the next turn starts with the new state.
    vibe_context.refresh(sid, plugin_root=plugin_root, base_env=base_env)
    return rc


if __name__ == "__main__":
    sys.exit(main())
