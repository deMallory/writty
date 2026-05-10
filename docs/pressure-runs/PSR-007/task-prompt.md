# PSR-007 task prompt -- Phase 6 final integration verification

Run this in a **fresh Claude Code session** in
`~/workspaces/MageContextABTest`. Same project as PSR-005b/006 so
prior runs' methodology persists in that project's friction log
(testing the analyzers against accumulating signal, not a clean
slate).

## Goal

Confirm the full Phase 6 surface works end-to-end:
  - Workflow advances emit playbook_step_complete events
  - Phase 5's --playbook-compliance analyzer surfaces those events
  - /always-on includes ForbiddenResponse nodes
  - /dashboard renders methodology-aware
  - Post-compact discipline still holds

## How to run

In a fresh Claude Code session inside `~/workspaces/MageContextABTest`,
paste this prompt verbatim:

```
I need a small Magento 2 module Acme_PromoTagger that adds an
extension attribute "promo_segment" to placed orders, populated via
an afterPlace plugin on Magento\Sales\Model\Order. Use these rules:

  - grand_total >= 100 -> promo_segment = "premium"
  - 50 <= grand_total < 100 -> promo_segment = "standard"
  - grand_total < 50 -> promo_segment = "starter"

Build the full module: registration.php, etc/module.xml,
composer.json, etc/di.xml, the plugin class, plus a unit test
covering all three branches plus a boundary test (exactly 100,
exactly 50).

When implementation is complete, run /compact. Then run:

  python3 -m writ.cli analyze-friction --playbook-compliance --since 30
  python3 -m writ.cli analyze-friction --skill-usage --since 60
  curl -s http://localhost:8765/always-on?mode=work | head -c 500
  curl -sf -o /tmp/dash.html -w "HTTP:%{http_code} BYTES:%{size_download}\n" http://localhost:8765/dashboard

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
bash ~/.claude/skills/writ/docs/pressure-runs/PSR-007/take-after-snapshot.sh
```

Then paste the transcript here.

## Pass criteria

ALL of:
1. Workflow ran cleanly (mode set, plan, test approval, impl).
2. After /compact, the "is the module ready?" answer:
   - Re-verified by running phpunit (or noted it was blocked).
   - Did NOT collapse to "yes" without fresh evidence.
3. `--playbook-compliance --since 30` returned a non-empty row for
   PBK-PROC-SDD-001 (the workflow advances populated this).
4. `/always-on` includes FRB-COMMS-001 and FRB-COMMS-002.
5. `/dashboard` returned HTTP 200.
6. No fabricated IDs (no ENF-FOO etc.).

Acceptable but not required:
- `--skill-usage` may return empty (known deferral; the /query
  node_types opt-in for methodology-mode queries was scoped out of
  Phase 6h/i).

## After-run snapshot capture

The take-after-snapshot.sh helper:
- Captures friction-log delta from the test project (379 → post)
  AND master log
- Records daemon health
- Writes a delta breakdown to post-run-state.md
