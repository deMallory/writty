"""Classify a /advance-phase response for auto-approve-gate.sh (stdlib-only).

Single source for the advance-phase outcome decision so the hook's branching is
unit-testable and not duplicated as inline python (two inline parses had already
drifted). No writ-package import (matches writ_mode_hint.py load-robustness): the
hook calls it by path even if the package is unimportable.
"""

import json
import sys


def _empty(outcome: str = "none", phase: str = "", error: str = "") -> dict:
    return {"outcome": outcome, "phase": phase, "error": error, "validated": "",
            "token_spent": ""}


def _token_spent(d: dict) -> str:
    """'true' | 'false' | '' for the hook, from the response's token_spent flag.

    Empty when the server did not say (an older daemon, or a path that never touches the
    token). The hook must not claim either way in that case: telling the user their
    approval was spent when it was not sends them to re-approve for nothing, and the
    reverse leaves them waiting on a gate that needs a fresh approval.
    """
    v = d.get("token_spent")
    if v is True:
        return "true"
    if v is False:
        return "false"
    return ""


def classify(resp_text: str) -> dict:
    """Map a response body to {outcome, phase, error, validated, token_spent}.

    outcome is 'advanced' (gate advanced; phase set), 'rejected' (server refused,
    e.g. plan.md format; error set), or 'none' (empty / unreachable / malformed --
    no gate action). Fail-closed: anything unparseable is 'none', never a raise.

    `validated` carries the project root and artifact the server actually judged, so
    the hook can name them in its confirmation line instead of an unqualified
    "approved" (a root resolved from a stray marker file is otherwise invisible).
    Empty when the server did not report them (older daemon, or a no-op).

    `token_spent` tells the hook whether the human's approval was consumed, so a refusal
    can say whether they need to approve again. See _token_spent.
    """
    text = (resp_text or "").strip()
    if not text:
        return _empty()
    try:
        d = json.loads(text)
    except (ValueError, TypeError):
        return _empty()
    if not isinstance(d, dict):
        return _empty()
    validated = _describe_validated(d)
    spent = _token_spent(d)
    error = d.get("error", "")
    if error:
        return {"outcome": "rejected", "phase": "", "error": str(error),
                "validated": validated, "token_spent": spent}
    if d.get("advanced") is False and d.get("reason"):
        return {"outcome": "noop", "phase": str(d.get("phase", "")), "error": "",
                "validated": "", "token_spent": spent}
    if d.get("advanced", True) is False:
        return {"outcome": "rejected", "phase": "",
                "error": str(error or "advance rejected"),
                "validated": validated, "token_spent": spent}
    phase = d.get("phase", "")
    if phase:
        return {"outcome": "advanced", "phase": str(phase), "error": "",
                "validated": validated, "token_spent": spent}
    return _empty()


def _describe_validated(d: dict) -> str:
    """One-line 'what did the gate actually look at', from the response fields."""
    root = str(d.get("project_root") or "")
    artifact = str(d.get("validated") or "")
    if artifact:
        tier = str(d.get("root_tier") or "")
        suffix = f" (project root from {tier})" if tier else ""
        out = f"validated {artifact}{suffix}"
    elif root:
        out = f"project root {root}"
    else:
        return ""
    # Tabs/newlines would break the tab-separated transport below (a path may
    # legally contain either), so they are flattened to spaces.
    return out.replace("\t", " ").replace("\n", " ").replace("\r", " ")


if __name__ == "__main__":
    data = sys.stdin.read() if len(sys.argv) < 2 else sys.argv[1]
    r = classify(data)
    # Tab-separated so the bash caller can cut -f1..-f4 with -f5- for the remainder.
    # `error` stays LAST because it is the only multi-line/unbounded field.
    print(f"{r['outcome']}\t{r['phase']}\t{r['validated']}\t{r['token_spent']}\t{r['error']}")
