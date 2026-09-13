---
name: writ-approve
description: Advance the current Writ workflow phase after you approve the Grok plan.
user-invocable: true
disable-model-invocation: true
---

You have been invoked because the user typed `/writ-approve`. That keystroke is the human gate token. Do not invent approval.

## Procedure

1. Materialize the Grok session plan to the repo-root artifact the phase-a validator reads:

```bash
writ grok materialize-plan --cwd "$(pwd -P)" --session "${GROK_SESSION_ID:-$SESSION_ID}"
```

Report the JSON (`ok`, `action`, `source`, `dest`, `error`) verbatim. If `ok` is false, stop. Do not advance.

2. Check the current phase via `GET /session/$SESSION_ID/current-phase` (use `$GROK_SESSION_ID` when `$SESSION_ID` is empty).

3. Advance via POST, passing the gate token and the working directory. The token at `/tmp/writ-gate-token-$SESSION_ID` is written by the approval hook ONLY when the user's prompt matched an approval pattern (`/writ-approve`, `approved`, ...). The advance route consumes it (one approval = one advance).

   `cwd` MUST be sent: the server resolves the project root from it.

```bash
SID="${GROK_SESSION_ID:-$SESSION_ID}"
TOKEN=$(cat "/tmp/writ-gate-token-$SID" 2>/dev/null)
curl -sX POST http://localhost:8765/session/$SID/advance-phase \
  -H 'Content-Type: application/json' \
  -d "{\"confirmation_source\": \"tool\", \"token\": \"$TOKEN\", \"cwd\": \"$(pwd -P)\"}"
```

   If the response is a token error, the user has not actually approved this turn. Do NOT retry or fabricate a token.

4. Confirm: `[Writ: plan advanced -> $NEW_PHASE]` (or tests, on the second approval). Report `validated` and `project_root` verbatim.

## Never

- Never advance without this command. Never advance multiple phases in one invocation.
- Never mint or write `/tmp/writ-gate-token-*` yourself.
- Never treat Grok plan-mode `a` as a Writ gate open. `a` only exits Grok plan mode. This command opens the Writ gate.
