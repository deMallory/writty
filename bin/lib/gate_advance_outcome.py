"""Classify a /advance-phase response for auto-approve-gate.sh (stdlib-only).

Single source for the advance-phase outcome decision so the hook's branching is
unit-testable and not duplicated as inline python (two inline parses had already
drifted). No writ-package import (matches writ_mode_hint.py load-robustness): the
hook calls it by path even if the package is unimportable.
"""

import json
import sys


def classify(resp_text: str) -> dict:
    """Map an advance-phase response body to {outcome, phase, error}.

    outcome is 'advanced' (gate advanced; phase set), 'rejected' (server refused,
    e.g. plan.md format; error set), or 'none' (empty / unreachable / malformed --
    no gate action). Fail-closed: anything unparseable is 'none', never a raise.
    """
    text = (resp_text or "").strip()
    if not text:
        return {"outcome": "none", "phase": "", "error": ""}
    try:
        d = json.loads(text)
    except (ValueError, TypeError):
        return {"outcome": "none", "phase": "", "error": ""}
    if not isinstance(d, dict):
        return {"outcome": "none", "phase": "", "error": ""}
    error = d.get("error", "")
    if error:
        return {"outcome": "rejected", "phase": "", "error": str(error)}
    if d.get("advanced") is False and d.get("reason"):
        return {"outcome": "noop", "phase": str(d.get("phase", "")), "error": ""}
    if d.get("advanced", True) is False:
        return {"outcome": "rejected", "phase": "", "error": str(error or "advance rejected")}
    phase = d.get("phase", "")
    if phase:
        return {"outcome": "advanced", "phase": str(phase), "error": ""}
    return {"outcome": "none", "phase": "", "error": ""}


if __name__ == "__main__":
    data = sys.stdin.read() if len(sys.argv) < 2 else sys.argv[1]
    r = classify(data)
    # Tab-separated so the bash caller can `cut -f1/-f2/-f3-`.
    print(f"{r['outcome']}\t{r['phase']}\t{r['error']}")
