---
name: writ-approve
description: Report the pending Writ workflow gate and how the user advances it. The advance itself is performed by the approval hook on the user's own "approved"; the agent never handles the gate token.
---

You have been invoked to check the Writ workflow gate. This command is status-only: it never advances a phase and never touches the gate token.

## Why status-only

The gate token at `/tmp/` is written by the approval hook ONLY when the user's own prompt matched an approval pattern, and the same hook posts the advance in the same turn. The Bash write gate refuses any command that names that token file, so an agent-side read + POST could only ever fail, and every failure sent the user back to retype "approved". One path remains: the user types the approval, the hook executes it.

## Procedure

1. Read the current phase via `GET /session/$SESSION_ID/current-phase` (curl is fine; this route touches no gate state).
2. If the phase is `planning` or `testing`, the artifact for that phase (plan.md, or the test skeletons) must exist and have been presented to the user. If it has not, present it now.
3. Tell the user, in one line, what the pending gate is and that typing **approved** advances it. Example: "Pending: plan.md (planning gate). Say approved to proceed."
4. If the user already approved this turn and the hook reported `REJECTED`, do NOT ask them to approve again: the approval is kept for 15 minutes. Fix the artifact; the gate retries automatically on your next write to it.

## Never

- Never read, echo, copy or POST the gate token. The hook is the only advance path.
- Never fabricate approval or advance a phase yourself. If the user has not said so, ask them.
- Never advance multiple phases in one turn. One approval = one advance.
