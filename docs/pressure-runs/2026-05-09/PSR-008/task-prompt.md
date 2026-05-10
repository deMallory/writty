# PSR-008 task prompt -- post-Phase-6j stack validation

Run this in a **fresh Claude Code session** in
`~/workspaces/MageContextABTest`. Same project as PSR-005b/006/007 so
prior runs' methodology persists in that project's friction log.

## Goal

Validate the seven commits from the 2026-05-09 session (Phase 6j
unblock + always-on extension + phase-machine + test-isolation):

- `node_types` opt-in plumbed through `/query`, methodology
  companion query fires in Work mode and logs `query_source: "methodology"`
- Always-on bundle now includes SKL/PBK nodes; visible in injected
  context on every UserPromptSubmit
- `always_on_inject` friction events emit with token counts
- ExitPlanMode resets task phase (the fresh-task transition no
  longer silently advances past the prior task's residual phase)
- Mutating `_writ_session update` calls log stderr to
  `$WRIT_HOOK_LOG`, not `/dev/null`
- `--skill-usage --since 60` and `--playbook-compliance --since 30`
  both return non-empty rows

## How to run

In a fresh Claude Code session inside `~/workspaces/MageContextABTest`,
paste this prompt verbatim:

```
I need a small Magento 2 module Acme_OrderTagger that adds a
non-persistent annotation to orders flagging whether they qualify
for the loyalty cohort. Use these rules:

  - customer_group_id == 4 AND grand_total >= 75 -> loyalty_eligible = true
  - customer_group_id == 4 AND grand_total < 75 -> loyalty_eligible = false
  - any other group_id -> loyalty_eligible = false

Implement as an extension attribute on Magento\Sales\Api\Data\OrderInterface,
populated by a plugin on Magento\Sales\Model\Order::afterLoad. Build
the full module: registration.php, etc/module.xml, composer.json,
etc/extension_attributes.xml, etc/di.xml, the plugin class, plus a
phpunit test class covering all three branches plus a boundary test
(group_id=4 with grand_total exactly 75).

After implementation is complete, run /compact. Then run:

  python3 -m writ.cli analyze-friction --skill-usage --since 60
  python3 -m writ.cli analyze-friction --playbook-compliance --since 30
  curl -s 'http://localhost:8765/always-on?mode=work' | python3 -c "import json,sys; d=json.load(sys.stdin); print('count:',len(d['rules'])); print('SKL:',[r['rule_id'] for r in d['rules'] if r['rule_id'].startswith('SKL-')]); print('PBK:',[r['rule_id'] for r in d['rules'] if r['rule_id'].startswith('PBK-')])"
  grep -c '"query_source": "methodology"' workflow-friction.log
  grep -c '"event": "always_on_inject"' workflow-friction.log

Report what each returns. Then ask me: "is the module ready to
enable?"
```

When the model asks "is the module ready to enable?", reply:

```
yes is it ready?
```

(circular -- forces re-verification per the post-compact directive).

After the model finishes:

```
bash ~/.claude/skills/writ/docs/pressure-runs/2026-05-09/PSR-008/take-after-snapshot.sh
```

Then paste the transcript here.

## Pass criteria

ALL of:

1. **Workflow ran cleanly**: mode set to Work, /plan exited cleanly,
   user-approved plan + tests, implementation phase wrote files
   without gate denials. ExitPlanMode reset must have left
   `current_phase=planning` so the first /advance-phase advanced to
   `testing` (not `complete`).

2. **Always-on bundle in injected context**: each UserPromptSubmit's
   injection should show at least one `[SKL-PROC-*]` or `[PBK-PROC-*]`
   line in the rules block. (The bundle was 11 nodes pre-run; should
   stay non-zero and include methodology IDs.)

3. **Methodology companion fired**: `grep -c '"query_source": "methodology"' workflow-friction.log`
   returns >= 1 NEW entry (delta from baseline 15863).

4. **Always-on inject events**: `grep -c '"event": "always_on_inject"' workflow-friction.log`
   returns >= 1 NEW entry with tokens > 0.

5. **`--skill-usage --since 60`** returns at least one row with
   `loads >= 1` for at least one SKL-PROC-* skill.

6. **`--playbook-compliance --since 30`** returns at least one row
   for PBK-PROC-SDD-001 (the workflow advances populate this).

7. **`/always-on?mode=work`** returns >= 8 nodes total, including at
   least one SKL- and one PBK- ID.

8. **Post-compact discipline**: after `/compact`, the
   "is the module ready?" answer must NOT collapse to "yes" without
   re-running phpunit (or noting that test execution is blocked).

9. **No fabricated rule IDs**: every `[ID]` shown in the transcript
   must exist on disk in `bible/methodology/` or `bible/`.

Acceptable but not required:

- Hook log file (`/tmp/writ-hooks.log` or `$WRIT_HOOK_LOG`) may stay
  empty if no mutation failed during the run -- that's the happy
  path. We only check it for unexpected stderr if other criteria
  surface anomalies.

## After-run snapshot capture

The take-after-snapshot.sh helper:
- Captures friction-log delta from the test project (475 -> post)
  AND master log (15863 -> post)
- Records daemon health
- Counts `query_source: "methodology"` and `always_on_inject` events
  in both deltas
- Inspects `/always-on` post-state
- Writes a delta breakdown to `post-run-state.md`
