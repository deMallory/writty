# Approval pipeline: where it stands

Goal: an approval in Mistty costs one keystroke and lands on work Writ accepts.

Steps 1 to 3 are on branch `davidmalinen/approval-pipeline` (writty only). Step 4 is a
second PR across writty and mistty.

## Done on this branch

- [x] Step 1: a small change routes to patch mode (both work notices, Mistty state file)
- [x] Step 2: the pending gate's check runs before the user is asked (Stop hook
      `writ-gate-precheck.sh`, save-time plan check)
- [x] Step 3: one phrase everywhere ("Say approved to proceed."; `!mistty approve` counts
      as a request)

## Next, one at a time

- [ ] Merge the PR.
- [ ] Live check in Mistty: a 1-file fix runs in patch with no approval; a typed
      `approved` after "Say approved to proceed." advances phase-a.
- [ ] Step 4a (mistty): add `last_assistant_message` to the PostAgentInvocation envelope.
      Until then the new Stop hook reads nothing in Mistty and lets every turn end.
- [ ] Step 4b (mistty): show the pre_tool hook's text in the approval prompt.
      `request_approval(tool_name, args, tool_call_id, required_permissions)` drops it today.
- [ ] Step 4c (writty): answer the gate approval with pre_tool `ask`, which overrides
      every grant and the bypass (`_should_execute_tool` in mistty
      `vibe/core/agent_loop/_loop.py`).
- [ ] Step 4d: check what the headless broker does with an `ask`.
- [ ] Step 4e (writty): map post_tool success of the asked `tool_call_id` to the gate
      advance.

## Known failures that predate this branch

- `tests/test_debug_lens_predicate.py` fails at collection: it expects 6 modes, and
  patch mode (ce7b0a6) made 7.
- `tests/test_mode_autoroute.py::TestHookIgnoresNonUserTurns::test_task_notification_with_a_work_request_leaves_an_unset_session_unset`
  expects an unset mode; 34a4764 defaults it to conversation.

## Left as is, on purpose

- The two "paused work restored" notices still offer `writ mode set conversation`: the
  restored cycle already holds approvals, and `mode set` would clear them.
- A refused approval stays spent: for test-skeletons, the token's plan hash does not
  cover the test files.
