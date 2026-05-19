#!/usr/bin/env python3
"""Project-agnostic test-path resolver.

Owns all knowledge of which files are sources vs tests, how to map a source
to its test, and how to invoke the test runner. Consumed by the bash hooks
(writ-mark-pending-test.sh, writ-run-pending-tests.sh) via the CLI surface.

Configuration precedence:
  1. <cwd>/.claude/writ.json (project-local)
  2. <skill>/bin/lib/test-paths-defaults.json (bundled)

If the project file has `extends_defaults: true` (default), project patterns
override defaults of the same name and any remaining defaults are appended.
If `extends_defaults: false`, defaults are dropped entirely.

CLI:
  match-src   <file>          -> first matching pattern name, or empty
  match-test  <file>          -> first matching pattern name, or empty
  resolve-test <src-file>     -> absolute test path if it exists, or empty
  runner-for  <test-file>     -> two lines: command, config-file (or empty)

Always exits 0 on the CLI; bash callers treat empty stdout as no-match.
"""
from __future__ import annotations

import argparse
import fnmatch
import json
import os
import re
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULTS_PATH = SCRIPT_DIR / "test-paths-defaults.json"

# Set by load_config when the project JSON fails to parse. Tests inspect this.
last_load_error: str | None = None


def _read_json(path: Path) -> dict:
    with path.open() as f:
        return json.load(f)


def load_config(cwd: Path | str | None = None) -> dict:
    """Merge bundled defaults with optional <cwd>/.claude/writ.json."""
    global last_load_error
    last_load_error = None

    defaults = _read_json(DEFAULTS_PATH)
    if cwd is None:
        return defaults
    cwd = Path(cwd)
    project_path = cwd / ".claude" / "writ.json"
    if not project_path.is_file():
        return defaults

    try:
        project = _read_json(project_path)
    except (json.JSONDecodeError, ValueError) as exc:
        last_load_error = f"{project_path}: {exc}"
        return defaults

    extends = project.get("extends_defaults", True)
    project_pats = project.get("patterns", []) or []
    if not extends:
        return {"patterns": project_pats}

    redefined = {p.get("name") for p in project_pats if p.get("name")}
    surviving_defaults = [
        p for p in defaults.get("patterns", []) if p.get("name") not in redefined
    ]
    return {"patterns": project_pats + surviving_defaults}


def _any_glob_matches(file_path: str, globs: list[str]) -> bool:
    return any(fnmatch.fnmatch(file_path, g) for g in globs)


def _matches_any_test_glob(file_path: str, config: dict) -> bool:
    for pat in config.get("patterns", []):
        if _any_glob_matches(file_path, pat.get("test_match", [])):
            return True
    return False


def match_src(file_path: str, config: dict) -> str:
    """Return the first pattern whose src_match matches, EXCLUDING test files.

    The test-exclusion check prevents src globs that greedily span path
    components (e.g. `*.go`, `*/app/code/*/Model/*.php`) from claiming a
    file that should be classified as a test.
    """
    if _matches_any_test_glob(file_path, config):
        return ""
    for pat in config.get("patterns", []):
        if _any_glob_matches(file_path, pat.get("src_match", [])):
            return pat.get("name", "")
    return ""


def match_test(file_path: str, config: dict) -> str:
    for pat in config.get("patterns", []):
        if _any_glob_matches(file_path, pat.get("test_match", [])):
            return pat.get("name", "")
    return ""


def _find_pattern(config: dict, name: str) -> dict | None:
    for pat in config.get("patterns", []):
        if pat.get("name") == name:
            return pat
    return None


def resolve_test(src_path: str, config: dict) -> str:
    """If src_path is itself a test, return it (if it exists). Else apply mirror.

    Returns empty when the computed test file does not exist on disk.
    """
    if match_test(src_path, config):
        return src_path if os.path.isfile(src_path) else ""

    name = match_src(src_path, config)
    if not name:
        return ""
    pat = _find_pattern(config, name)
    if not pat:
        return ""
    regex = pat.get("src_to_test_regex")
    template = pat.get("src_to_test_replace")
    if not regex or not template:
        return ""
    m = re.match(regex, src_path)
    if not m:
        return ""

    def _sub(token: re.Match) -> str:
        idx = int(token.group(1))
        return m.group(idx)

    result = re.sub(r"\{(\d+)\}", _sub, template)
    return result if os.path.isfile(result) else ""


def runner_for(test_path: str, config: dict, cwd: Path | str | None = None) -> tuple[str, str]:
    """Return (command, config_file_or_empty) for the runner that owns this test."""
    name = match_test(test_path, config)
    if not name:
        return ("", "")
    pat = _find_pattern(config, name)
    if not pat:
        return ("", "")
    cmd = pat.get("runner_command", "")
    cfg_rel = pat.get("runner_config_file", "") or ""
    cfg_abs = ""
    if cfg_rel:
        base = Path(cwd) if cwd else Path.cwd()
        candidate = base / cfg_rel
        if candidate.is_file():
            cfg_abs = str(candidate)
    return (cmd, cfg_abs)


# ── CLI dispatch ────────────────────────────────────────────────────────────


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)

    p_ms = sub.add_parser("match-src")
    p_ms.add_argument("file")
    p_mt = sub.add_parser("match-test")
    p_mt.add_argument("file")
    p_rt = sub.add_parser("resolve-test")
    p_rt.add_argument("file")
    p_rf = sub.add_parser("runner-for")
    p_rf.add_argument("file")

    args = ap.parse_args(argv)
    cwd = Path.cwd()
    config = load_config(cwd)

    if args.cmd == "match-src":
        print(match_src(args.file, config))
    elif args.cmd == "match-test":
        print(match_test(args.file, config))
    elif args.cmd == "resolve-test":
        print(resolve_test(args.file, config))
    elif args.cmd == "runner-for":
        cmd, cfg = runner_for(args.file, config, cwd)
        print(cmd)
        print(cfg)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
