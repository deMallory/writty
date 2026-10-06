# Approval pipeline: where it stands

Goal: an approval in Mistty costs one keystroke and lands on work Writ accepts.

Steps 1 to 3 shipped as PR 49 (writty only). Step 4 is on branch
`davidmalinen/one-key-approval` in writty, and on the branch of the same name in the
mistty worktree `.claude/worktrees/one-key-approval`.

## Done

- [x] Step 1: a small change routes to patch mode (both work notices, Mistty state file)
- [x] Step 2: the pending gate's check runs before the user is asked (Stop hook
      `writ-gate-precheck.sh`, save-time plan check)
- [x] Step 3: one phrase everywhere ("Say approved to proceed."; `!mistty approve` counts
      as a request)
- [x] Step 4a (mistty): the unified harness post_agent payload carries
      `last_assistant_message`, so Writ's Stop checks read Mistty replies.
- [x] Step 4b (mistty): the approval card shows the hook's reason under its title.
- [x] Step 4c (writty): `mistty ask` gets pre_tool `ask` when the pending gate passes
      `writ-session.py gate-precheck`, and a deny with the problem when it does not.
- [x] Step 4d: a headless session has no one to answer, so Mistty denies the ask; the
      typed `approved` stays the fallback, and the state file says so.
- [x] Step 4e (writty): the post_tool of an asked `mistty ask` runs Writ's approval hook
      as `!mistty approve` does, for the gate the card named, once.

## Next, one at a time

- [ ] Merge the two step 4 PRs (writty, mistty).
- [ ] Live check in Mistty: a 1-file fix runs in patch with no approval; `mistty ask`
      after a plan opens the card with the gate and the plan, and yes advances phase-a
      in the same turn.

## Still open

- The gothic gate (`vibe/cli-rust/src/ui/gothic/gate.rs`) does not show the reason; the
  grok and plain cards do.
- The audit row logs a card approval as `approval_evidence_override`, as
  `!mistty approve` does. A source label would touch the approval hook.
- The card binds plan.md's hash, as the approval token does; for test-skeletons a
  test file rewritten while the card is open is not caught.
- A declined card leaves its `<call_id>.ask` record in `/tmp/writ-vibe/<sid>/`; the next
  ask for that call id removes it, nothing else does.
- The legacy backend (`vibe/core/*`) keeps its ask text and post_agent payload: Mistty
  does not run it.

## Known failures that predate this branch

- `tests/test_debug_lens_predicate.py` fails at collection: it expects 6 modes, and
  patch mode (ce7b0a6) made 7.
- `tests/test_mode_autoroute.py::TestHookIgnoresNonUserTurns::test_task_notification_with_a_work_request_leaves_an_unset_session_unset`
  expects an unset mode; 34a4764 defaults it to conversation.
- mistty `tests/app_server/test_unified_harness_backend_adapter.py::test_unified_runtime_counts_the_hooks_the_session_compiled`
  finds an `output_style` hook it does not expect, on an untouched main checkout too.

## Left as is, on purpose

- The two "paused work restored" notices still offer `writ mode set conversation`: the
  restored cycle already holds approvals, and `mode set` would clear them.
- A refused approval stays spent: for test-skeletons, the token's plan hash does not
  cover the test files.
