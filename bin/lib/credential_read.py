#!/usr/bin/env python3
"""Classify Read / Grep / Bash tool inputs that would read a secret file.

Whatever Claude reads enters the transcript and leaves the machine, so the read is
the leak. This module never opens a file: it looks at paths only, and reuses
writ.session.gates._is_credential_path so the template allowlist (.env.example,
.env.sample, ...) stays the same as the write gate's.

Known gaps (see README limits): a path built from variables, eval, base64,
sh -c, an interpreter reaching the file by a computed name, a program file
(python read_env.py), and Grep over a directory that holds a committed .env.

CLI: reads a hook envelope on stdin, prints the offending path (or nothing).
"""

from __future__ import annotations

import json
import os
import re
import shlex
import sys

_ROOT = os.environ.get("WRIT_DIR") or os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)
sys.path.insert(0, _ROOT)

try:
    from writ.session.gates import _CREDENTIAL_DIR_SEGMENTS, _is_credential_path
except Exception:  # broken install: fail closed on the common case, .env files
    _CREDENTIAL_DIR_SEGMENTS = ("/.ssh/", "/secrets/", "/secret/", "/.gnupg/", "/.kube/")
    _TEMPLATES = (
        ".env.example", ".env.sample", ".env.template", ".env.dist", ".env.defaults",
        "example.env", "sample.env", "template.env",
    )

    def _is_credential_path(path: str) -> bool:
        base = os.path.basename(path.replace("\\", "/")).lower()
        if base in _TEMPLATES:
            return False
        return base == ".env" or base.startswith(".env.")


READERS = frozenset({
    "cat", "tac", "head", "tail", "less", "more", "bat", "nl",
    "grep", "egrep", "fgrep", "rg", "ag", "awk", "sed", "cut", "sort", "uniq",
    "strings", "xxd", "od", "hexdump", "base64", "diff", "cmp", "jq", "yq",
    "source", ".", "cp", "scp", "rsync", "tar", "zip", "openssl",
})
WRAPPERS = frozenset({"env", "command", "sudo", "nohup", "time", "exec"})
INTERPRETER = re.compile(r"^(python[0-9.]*|node|ruby|perl|php)$")
INLINE_FLAGS = frozenset({"-c", "-e", "-r", "-E"})
SEPARATORS = frozenset({"|", "||", "&&", ";", "&", "|&", "(", ")", ";;"})
ASSIGNMENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")
STRING_LITERAL = re.compile(r"""['"]([^'"\s]+)['"]""")
GREP_FAMILY = frozenset({"grep", "egrep", "fgrep", "rg", "ag"})
# Flags whose value is a pattern (skipped) or a count (never the pattern).
PATTERN_FLAGS = frozenset({"-e", "--regexp"})
COUNT_FLAGS = frozenset({"-A", "-B", "-C", "-m", "--max-count"})
# `secret`, `.ssh`, ... alone: _is_credential_path reads the word as the directory
# itself, so `grep secret src/` or `d['secret']` was refused. A path must follow.
SECRET_DIR_NAMES = frozenset(s.strip("/") for s in _CREDENTIAL_DIR_SEGMENTS)


def _is_secret(path: str) -> bool:
    if not path or ("/" not in path and path.lower() in SECRET_DIR_NAMES):
        return False
    return _is_credential_path(path) or _is_credential_path(os.path.expanduser(path))


def _without_pattern(args: list[str]) -> list[str]:
    """grep-family args minus the search pattern, which is text, not a file. The
    pattern is the -e value, else the first positional. -f and -g values stay: grep
    -f and rg -g make the tool open that file."""
    explicit = any(a in PATTERN_FLAGS or a.startswith("--regexp=") for a in args)
    out: list[str] = []
    i = 0
    while i < len(args):
        a = args[i]
        if a in PATTERN_FLAGS or a in COUNT_FLAGS:
            i += 2
            continue
        if not explicit and not a.startswith("-"):
            explicit = True
            i += 1
            continue
        out.append(a)
        i += 1
    return out


def _tokens(command: str) -> list[str]:
    try:
        lex = shlex.shlex(command, posix=True, punctuation_chars=True)
        lex.whitespace_split = True
        return list(lex)
    except ValueError:  # unbalanced quotes: a plain split still finds bare paths
        return command.split()


def _segments(tokens: list[str]) -> list[list[str]]:
    out: list[list[str]] = [[]]
    for tok in tokens:
        if tok in SEPARATORS:
            out.append([])
        else:
            out[-1].append(tok)
    return [seg for seg in out if seg]


def _check_segment(seg: list[str]) -> str | None:
    args: list[str] = []
    i = 0
    while i < len(seg):
        tok = seg[i]
        if tok == "<" or tok == "<<<":
            if tok == "<" and i + 1 < len(seg) and _is_secret(seg[i + 1]):
                return seg[i + 1]
            i += 2
            continue
        if tok.startswith(">") or tok.startswith("<"):
            i += 2  # output redirect target: the write gate's job
            continue
        args.append(tok)
        i += 1

    while args and ASSIGNMENT.match(args[0]):
        args.pop(0)
    while args and os.path.basename(args[0]) in WRAPPERS:
        args.pop(0)
        while args and (args[0].startswith("-") or ASSIGNMENT.match(args[0])):
            args.pop(0)
    if not args:
        return None

    verb = os.path.basename(args[0])
    rest = args[1:]
    if verb in READERS:
        if verb in GREP_FAMILY:
            rest = _without_pattern(rest)
        for arg in rest:
            candidate = arg.split("=", 1)[1] if arg.startswith("-") and "=" in arg else arg
            if _is_secret(candidate):
                return candidate
    elif INTERPRETER.match(verb):
        for flag, code in zip(rest, rest[1:]):
            if flag in INLINE_FLAGS:
                for lit in STRING_LITERAL.findall(code):
                    if _is_secret(lit):
                        return lit
    return None


def find_credential_read(tool_name: str, tool_input: dict) -> str | None:
    """Return the first secret path this tool call would read, else None."""
    if not isinstance(tool_input, dict):
        return None
    if tool_name == "Read":
        path = tool_input.get("file_path") or ""
        return path if _is_secret(path) else None
    if tool_name == "Grep":
        path = tool_input.get("path") or ""
        return path if _is_secret(path) else None
    if tool_name == "Bash":
        command = tool_input.get("command") or ""
        for seg in _segments(_tokens(command)):
            hit = _check_segment(seg)
            if hit:
                return hit
    return None


def main() -> None:
    try:
        envelope = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        return
    hit = find_credential_read(envelope.get("tool_name", ""), envelope.get("tool_input", {}))
    if hit:
        sys.stdout.write(hit)
        sys.stdout.flush()
        # The refusal is already out; a logging failure must not turn it into an allow.
        try:
            from writ.session.cache import _read_cache
            from writ.session.friction import _log_friction_event
            sid = envelope.get("session_id") or ""
            _log_friction_event(sid, _read_cache(sid).get("mode") if sid else None,
                                "gate_denial", rule_id="SEC-CREDENTIAL-READ",
                                file_path=hit, gate="credential_read")
        except Exception:
            pass


if __name__ == "__main__":
    main()
