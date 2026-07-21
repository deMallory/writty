"""Approval-phrase detector for auto-approve-gate.sh (stdlib-only).

Single importable source for the approval predicate so the hook and the tests
bind to the same logic (no inline-python extraction drift). No writ-package
import (matches gate_advance_outcome.py / writ_mode_hint.py load-robustness):
the hook calls it by path even if the package is unimportable.

The caller passes an already-lowercased, already-stripped prompt (the hook's
PROMPT_LOWER and the test wrapper both lower+strip first). is_approval may
.strip() defensively but does not change the matching semantics.
"""

import re
import sys


def _levenshtein(s1: str, s2: str) -> int:
    if len(s1) < len(s2):
        return _levenshtein(s2, s1)
    if len(s2) == 0:
        return len(s1)
    prev = range(len(s2) + 1)
    for i, c1 in enumerate(s1):
        curr = [i + 1]
        for j, c2 in enumerate(s2):
            curr.append(min(prev[j + 1] + 1, curr[j] + 1, prev[j] + (c1 != c2)))
        prev = curr
    return prev[-1]


def is_approval(prompt: str) -> bool:
    """Return True if the (lowercased) prompt is a human approval signal.

    Pure function, no I/O, fail-closed: any internal error returns False so a
    hook defect degrades to "no approval detected" (the safe default).
    """
    try:
        prompt = (prompt or "").strip()

        exact = {
            'approved', 'approve', 'lgtm', 'proceed', 'go ahead',
            'looks good', 'ship it', 'yes', 'yep', 'y', 'ok', 'okay',
            'go', 'do it', 'continue', 'accepted', 'accept',
        }

        clean = re.sub(r'[.!,]+$', '', prompt.strip())

        if clean in exact:
            return True

        # Strip common prefix words and re-check exact match
        prefixes = ('ok ', 'okay ', 'sure ', 'yeah ', 'yes ', 'yep ', 'alright ')
        stripped = clean
        for p in prefixes:
            if clean.startswith(p):
                stripped = re.sub(r'^' + re.escape(p) + r'[,]?\s*', '', clean)
                break
        if stripped != clean and stripped in exact:
            return True

        fuzzy_targets = ['approved', 'approve', 'proceed', 'accepted', 'accept']
        if len(clean) <= 12:
            for target in fuzzy_targets:
                if _levenshtein(clean, target) <= 2:
                    return True

        if len(prompt) < 120:
            approval_words = r'(?:approved?|proceed|go ahead|continue|accept(?:ed)?|lgtm|looks? good|ship it)'
            prefix_words = r'(?:ok|okay|sure|yeah|yes|yep|alright)'
            patterns = [
                r'^(?:yes|yep|yeah),?\s*' + approval_words,
                r'^' + approval_words + r'\s*[.!]*$',
                r'^(?:phase\s*[a-d]|test.skeletons?)\s*(?:approved?|lgtm)\s*[.!]*$',
                r'^(?:approve|create)\s+(?:phase|gate)',
                # Prefix word + optional comma/space + approval word (+ optional trailing context)
                r'^' + prefix_words + r'[,.]?\s+' + approval_words,
                # Approval word + conjunction/comma + short trailing instruction.
                # Precision signal: user approves AND issues an instruction (not
                # a sentence merely beginning with an approval word).
                r'^' + approval_words + r'\s*(?:,|\s+(?:and|then|plus|&))\s+[\w][\w ,]*[.!]*$',
            ]
            for p in patterns:
                if re.match(p, prompt):
                    return True

        return False
    except Exception:
        return False


if __name__ == "__main__":
    arg = sys.argv[1] if len(sys.argv) > 1 else sys.stdin.read()
    sys.exit(0 if is_approval(arg) else 1)
