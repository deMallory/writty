#!/usr/bin/env python3
"""Completion-claim check: paths named in a message that do not exist.

Reads a hook envelope (raw or parse-hook-stdin output) on stdin, extracts
a message field (default last_assistant_message), and prints a
comma-separated list of claimed paths missing from disk. Used by
writ-subagent-stop.sh (SubagentStop) and writ-verify-before-claim.sh
(Stop: the 2.1.199 envelope carries last_assistant_message for the main
agent too, which the 2.1.183 map did not list).

Tokens must contain a directory separator so prose mentions of bare
filenames ("update package.json later") never count; URLs are stripped
first. A path only counts inside a sentence that asserts completed work
(past-tense claim verb): hypotheticals like "next step would be creating
src/foo.py" are not claims. Verbs asserting removal (deleted, removed)
are deliberately absent, since for those the file is supposed to be
missing. Stdlib only.
"""

import json
import os
import re
import sys

EXTS = r"(?:py|php|js|jsx|ts|tsx|go|rs|sh|yaml|yml|xml|graphql|graphqls|json|md)"

CLAIM_VERBS = re.compile(
    r"(?i)\b(?:created|wrote|written|added|implemented|updated|edited|"
    r"fixed|generated|saved|synced|refactored|modified|extended|"
    r"registered|patched|built|produced)\b"
)


def main() -> None:
    field = sys.argv[1] if len(sys.argv) > 1 else "last_assistant_message"
    try:
        d = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        return
    msg = d.get(field) or ""
    cwd = d.get("cwd") or os.getcwd()
    msg = re.sub(r"https?://\S+", "", msg)
    tokens = []
    for sentence in re.split(r"[.!?\n]+(?=\s|$)", msg):
        if not CLAIM_VERBS.search(sentence):
            continue
        tokens.extend(
            re.findall(
                r"(?:~?/)?[A-Za-z0-9_@.-]+(?:/[A-Za-z0-9_@.-]+)+\." + EXTS + r"\b",
                sentence,
            )
        )
    missing = []
    for t in dict.fromkeys(tokens[:40]):
        p = os.path.expanduser(t)
        if os.path.isabs(p):
            if not os.path.exists(p):
                missing.append(t)
        elif not os.path.exists(os.path.join(cwd, p)):
            missing.append(t)
    print(", ".join(missing[:10]))


if __name__ == "__main__":
    main()
