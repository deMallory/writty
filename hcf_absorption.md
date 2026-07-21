# HCF Absorption Plan for Writ (verified)

Strategic, now-actionable plan produced from a competitive analysis between this
project (`~/.claude/skills/writ`) and HCF (`~/workspaces/hcf`, by Mark Shust).
Captures features Writ should absorb from HCF, existing Writ behaviors that HCF
handles better, and the places where the right move is a hybrid that takes the
best of both while preserving Writ's enforcement floor.

---

## Provenance and verification status

This revision replaces the 2026-05 strategic sketch. The original was built from
explorer-agent reports that read file excerpts; it carried a "not a verified
plan" warning. This revision was produced on **2026-06-02** from a full read of
both repositories (HCF: all 11 source files; Writ: the methodology corpus, the
rule corpus, the `writ/` Python package + `bin/`, the hooks layer, the install
and evolution docs, and the architecture extraction docs). Every "Writ today"
line below is verified against source and cites where the behavior lives.

### What changed from the unverified sketch

1. **A3 corrected.** The sketch claimed "Writ has NO discovery-first planning
   sub-phase" and that "`writ-planner` jumps to template fill-in." Both are
   false. Writ has discovery via the `writ-explorer` sub-agent (runs before the
   planner) and a nine-phase design brainstorm (`PHA-BRAIN-001..009`) that
   restates intent, surfaces unknowns, proposes 2-3 genuinely different
   approaches with trade-offs, and asks clarifying questions before synthesis.
   A3 is re-scoped from "add a discovery phase" to "add codebase-grounded
   assumption/permutation enumeration to the step Writ already has."

2. **A6 corrected.** The sketch claimed "no over-implementation guardrail." Writ
   has `ANT-PROC-TDD-001` ("test passes on first run, delete and start over").
   It frames an immediately-passing test as a test-trust / skipped-RED problem,
   not an over-implementation signal. A6 is re-scoped from "absorb a new rule"
   to "add HCF's over-implementation interpretation to the existing anti-pattern
   node," with the quantified variant deferred to H4.

3. **H5 corrected.** The sketch assumed Writ "has a more disciplined commit
   history" suitable for a conventional-commit-parsing changelog generator.
   Measured: only **3 of the last 100** commits use a `feat:` / `fix:` prefix.
   Writ's actual convention is `"<Area>: <description> (<increment-id>)"` (e.g.
   `"Debug lens: defer code-reading until runtime evidence (INV-9)"`). H5 is
   corrected: the generator must parse Writ's real convention, or the project
   adopts conventional commits going forward. Do not assume conventional commits.

4. **The seven open questions are resolved** (see the dedicated section below),
   so every effort estimate is now grounded rather than a guess.

5. **Concrete touch points (files) are listed per item**, and each item carries
   a Definition of Done so it can be picked up directly.

### Enforcement floor: do not erode (preserved from the original)

Gates, mandatory rules, authority preference, sub-agent session isolation, and
the one-time approval-token mechanism are load-bearing and are not user-tunable
by design. HCF is graceful precisely because it has no enforcement floor;
importing its choices naively would erode Writ's defining feature. Any
absorption that touches these layers must **extend Writ's primitive**, never
swap it for HCF's. The load-bearing set:

- Mechanical write-gates in `bin/lib/writ-session.py::_can_write_check`
  (design-approved, phase-a/plan, test-skeletons) and the validator hooks.
- The 30 mandatory always-on rules loaded out-of-band via `/always-on`.
- The one-time, session-keyed approval token (`/tmp/writ-gate-token-{sid}`),
  required by `cmd_advance_phase --token`; agent self-approval is blocked.
- Sub-agent isolation: `writ-subagent-start.sh` sets `is_subagent: true`, giving
  each worker its own session cache and RAG budget.
- Authority preference (human rules outrank AI rules at equal relevance).

---

## Verified baseline: what Writ has today

A factual snapshot so every item below has a checkable starting point.

| Area | Writ today (verified) | Evidence |
|---|---|---|
| Modes | conversation / debug / review / work; only Work gates writes | `SKL-PROC-MODE-001`, `_can_write_check` |
| Work gates | three sequential: design-approved, phase-a (plan), test-skeletons | `PBK-PROC-WORK-WORKFLOW-001`, `writ-session.py` |
| Discovery | `writ-explorer` sub-agent (read-only) runs before planning | `.claude/agents/writ-explorer.md` |
| Brainstorm | 9 phases incl. 2-3 alternative approaches + clarifying Qs | `PHA-BRAIN-001..009`, `*-PROC-BRAIN-001` |
| Planning | `writ-planner` writes single `plan.md` + `capabilities.md` | `.claude/agents/writ-planner.md`, `PBK-PROC-PLAN-001` |
| Plan validation | lexical placeholder gate + Haiku semantic judge | `validate-exit-plan.sh`, `writ-quality-judge.sh` |
| TDD | mandatory; production write denied without a test file w/ assertions | `PBK-PROC-TDD-001`, `validate-test-file.sh`, `ENF-PROC-TDD-001` |
| Review | spec-reviewer then code-quality-reviewer, order enforced | `ENF-PROC-SDD-001`, `writ-sdd-review-order.sh` |
| Static analysis | PHPStan/ESLint/ruff/cargo/go-vet + 6 security analyzers, wired to deny | `bin/run-analysis.sh`, `pre-validate-file.sh` |
| Orchestration | `--orchestrator` master + 6 named roles, **sequential foreground** | `PBK-PROC-ORCHESTRATOR-001`; parallel implementers forbidden (`PBK-PROC-SDD-001`) |
| Worker isolation | per-`agent_id` isolated session cache, fresh RAG budget | `writ-subagent-start.sh` |
| Project config | global only; no `writ init`; CLI has 16 commands, none scaffold | `writ/cli.py`; lone project file is `.claude/writ.json` (test paths) |
| Stack detection | language-level only, into ephemeral session cache | `writ-cwd-changed.sh` writes `cache.detected_domain` |
| Changelog | none; only a version-lockstep test (`plugin.json` == `pyproject`) | `tests/plugin/test_plugin_manifest.py` |
| Pipeline config | fixed global hook set; no project overlay | `templates/settings.json`, `hooks/hooks.json` |
| Run persistence | compaction state-preservation only; no loop driver | `writ-precompact.sh`, `writ-postcompact.sh` |
| Rule corpus | ~276 rules / 30 mandatory / ~17 domains incl. 73 security rules | `bible/`, `out-of-the-box-rules.md` |
| Evolution | propose, structural gate, frequency graduation, human promotion | `writ/gate.py`, `writ/frequency.py`, `writ review` |

---

## Absorb (HCF has, Writ doesn't)

### A1. Parallel TDD execution scheduler
- **HCF**: dependency graph in `_plan.md`, batch dispatch of TDD workers,
  status states (`pending` / `in_progress` / `completed` / `blocked`), 3-retry
  then block, terminal report `ALL_TASKS_COMPLETE` or `TASKS_BLOCKED: [003, 007]`.
- **Writ today (verified)**: sub-agent dispatch is sequential and foreground by
  design (`PBK-PROC-ORCHESTRATOR-001`: "strict sequence... do not pass
  `run_in_background=true`"). Parallel implementers are explicitly forbidden for
  shared-file conflict reasons (`PBK-PROC-SDD-001`). Writ does have parallel
  dispatch for read-only investigation (`SKL-PROC-PARALLEL-001`) and a
  hierarchical audit fan-out (`PBK-PROC-AUDIT-FANOUT-001`), but not for
  implementation.
- **Writ's way**: parallelize at the granularity of file-disjoint tasks only,
  under worktree isolation. Each worker keeps its already-supported isolated
  session cache; the orchestrator holds the single approval token and owns all
  user interaction; convergence happens at the artifact layer (per-task
  capability files merged by the orchestrator, per M1/H1), not at the cache
  layer (the cache has no multi-writer merge, see Resolved Question 1). Add
  status states and a 3-retry-then-block terminal report mirroring HCF.
- **Touch points**: new dispatcher (skill or `bin/` orchestrator) consuming the
  M1 task DAG; modify `PBK-PROC-ORCHESTRATOR-001` to add a parallel branch
  gated on file-disjointness; carve a file-disjoint exception into
  `PBK-PROC-SDD-001`; reuse `writ-subagent-start.sh` (isolation) and
  `writ-worktree-safety.sh` (per-worker worktrees).
- **Depends on**: M1 (per-task files). **Effort**: 1-2 weeks. **Risk**: high;
  parallel implementers on overlapping files corrupt state. The file-disjoint +
  worktree constraint is the safety boundary.
- **Done when**: a multi-task plan with independent tasks dispatches workers in
  parallel batches, each in its own worktree, retries a failed task up to 3
  times, blocks on the 4th, and the master emits `ALL_TASKS_COMPLETE` /
  `TASKS_BLOCKED` without any gate or token being bypassed at the master level.

### A2. `writ init` project bootstrap
- **HCF**: detects `composer.json` / `package.json` / `Cargo.toml` /
  `pyproject.toml` / `Gemfile` / `go.mod`, writes per-project config
  (`testing.md`, `code-standards.md`, `architecture.md`, `pipeline.md`).
- **Writ today (verified)**: no per-project state; all config is global.
  `writ/cli.py` has 16 commands, none of which scaffold. The only project-local
  files Writ ever reads are `.claude/writ.json` (test-path patterns, via
  `bin/lib/test_paths.py`) and the optional `.claude/phpstan-level` /
  `.claude/phpcs-standard` (via `common.sh`); Writ never creates them.
- **Writ's way**: a new `writ init` writes a single project-local hint file (the
  source of truth for "what stack are we in"), not HCF's four separate config
  docs. It records the detected stack/framework and optional linter config,
  which the existing domain system and analyzers already know how to read
  (extend the `.claude/writ.json` schema rather than inventing new files).
  This unlocks A5, A7, M4, M6.
- **Touch points**: new command in `writ/cli.py`; extend the `.claude/writ.json`
  schema in `bin/lib/test_paths.py`; reuse the marker list already in
  `common.sh::detect_project_root` and `writ-cwd-changed.sh`.
- **Depends on**: nothing. **Effort**: 2-3 days. **Risk**: low.
- **Done when**: `writ init` in a fresh repo detects the stack, writes one
  project-local hint file, and `writ-cwd-changed.sh` plus the analyzers consume
  it with no global-config change.

### A3. Codebase-grounded assumption and permutation enumeration
- **Re-scoped (see correction 1).** Writ already has discovery (`writ-explorer`)
  and a brainstorm that proposes 2-3 approaches (`PHA-BRAIN-003`). What it lacks
  is HCF's explicit step of enumerating, for each noun and verb in the request,
  the hidden design axes a senior engineer catches and a junior misses, grounded
  in what the explorer actually found in the codebase.
- **HCF**: `plan-create` Phase 1 surfaces hidden axes (schema variants, list
  structure, state semantics, auth/persistence/UI) and produces a "what I found
  vs. what you asked" diff before clarifying questions.
- **Writ's way**: add an assumption-enumeration sub-step to the explorer output
  contract and the brainstorm, feeding the categorized questions of A4. Tie
  enumerated axes to retrieved rules where one applies (a rule that mandates an
  invariant becomes a must-answer in A4).
- **Touch points**: `.claude/agents/writ-explorer.md` (output contract),
  `PHA-BRAIN-002`/`PHA-BRAIN-006` (brainstorm nodes).
- **Depends on**: pairs with A4. **Effort**: 1 day. **Risk**: low.
- **Done when**: the brainstorm presents a "found vs. asked" diff and a list of
  resolved/assumed design axes before clarifying questions are asked.

### A4. Question categorization protocol
- **HCF**: clarifying questions classified `must-answer` vs
  `will-default-if-silent`, with proposed defaults printed inline.
- **Writ today (verified)**: `PHA-BRAIN-006` requires questions batched into one
  message and forbids one-at-a-time, but there is no categorization taxonomy.
- **Writ's way**: see H2. Categorize, and tag each must-answer with the rule
  that mandates it.
- **Touch points**: `PHA-BRAIN-006`. **Depends on**: pairs with A3.
  **Effort**: 1 day. **Risk**: low.

### A5. Configurable per-project pipeline overlay
- **HCF**: `.claude/pipeline.md` declares extra agents to run at `post-plan` and
  `post-implementation` boundaries; any agent is swappable.
- **Writ today (verified)**: hooks are a fixed global set in two files
  (`templates/settings.json` for standalone, `hooks/hooks.json` for plugin); no
  project overlay; the dispatcher does not support project-local hook
  registration (Resolved Question 4).
- **Writ's way**: see H3. A validated two-tier schema; load-bearing hooks
  immutable, advisory hooks configurable.
- **Touch points**: new overlay loader; schema validated at `writ init` and on
  load; `templates/settings.json` / `hooks/hooks.json` (tier the registrations).
- **Depends on**: A2. **Effort**: 2-3 days. **Risk**: medium (security: a
  removable enforcement hook breaks the model).

### A6. Over-implementation interpretation on the existing anti-pattern
- **Re-scoped (see correction 2).** Not a new rule. `ANT-PROC-TDD-001` already
  fires on an immediately-passing test but frames it as test-trust. Add HCF's
  second reading: an immediately-passing test can also mean the previous GREEN
  step over-implemented.
- **Writ's way**: extend `ANT-PROC-TDD-001` body with the over-scope
  interpretation; advisory. Quantification is H4.
- **Touch points**: `bible/methodology/ANT-PROC-TDD-001.md`.
  **Effort**: 1 hour. **Risk**: low.

### A7. Non-destructive config sync command
- **HCF**: `project-update` diffs project config against the latest template,
  flags drift, never overwrites.
- **Writ today (verified)**: no sync command. The only sync-shaped operation is
  `writ export`, which runs the opposite direction (graph to `bible/`) and is
  destructive (overwrites the output dir).
- **Writ's way**: `writ update-project` reconciles the A2 project hint file
  against the current defaults, additive and confirm-before-write, mirroring
  HCF's non-destructive contract.
- **Touch points**: new command in `writ/cli.py`. **Depends on**: A2.
  **Effort**: 1 day. **Risk**: low.

---

## Modify (Writ has, HCF differs)

### M1. Plan file structure
- **Current (verified)**: single `plan.md` (sections `## Files`, `## Analysis`,
  `## Rules Applied`, `## Capabilities`) + `capabilities.md`. Validated by
  `validate-exit-plan.sh` (`_validate_phase_a`, single-file, Resolved Q3).
- **Modified**: `_plan.md` overview + `001-{task}.md ... NNN-{task}.md` per-task
  files. Required for A1 (workers need a task-local artifact) and for parallel
  convergence (each task owns its capability slice; the orchestrator merges).
- **Touch points**: `PBK-PROC-PLAN-001` / `SKL-PROC-PLAN-001`,
  `.claude/agents/writ-planner.md`, extend `validate-exit-plan.sh` to validate
  the overview plus iterate task files (and H1's rule cross-reference),
  `bin/lib/checklists.json` planning exit criteria.
- **Depends on**: nothing; is a prerequisite for A1. **Effort**: 2-3 days.

### M2. Pre-approval reviewer placement
- **Current (verified)**: `writ-spec-reviewer` runs on demand, per task, on the
  diff, after the implementer returns. Nothing reviews the plan before approval.
- **Modified**: auto-dispatch a plan-time gap check on `plan.md` write; bundle
  its output into the summary the user reviews. Gap-finding becomes default.
- **Writ's way**: see H6. Extend the existing spec-reviewer; do not add an agent.
- **Touch points**: `.claude/agents/writ-spec-reviewer.md`, a dispatch trigger
  in `PBK-PROC-ORCHESTRATOR-001` or a hook on `plan.md` write.
- **Effort**: half day.

### M3. Test phase discipline
- **Current (verified)**: the test-skeletons gate requires real assertions, then
  implementation proceeds without a structural over-implementation check.
- **Modified**: a PostToolUse signal during implementation that flags suspected
  over-implementation per A6/H4 (assertions-vs-LOC ratio). Hook-level, not a
  corpus change.
- **Touch points**: a new PostToolUse check or an addition to
  `writ-posttool-rag.sh` / `validate-file.sh`. **Effort**: half day (advisory).
- **Depends on**: A6 framing, H4 threshold.

### M4. Rule injection granularity (stack-within-domain)
- **Current (verified)**: domain detection is language-level
  (`composer.json -> php`, etc.) and `Rule.domain` is single-valued (Resolved
  Q6). Framework rules exist as separate bundles (`FW-M2-*`) but there is no
  framework sub-tag in the Stage-1 filter.
- **Modified**: stack-within-domain (Laravel vs Symfony, React vs Vue, Django vs
  FastAPI). Requires a framework tag on the Rule schema and Stage-1 filter
  support, fed by the A2 project hint via H7.
- **Touch points**: `writ/graph/schema.py` (Rule), `writ/retrieval/pipeline.py`
  (Stage 1), `writ-cwd-changed.sh`. **Depends on**: A2. **Effort**: 2-3 days.
  **Risk**: medium (schema migration + re-ingest).

### M5. Sub-agent roster
- **Current (verified)**: 6 roles (explorer, planner, test-writer, implementer,
  spec-reviewer, code-quality-reviewer), dispatched sequentially.
- **Modified**: add an orchestrator dispatch graph (A1). `writ-implementer`
  instances become parallelizable across file-disjoint tasks; planner and
  test-writer stay singleton per session.
- **Touch points**: `PBK-PROC-ORCHESTRATOR-001`, `PBK-PROC-SDD-001`.
  **Depends on**: A1. **Effort**: half day after A1.

### M6. Project CLAUDE.md generation
- **Current (verified)**: none. Writ renders only a global `~/.claude/CLAUDE.md`
  during install.
- **Modified**: A2 optionally writes a project `CLAUDE.md` that includes the
  project hint file.
- **Touch points**: A2's `writ init`. **Depends on**: A2. **Effort**: 1 day.

### M7. Changelog process
- **Current (verified)**: no CHANGELOG.md; commits do not follow conventional
  format (3/100, see correction 3); only a version-lockstep test exists.
- **Modified**: adopt Keep-a-Changelog format. See H5 for the generation angle
  (corrected: cannot assume conventional commits).
- **Touch points**: new `CHANGELOG.md`; optional generator under `scripts/`.
  **Effort**: 1 hour for the file, 1 day for a generator.

---

## Hybrid / New design (do not just copy HCF)

### H1. Per-task files plus rule cross-reference
HCF's plans are convention; Writ's are validated. Splitting into per-task files
(M1) opens an opportunity HCF cannot match: each task file declares the rule IDs
it depends on, and `validate-exit-plan.sh` verifies each cited rule ID exists in
the corpus via `/rule/{id}`. This makes the per-task split more rigorous than
HCF's, not just structurally similar.

### H2. Question categorization with rule authority
Beyond HCF's must-answer / will-default tags (planner judgment), tag each
must-answer with the rule that mandates it (e.g. "must-answer because
`ENF-PRE-002` requires the invariant declaration"). The categorization gains
authority: the user can challenge the rule, not just the question. Writ's
retrieval already surfaces the triggering rules, so the data is available.

### H3. Pipeline customization with two-tier permissions
HCF lets a project swap any agent. Writ cannot make enforcement hooks
user-tunable without breaking the security model (a project that removed
`auto-approve-gate.sh` could self-approve). New design: `pipeline` is a validated
schema with two tiers. **Load-bearing** (gates, mandatory-rule injection,
approval token, friction logger) cannot be removed or reordered. **Advisory**
(reviewers, custom analyzers, project linters) are user-configurable. Validated
at `writ init` and on every load.

### H4. Over-implementation: HCF's principle plus Writ's measurability
HCF says "if the test passes immediately, you wrote too much" as guidance. Writ
can make it falsifiable: track an assertions-vs-LOC ratio per task against a
threshold and flag outliers (M3). The threshold needs calibration against real
implementations, not invented numbers. Ship advisory first; harden to mandatory
only after measurement.

### H5. Changelog: HCF's format plus a generator matched to Writ's real convention
**Corrected.** HCF maintains CHANGELOG.md manually. Writ's commits do not follow
conventional commits (measured 3/100); they follow
`"<Area>: <description> (<increment-id>)"`. Two viable paths: (a) write a
generator that parses Writ's actual convention and groups by area/increment, or
(b) adopt conventional commits going forward and generate from that point on.
HCF's format wins; assuming HCF's input format would fail against Writ's history.

### H6. Plan gap-review: extend the spec-reviewer, do not add an agent
HCF's `devils-advocate` scans plans for framework gotchas, interface contracts,
data-flow and timing, and integration completeness, before the build. Writ's
`writ-spec-reviewer` reviews the diff after implementation. Rather than add a
second reviewer (a maintenance burden and a confusion vector), extend the
existing spec-reviewer with HCF's gotcha categories and dispatch it at
plan-approval time (M2). One reviewer, two trigger points.

### H7. Stack detection feeds Writ's existing domain system
HCF detects stacks via file signatures and writes per-stack config. Writ already
has language detection in `writ-cwd-changed.sh` (ephemeral, per-session,
Resolved Q5). New design: `writ init` writes a persistent project-local stack
hint; `writ-cwd-changed.sh` reads it on every cd and feeds the existing domain
system (and M4's framework tag). Single source of truth for "what stack are we
in," persistent across sessions rather than re-derived each time.

---

## Resolved open questions (the original seven, now answered)

1. **Sub-agent session-cache schema / multi-writer reconciliation.** The session
   cache is per-id JSON at `${WRIT_CACHE_DIR}/writ-session-{id}.json`. Sub-agents
   get an isolated cache keyed on `agent_id` (`writ-subagent-start.sh`),
   inheriting mode/phase/gates from the parent. There is **no multi-writer merge**
   onto a shared cache. Implication for A1: design parallel convergence at the
   artifact layer (per-task capability files merged by the orchestrator, M1/H1),
   not at the cache layer.

2. **Gate token semantics under parallel workers.** The token is one-time and
   session-keyed (`/tmp/writ-gate-token-{sid}`), created by
   `auto-approve-gate.sh`, required by `cmd_advance_phase --token`. Workers
   bypass gates entirely (`is_subagent: true` makes `_can_write_check` return
   allow), so workers need no token. The **master holds the single token** and
   enforces the gate once before dispatch. Parallel workers are safe with
   respect to the token because they never advance phases.

3. **`validate-exit-plan.sh` extensibility.** Currently a single-file phase-a
   validator (`_validate_phase_a`, 165 lines). M1/H1 require extending it to
   validate the `_plan.md` overview, iterate task files, and cross-check each
   cited rule ID via `/rule/{id}`.

4. **Hook ordering / project-local registration.** Order is baked into two
   global files (`templates/settings.json`, `hooks/hooks.json`). There is no
   project-local hook registration. A5/H3 must introduce a validated overlay
   loader; the existing global set becomes the load-bearing tier.

5. **`writ-cwd-changed.sh` re-detection and persistence.** Idempotent on repeated
   cd; writes `cache.detected_domain` into the ephemeral per-session cache; does
   not persist across sessions. H7 needs a persistent project-local hint file the
   hook reads on cd.

6. **Domain corpus segmentation.** `Rule.domain` is single-valued
   (language/universal level). Framework rules exist as separate bundles
   (`FW-M2-*`) but there is no framework sub-tag in the Stage-1 filter. M4/H7
   require either a framework tag on the Rule schema plus Stage-1 filter support,
   or modeling frameworks as their own domain values (a schema migration and
   re-ingest either way).

7. **Conventional-commit discipline.** Measured: 3 of the last 100 commits use a
   conventional prefix. Writ uses `"<Area>: <description> (<increment-id>)"`. H5
   must parse this convention or adopt conventional commits going forward.

---

## Priority, critical path, and first sprint

| Item | Type | Effort | Risk | Unlocks |
|---|---|---|---|---|
| A6 / H4: over-implementation interpretation | Modify + Hybrid | 1h advisory, 1d quantified | low | TDD discipline |
| M7 / H5: changelog | Modify + Hybrid | 1h file, 1d generator | low | release hygiene |
| A4 / H2: question categorization w/ rule authority | Absorb + Hybrid | 1d | low | planning UX |
| A3: assumption/permutation enumeration | Absorb | 1d | low | plan quality |
| M2 / H6: plan gap-review (extend spec-reviewer) | Modify + Hybrid | half day | low | plan quality |
| A2: `writ init` bootstrap | Absorb | 2-3d | low | A5, A7, M4, M6 |
| M1 / H1: plan file split + rule cross-ref | Modify + Hybrid | 2-3d | medium | A1 prerequisite |
| A5 / H3: pipeline overlay, two tiers | Absorb + Hybrid | 2-3d | medium | depends on A2 |
| M4 / H7: stack-within-domain | Modify + Hybrid | 2-3d | medium | depends on A2 |
| A7: project sync command | Absorb | 1d | low | depends on A2 |
| M6: project CLAUDE.md generation | Modify | 1d | low | depends on A2 |
| M3: over-implementation hook | Modify | half day | low | depends on A6/H4 |
| A1: parallel TDD scheduler | Absorb | 1-2wk | high | the big one |
| M5: orchestrator role graph | Modify | half day | low | depends on A1 |

**Critical path:**
- A2 (`writ init`) is the bottleneck: A5, A7, M4, M6 depend on it.
- M1 (plan file split) is the prerequisite for A1: workers need a task-local
  artifact and a per-task capability slice for parallel convergence. Do M1
  before A1.
- A1 (parallel scheduler) is the highest-value standalone item and can run in
  parallel with A2, since it operates at the orchestrator layer, not the
  project-config layer, but it must wait on M1.

**Total estimate**: 4-6 weeks for the full program. 1-2 weeks for everything
except A1 and M4.

### Ready to start: first sprint (low risk, high leverage, no dependencies)

These four ship value immediately, touch no enforcement-floor primitive, and
have zero cross-dependencies:

1. **A6 / H4 (1h)**: extend `ANT-PROC-TDD-001` with the over-implementation
   reading, advisory.
2. **A4 / H2 + A3 (2d)**: add question categorization with rule-authority tags
   and assumption enumeration to the brainstorm nodes.
3. **M2 / H6 (half day)**: extend `writ-spec-reviewer` with gotcha categories and
   dispatch at plan-approval time.
4. **M7 (1h)**: create `CHANGELOG.md` in Keep-a-Changelog format; defer the
   generator (H5) until the commit-convention decision is made.

After the first sprint, start **A2 (`writ init`)** to unlock the config-dependent
items, and **M1 (plan file split)** to set up A1. Each item above is sized,
scoped to specific files, and carries a Definition of Done where stated.

When any item becomes active implementation, it moves into a `plan.md` at the
project root with the four required sections (`## Files`, `## Analysis`,
`## Rules Applied`, `## Capabilities`), per the Work-mode workflow Writ enforces
on itself.
