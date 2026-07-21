# Efficacy A/B harness -- Phase 2 runbook (run only when you want a measurement)

`writ efficacy-ab` is the NUMERATOR instrument from WRIT-TOKEN-BLUEPRINT.md. It measures whether a
Writ rule actually changes agent behavior (catches a planted defect) and at what total cost. Unlike
`writ token-audit` (which reads transcripts that already exist, for free), this one must RUN real
agentic Claude Code sessions to get a controlled Writ-on vs Writ-off comparison -- so running it
consumes your Claude Code account (the same auth/quota as interactive `claude`, not a separate API
key or invoice). Nothing here runs automatically. This doc is the procedure for the day you decide a
specific rule or lever needs efficacy evidence.

## Status

- Phase 1 (the instrument) is BUILT + committed: `f54ddd0` on branch `regression-fixes`.
  - `writ/analysis/efficacy_ab.py`, `writ/analysis/variants.py`, the `efficacy-ab` CLI command,
    `tests/test_efficacy_ab.py` (39 offline unit tests).
- The task-suite fixture exists on disk but is UNCOMMITTED:
  `tests/efficacy_suite/defect_idor/` + `tests/efficacy_suite/clean_listing/`.
  Each `repo/` currently carries a nested `.git`; that is harmless (`run_task` re-inits the throwaway
  copy), but if you want the suite committed, remove the nested `.git` dirs first so they do not
  commit as embedded repos.
- Phase 2 (actually running it) = this runbook. NOT yet run. Zero spend so far.

## When to run it

Only when you are about to ship an efficacy-affecting lever (summary-mode default, Layer-0 placement,
gate-on/off) and need to prove it holds defect-catching while lowering cost. The blueprint calls this
PERIODIC, not per-change. Do not wire it into CI or a loop.

## Cost + guardrails (read before --live)

- The CLI DEFAULTS to a dry-run: it prints the run plan + a cost estimate and spawns nothing.
- `--live` is the ONLY path that spawns real `claude` runs. `--reps` defaults to 1.
- Increment-1 smoke = 2 tasks x 2 variants x 1 rep = 4 runs, estimated ~$1.20+ equivalent
  (a trivial run measured ~$0.28; real defect-arm runs cost more).
- The smallest honest loop-proof is 1 task x 2 variants x 1 rep = 2 runs (~$0.60 equivalent).

## Prerequisites

1. The live Writ daemon must be up for the writ-on arm to inject rules:
   `systemctl --user restart writ-server` (NOT `kill -9` -- that fights systemd auto-restart).
2. The suite fixture must exist at `tests/efficacy_suite/` (it does; see Status).
3. Run from the repo root: `~/.claude/skills/writ`.

## Step 0 -- dry run (free, confirms the plan)

```
cd ~/.claude/skills/writ
.venv/bin/writ efficacy-ab tests/efficacy_suite
# expect: "DRY RUN: 4 runs (2 tasks x 2 variants x 1 reps). Est ~$1.20+ ...", exit 0, no spawn
```

## Step 1 -- build-spikes (resolve BEFORE trusting --live; ~2 trivial runs of spend)

These two unknowns were flagged during design and must be confirmed empirically once, because the
writ-off arm and the writ-on arm depend on them:

- B1 -- does `claude --settings <file>` MERGE with `~/.claude/settings.json` or REPLACE it?
  Probe: run the same trivial prompt twice, once with `--settings <a no-hooks.json>` and once
  without, and confirm via the transcript whether Writ hooks fired. The generated `no-hooks.json`
  already carries a permission allow-list so it is safe under either semantics; this probe only
  confirms which one is in effect (it changes nothing about the code, just your confidence).
- B2 -- does the writ-ON arm actually inject rules? After restarting the daemon, run one writ-on
  task and confirm a `rag_query` / `always_on_inject` event lands in that run's per-run friction log
  (the variant profile sets `WRIT_FRICTION_LOG` to an isolated path). If no injection event appears,
  the writ-on arm is measuring nothing and the comparison is invalid.

## Step 2 -- the live run

```
cd ~/.claude/skills/writ
.venv/bin/writ efficacy-ab tests/efficacy_suite --live            # 4 real runs, mechanical scoring
# add --judge to enable the LLM-judge fallback for ambiguous defect-caught cases (more spend)
# add --json for machine-readable output
```

Output is a 2x2: per (arm/variant) the mean total cost + defect-caught rate, plus a verdict block.

## How to read the result

- `defect/writ-on` vs `defect/writ-off`: did the planted IDOR get caught with Writ vs without?
  `signal` is labeled `gate` (a mandatory rule denied the write -- binary, trustworthy) or `judge`
  (the LLM judge read the diff -- softer, audit it).
- `clean/*`: cost-of-presence. A gate firing on the clean task is a FALSE positive (`spurious_gate`).
- VERDICT at reps=1 will be `insufficient_n` BY DESIGN -- one draw cannot beat agentic
  non-determinism. Treat a single run as a smoke test that the loop works, NEVER as a lever verdict.

## Known nuance (do not misread the verdict)

`compare_arms`' generic verdict is "pass = cost DROPS and defect-caught HOLDS." That fits the later
summary-vs-full lever (summary should be cheaper and still catch). It does NOT fit writ-on/off
directly: Writ deliberately spends MORE to BUY coverage, so "writ-on costs more" is expected, not a
failure. For the writ-on/off comparison, read the two numbers (does writ-on catch more? at what cost
premium?) rather than the pass/fail flag. Per-lever verdict semantics are deferred work (below).

## Deferred before this is a real gate (not just a smoke)

- N-rep distribution + a noise floor (the blueprint's "compare distributions, not single runs");
  pick `--reps` >= a configured floor and report a confidence interval, not a point.
- Broader defect suite (N+1, write-before-plan, SQL-injection -- 8 more candidates already
  identified) so a lever is judged on more than one defect class.
- The full-vs-summary and Layer-0 levers as variant profiles -- these need a server-side
  `render_mode` query param that does NOT exist yet (server.py hardcodes summary).
- Per-lever verdict semantics (see the nuance above).
- A hardened/cheaper LLM judge (rubric calibration, agreement-vs-human measurement).
