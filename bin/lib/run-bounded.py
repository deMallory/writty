#!/usr/bin/env python3
"""Run a command under a time limit: a stand-in for GNU timeout(1).

    run-bounded.py SECONDS COMMAND [ARG...]

Stock macOS ships no `timeout`. A hook that calls it gets the shell's exit 127, which
reads the same as the failure the hook was checking for.

Exits with the command's status (128+N when signal N killed it), or 124 when the limit
expires, as GNU timeout does. The command runs in its own session so that expiry kills
the whole group: a test runner's workers must not outlive the run. TERM, HUP and INT
sent to this process are forwarded to that group, again as GNU timeout does, so a hook
killed by its caller does not orphan the command.
"""
from __future__ import annotations

import os
import signal
import subprocess
import sys


def _killpg(pgid: int, signum: int) -> None:
    # The group can empty between the check and the kill; nothing is left to signal.
    try:
        os.killpg(pgid, signum)
    except ProcessLookupError:
        pass


def main(argv: list[str]) -> int:
    seconds = float(argv[0])
    proc = subprocess.Popen(argv[1:], start_new_session=True)

    def forward(signum: int, _frame) -> None:
        _killpg(proc.pid, signum)

    for signum in (signal.SIGTERM, signal.SIGHUP, signal.SIGINT):
        signal.signal(signum, forward)
    try:
        returncode = proc.wait(timeout=seconds)
    except subprocess.TimeoutExpired:
        _killpg(proc.pid, signal.SIGTERM)
        proc.wait()
        return 124
    return 128 - returncode if returncode < 0 else returncode


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
