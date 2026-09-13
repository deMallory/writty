---
name: writ-approve
description: Advance the current Writ workflow phase. Replaces pattern-match "approved" detection with an explicit tool-confirmed advance (plan Section 8.1).
---

You have been invoked to advance the Writ workflow phase. Confirm the user's intent is to advance, then run this command via Bash.

On Grok Build the human gesture is: approve the TUI plan with `a`, then type `/writ-approve`. The first step copies the Grok session plan to repo-root `plan.md`. The second step consumes the one-time token minted from that typed prompt.

## Procedure

1. If `$GROK_SESSION_ID` is set (Grok Build), materialize the session plan first:

```bash
writ grok materialize-plan --cwd "$(pwd -P)" --session "${GROK_SESSION_ID:-$SESSION_ID}"
```

Stop if that JSON has `"ok": false`.

2. Check the current phase via `GET /session/$SESSION_ID/current-phase`.
3. If the current phase artifact exists and was presented to the user in this or a prior turn (plan.md for planning, test skeletons for testing, etc.), proceed. Otherwise, respond: "No current phase artifact to approve. Present the artifact first."
4. Advance via POST, passing the gate token and the working directory. The token at
   `/tmp/writ-gate-token-$SESSION_ID` is written by the approval hook ONLY when the
   user's prompt matched an approval pattern, so it proves genuine user approval; the
   advance route requires it and consumes it (one approval = one advance).

   `cwd` MUST be sent: the server resolves the project root from it (that is where
   plan.md and the test skeletons are looked for), and it cannot substitute its own
   working directory, which is Writ's install dir. Omitting it makes a planning advance
   fail closed on an empty root.

```bash
TOKEN=$(cat "/tmp/writ-gate-token-$SESSION_ID" 2>/dev/null)
curl -sX POST http://localhost:8765/session/$SESSION_ID/advance-phase \
  -H 'Content-Type: application/json' \
  -d "{\"confirmation_source\": \"tool\", \"token\": \"$TOKEN\", \"cwd\": \"$(pwd -P)\"}"
```

   If the response is `{"advanced": false, ...}` with a token error, the user has not
   actually approved this turn (no token was written). Do NOT retry or fabricate a token:
   tell the user the approval was not detected and ask them to confirm explicitly.

5. Confirm to the user: "[Writ: $ARG advanced -> $NEW_PHASE]" where $ARG is what they approved (design / plan / tests) and $NEW_PHASE is the new phase name from the response. Also report the response's `validated` and `project_root` fields verbatim, so the user can see WHICH plan.md was accepted and catch a wrong project root.

## Audit trail

Each advance is recorded to `session.phase_transitions` with `confirmation_source: "tool"` AND appended to `workflow-friction.log` as a `phase_advance` event. Phase 5 telemetry distinguishes tool-confirmed from pattern-confirmed advances for rubric refinement.

## Never

- Never advance without this command (or its MCP equivalent `writ_approve`). Pattern match on "approved" in user prompts is defence in depth, not the primary path.
- Never advance multiple phases in a single invocation. One call = one advance.
- Never fabricate approval. If the user has not explicitly authorized, ask them before calling.
