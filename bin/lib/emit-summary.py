#!/usr/bin/env python3
"""Shared summary emitter for hooks that produce verbose tool output.

Reads a log file (full tool output), emits a terse stderr summary that
references the log path. Claude reads the log only if the summary does not
pinpoint the cause. Always exits 0; caller picks the hook exit code.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path


def summarize_pytest(text: str) -> tuple[int, list[str]]:
    fails = re.findall(r"^FAILED .*$", text, re.M)
    first_assert = re.search(r"^E\s+.*$", text, re.M)
    lines: list[str] = []
    if fails:
        lines.append(fails[0])
    if first_assert:
        lines.append(first_assert.group(0))
    return len(fails), lines


def summarize_phpunit(text: str) -> tuple[int, list[str]]:
    # PHPUnit prints `1) ...` numbered lists for BOTH failures and warnings,
    # and a run can contain a warnings section AND a failures section in the
    # same output (e.g. Magento with Allure config missing + failing tests).
    # Two-stage filter:
    #   1. Require a `FAILURES!` or `ERRORS!` headline -- proves real failures
    #      exist somewhere in the output.
    #   2. Require `::` in each matched line -- failure/error entries use the
    #      `1) FQCN::methodName` form; warning entries have free-form text.
    if not re.search(r"^(FAILURES!|ERRORS!)", text, re.M):
        return 0, []
    fails = re.findall(r"^\d+\) .*::.+$", text, re.M)
    return len(fails), fails[:1]


def summarize_gotest(text: str) -> tuple[int, list[str]]:
    fails = re.findall(r"^--- FAIL: .*$", text, re.M)
    return len(fails), fails[:1]


def summarize_json(text: str) -> tuple[int, list[str]]:
    try:
        findings = json.loads(text)
    except (json.JSONDecodeError, ValueError):
        return 0, []
    if not isinstance(findings, list):
        return 0, []
    errs = [f for f in findings if isinstance(f, dict) and f.get("severity") == "error"]
    if not errs:
        return 0, []
    f = errs[0]
    line = (f"{f.get('file', '?')}:{f.get('line', 0)} "
            f"[{f.get('tool', '?')}] {f.get('message', '')}")
    return len(errs), [line]


DISPATCH = {
    "pytest": summarize_pytest,
    "phpunit": summarize_phpunit,
    "gotest": summarize_gotest,
    "json": summarize_json,
}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--format", required=True, choices=list(DISPATCH))
    ap.add_argument("--log", required=True, help="Path to full output log")
    ap.add_argument("--rule", default="ENF-POST-007", help="Rule code prefix")
    ap.add_argument("--label", default="findings",
                    help="Plural noun used in the count line")
    args = ap.parse_args()

    log_path = Path(args.log)
    if not log_path.is_file():
        return 0

    try:
        text = log_path.read_text(errors="replace")
    except OSError:
        return 0

    count, first_lines = DISPATCH[args.format](text)
    if count == 0:
        return 0

    print(f"[{args.rule}] {count} {args.label}. First:", file=sys.stderr)
    for line in first_lines:
        if line:
            print(f"  {line}", file=sys.stderr)
    print(f"Full log: {log_path}", file=sys.stderr)
    print("Read the log only if the first finding does not pinpoint the cause.",
          file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
