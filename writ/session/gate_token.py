"""Single source for the gate-token mechanism (H2).

The gate token is written by auto-approve-gate.sh ONLY on genuine user
approval (input the agent cannot forge), so requiring it is what makes the
human the approver. The path, the read semantics (missing -> ""), the
match comparison, and consumption are security-critical and MUST be defined
once: three call sites (server advance-phase, server promote-candidate, CLI
cmd_advance_phase) previously each reimplemented the comparison, and they
had already drifted. Callers keep their own friction events, error
envelopes, and async wrapping; only the security decision lives here.
"""

import os
import uuid


def gate_token_path(session_id: str) -> str:
    # Must match the bash writer (auto-approve-gate.sh) byte-for-byte: it
    # hardcodes /tmp, as do server.py's comment and the explore.html doc. Using
    # tempfile.gettempdir() here would diverge the instant $TMPDIR is set (the
    # reader would look elsewhere than the writer wrote), fail-closing every
    # gate advance. A hardcoded /tmp guarantees writer and reader always agree.
    return os.path.join("/tmp", f"writ-gate-token-{session_id}")


def read_gate_token(session_id: str) -> str:
    """Return the on-disk gate token, or "" if absent/unreadable (fail-closed)."""
    try:
        with open(gate_token_path(session_id)) as f:
            return f.read().strip()
    except FileNotFoundError:
        # No approval outstanding: the normal state on most turns, not a failure.
        return ""
    except OSError as exc:
        # Present but unreadable is anomalous -- a fail-closed gate that should have
        # opened. Distinguished from the absent case so this stays signal, not noise.
        from writ.shared.logging import emit_exception

        emit_exception("session.gate_token.read", exc, session_id, None)
        return ""


def gate_token_valid(token: str, expected: str) -> bool:
    """True only when a non-empty supplied token matches a non-empty expected one."""
    return bool(token) and bool(expected) and token == expected


def consume_gate_token(session_id: str) -> None:
    """Remove the token: one user approval authorizes exactly one gated action."""
    try:
        os.remove(gate_token_path(session_id))
    except FileNotFoundError:
        pass  # Already consumed: the normal idempotent case.
    except OSError as exc:
        # A token that cannot be removed stays claimable, which is the one failure
        # mode that could let a single approval authorize a second action.
        from writ.shared.logging import emit_exception

        emit_exception("session.gate_token.consume", exc, session_id, None)


def claim_gate_token(session_id: str, supplied_token: str) -> bool:
    """Atomically claim the gate token: exactly one concurrent caller wins.

    The token FILE is the mutual-exclusion primitive. os.rename is atomic on
    POSIX, so of N concurrent callers renaming the same source to distinct temp
    names, exactly ONE rename succeeds; every other caller's rename raises
    FileNotFoundError (source already gone -> a subclass of OSError) and returns
    False. The winner reads the renamed file, removes it, and returns whether
    supplied_token matched the on-disk token. This makes "one user approval
    authorizes exactly one gated action" hold even under concurrent same-token
    requests (closes the advance-phase double-fire): only the claim winner runs
    the advance + side effects; every loser returns False and does nothing.

    Returns False when the token is absent, already claimed by a concurrent
    caller, or present-but-mismatched (fail-closed, mirrors gate_token_valid).
    """
    src = gate_token_path(session_id)
    claimed = f"{src}.claiming-{uuid.uuid4().hex}"
    try:
        os.rename(src, claimed)
    except OSError:
        # Absent, or another concurrent caller already won the rename.
        return False
    try:
        with open(claimed) as f:
            actual = f.read().strip()
    except OSError as exc:
        # The rename above just succeeded, so this file exists and is ours; failing
        # to read it now means the claim is lost to a real I/O fault, not contention.
        from writ.shared.logging import emit_exception

        emit_exception("session.gate_token.claim_read", exc, session_id, None)
        actual = ""
    try:
        os.remove(claimed)
    except OSError as exc:
        # Leaves a stray .claiming-* file behind; harmless per call, but it is the
        # only trace that cleanup is failing.
        from writ.shared.logging import emit_exception

        emit_exception("session.gate_token.claim_cleanup", exc, session_id, None,
                       claimed_path=claimed)
    return gate_token_valid(supplied_token, actual)
