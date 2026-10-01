---
name: writ-approve
description: Advance the current Writ workflow phase after you approve the Grok plan.
user-invocable: true
disable-model-invocation: true
---

You have been invoked because the user typed `/writ-approve`. That keystroke is the exact approval. Do not invent approval.

## What already happened

`auto-approve-gate.sh` runs before this command. On this prompt it copies the Grok session plan to repo-root `plan.md`, then fingerprints that file and advances the pending gate. Do not run `writ grok materialize-plan` here. A later copy changes `plan.md` out from under the fingerprint, and the advance route refuses the token.

Pressing `a` in the TUI only exits Grok plan mode. It does not open the Writ gate.

## Procedure

1. Check the current phase via `GET /session/$SID/current-phase`, where `SID` is `$GROK_SESSION_ID`, or `$SESSION_ID` when that is empty. The response reports `phase`, `next_gate` and `plan_hash`.

2. If the phase already moved, stop and confirm: "[Writ: $ARG advanced -> $NEW_PHASE]". Report `validated` and `project_root` when the advance response is still available. Do not POST again.

3. If the phase did not move, advance via POST. The token file has three lines. Send line one only.

```bash
SID="${GROK_SESSION_ID:-$SESSION_ID}"
TOKEN=$(head -1 "/tmp/writ-gate-token-$SID" 2>/dev/null)
curl -sX POST http://localhost:8765/session/$SID/advance-phase \
  -H 'Content-Type: application/json' \
  -d "{\"confirmation_source\": \"tool\", \"token\": \"$TOKEN\", \"cwd\": \"$(pwd -P)\"}"
```

   If the response is a token error, the approval hook did not mint a token. Do not retry and do not write the token file.

4. Confirm: "[Writ: $ARG advanced -> $NEW_PHASE]". Report `validated` and `project_root` verbatim.

## Never

- Never advance more than one phase in this command.
- Never mint or write `/tmp/writ-gate-token-*`.
- Never treat Grok plan-mode `a` as a Writ gate open.
