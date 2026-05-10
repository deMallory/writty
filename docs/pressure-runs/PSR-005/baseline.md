# PSR-005 baseline snapshot

Captured immediately before run.

## Master friction log

Path: `~/.claude/skills/writ/workflow-friction.log`
Line count at snapshot: 6987

After the run, diff against this baseline to extract events
attributable to the run. The take-after-snapshot.sh helper in
this directory captures the delta.

## Phase 5 surface state

- `writ analyze-friction` exposes six new flags: `--rule-effectiveness`, `--skill-usage`, `--playbook-compliance`, `--graduation-candidates`, `--trim-candidates`, `--quality-judge-false-positives`.
- `GET /dashboard` renders server-side HTML with auto-refresh meta tag.
- `POST /session/{id}/quality-judgment` emits `quality_judgment` friction events.
- `POST /session/{id}/active-playbook` emits `playbook_step_complete` friction events.
- `CONTRIBUTING.md` documents the monthly review ritual.
- `docs/monthly-reviews/TEMPLATE.md` provides a fill-in template.

## Tests at snapshot time

`pytest tests/test_phase5_*.py` was passing 67/67 in the prior
implementation session (cited from the implementation transcript,
not a fresh run -- the PSR-005 run will also re-verify). Per the
active post-compact directive, claiming "all tests pass" without a
fresh run here would substitute recall for evidence; the model
running PSR-005 should run tests if it needs that evidence.

## Phase 5 commit gate

Phase 5 is uncommitted. The user's gate from the Phase 4c
precedent: commit + push only after the pressure test passes.
