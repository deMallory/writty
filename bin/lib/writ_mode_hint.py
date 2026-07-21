"""Standalone, stdlib-only mode classifier for prompt auto-routing.

SOURCE OF TRUTH for classify_mode_hint. Kept as a single file with ZERO writ-package
imports so the UserPromptSubmit hook (writ-rag-inject.sh) can import it cheaply and
reliably from inside its latency-sensitive prompt-parse block. Importing the full
writ.session package chain there was intermittently failing under heavy machine load
(the import was swallowed by the block's error handling, so the auto-route silently
didn't fire). A one-file stdlib-only import removes that failure surface.

writ.session.mode_engine re-exports classify_mode_hint from here so the rest of the
system and the unit tests have a single definition.
"""

from __future__ import annotations

import re

# High-precision detection of audit/explore/research-shaped prompts, which map to
# investigate mode (the gate-light audit/explore/research engine). PRECISION over recall:
# a miss falls back to the manual mode directive, but a false positive on a build task is
# friction. We match audit as a VERB ("audit the/our/...") -- never the noun ("audit log",
# "audit trail") -- plus a small set of unambiguous security/explore/research phrases.
_INVESTIGATE_SIGNALS = re.compile(
    r"\bvulnerabilit"  # vulnerability / vulnerabilities / vulnerable
    r"|\bcwe-?\d"  # CWE-79 ...
    r"|\bcves?\b"  # CVE / CVEs
    r"|security\s+(posture|process|review|audit|assessment|risks?|gaps?|issues?|concerns?|holes?|exposure|vulnerabilit)"
    r"|\baudit\s+(the|our|this|your|all|my|for|against)\b"  # audit-as-VERB, not "audit log"
    r"|\binvestigate\b"
    r"|explore\s+(the|our|this|your)\s+(\w+\s+)?(codebase|code|project|repo|repository|module|system|architecture|structure)"
    r"|\bresearch\s+(the|our|whether|how|what|best|current|options)"
    r"|\bassess\s+(the|our|whether|how|security|risk)"
    r"|how\s+secure\b"
    r"|\bpenetration\s+test|\bpentest|\bthreat\s+model",
    re.IGNORECASE,
)


# Detection of implementation/build-shaped prompts, which map to work mode (the full
# plan -> test-skeletons -> implementation gated workflow). Auto-routing here is deliberate
# (agent self-classification proved unreliable). Recall-biased toward catching real build
# work -- a false positive only means an early "set a mode" gate the user clears with one
# `mode set conversation` -- but still gated to an action VERB + a code/artifact OBJECT so
# plain discussion / questions / reviews do not trip it.
_WORK_SIGNALS = re.compile(
    r"\b(implement|refactor|rewrite|reimplement|scaffold)\b"
    r"|\b(add|create|build|write|make|introduce|wire\s*up|set\s*up|hook\s*up|stub\s*out|extract)\s+"
    r"(a|an|the|some|new|another)?\s*(\w+[\s-]+){0,3}"
    r"(feature|function|method|class|endpoint|route|component|module|service|handler|"
    r"migration|schema|model|test|tests|hook|script|api|integration|page|form|field|"
    r"column|table|command|helper|wrapper|adapter|interface|controller|middleware|job|task|queue|cron)"
    r"|\bfix\s+(the|a|this|that|our)?\s*(\w+[\s-]+){0,2}"
    r"(bug|error|issue|crash|failure|fault|regression|typo|exception|test|build|leak|race)"
    r"|\b(change|update|modify|patch|edit|adjust|tweak)\s+(the|a|this|our)?\s*(\w+[\s-]+){0,3}"
    r"(function|method|class|code|logic|file|component|endpoint|behavior|implementation|handler|query|config|schema)"
    r"|\b(add|write)\s+(a|the|some|unit|integration|e2e)?\s*tests?\b"
    r"|\bmigrate\s+(the|our|this)\b",
    re.IGNORECASE,
)


def classify_mode_hint(prompt: str | None) -> str | None:
    """Best-effort mode suggestion from a user prompt. Returns 'investigate' for an
    audit/explore/research-shaped request, 'work' for a build/implementation request, else
    None. Pure. Investigate is checked first (an "audit and fix" request is investigation)."""
    if not prompt:
        return None
    if _INVESTIGATE_SIGNALS.search(prompt):
        return "investigate"
    if _WORK_SIGNALS.search(prompt):
        return "work"
    return None


if __name__ == "__main__":  # CLI: print the hint (or nothing) for argv[1]
    import sys

    hint = classify_mode_hint(sys.argv[1] if len(sys.argv) > 1 else "")
    if hint:
        sys.stdout.write(hint)
    sys.stdout.write("\n")
