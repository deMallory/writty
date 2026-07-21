"""Audit #5: hooks must tag their hook_execution telemetry with the real mode.

Six call sites across five hooks called `hook_timer_end ... "$SESSION_ID" ""` with an
empty 4th arg, so every hook_execution event those hooks emitted logged mode:null --
the latency/frequency telemetry could not be broken down by mode. Each hook must read
the session mode (or reuse one it already computed) and pass it.

Structural guard (per TEST-REGRESSION-001): the empty-literal 4th arg must be gone, and
each timer_end call must reference a mode variable. The hook_timer_end mechanism itself
is covered by test_friction_isolation.py::test_common_sh_hook_timer_end_honors_env.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

HOOKS_DIR = Path(__file__).resolve().parent.parent / "hooks" / "scripts"

# Hooks the audit flagged as passing an empty mode to hook_timer_end.
FLAGGED_HOOKS = [
    "writ-postcompact.sh",
    "writ-precompact.sh",
    "writ-posttool-rag.sh",
    "writ-session-end.sh",
    "writ-pre-write-dispatch.sh",
]

# A hook_timer_end call ending in an empty-string 4th positional arg, e.g.
#   hook_timer_end "$HOOK_START_NS" "name" "$SESSION_ID" ""
EMPTY_MODE_TIMER_END = re.compile(r'hook_timer_end\b[^\n]*"\$SESSION_ID"\s*""')


@pytest.mark.parametrize("hook", FLAGGED_HOOKS)
def test_no_empty_mode_timer_end(hook: str) -> None:
    src = (HOOKS_DIR / hook).read_text()
    bad = EMPTY_MODE_TIMER_END.findall(src)
    assert not bad, (
        f"{hook} still calls hook_timer_end with an empty mode arg "
        f"(logs mode:null): {bad}"
    )


@pytest.mark.parametrize("hook", FLAGGED_HOOKS)
def test_timer_end_passes_a_mode_variable(hook: str) -> None:
    src = (HOOKS_DIR / hook).read_text()
    timer_lines = [ln for ln in src.splitlines() if "hook_timer_end" in ln]
    assert timer_lines, f"{hook} has no hook_timer_end call"
    for ln in timer_lines:
        assert re.search(r'\$\{?(MODE|CURRENT_MODE)\b', ln), (
            f"{hook}: hook_timer_end must pass a mode variable, got: {ln.strip()}"
        )
