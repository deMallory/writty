# Dialectic review workflow

A repeatable Claude Code dynamic workflow that reviews a plan (design
document) or code (diff / file set) through a dialectic structure: a thesis
agent steelmans the work, two antithesis agents critique it adversarially,
refuting verifiers kill plausible-but-wrong findings, and a synthesis stage
reconciles every tension into a verdict. It enforces clean-code and
architecture practices, grounded in the Writ rule corpus when the server is
up. The workflow reports; it never edits files.

Script: [`scripts/dialectic-review-workflow.mjs`](../scripts/dialectic-review-workflow.mjs)

The structure adapts the elenchus playbook (`PBK-EDIT-ELENCHUS-001`: find the
question, find the antinomy, find the answer) from editorial pre-design to
code review: the Gather phase names the question (what is this work trying to
do), thesis and antithesis form the antinomy, and synthesis is the answer.

## What it does

| Phase | Agents | Output |
|---|---|---|
| Gather | `read-target`, `corpus` (parallel) | structured target summary + raw excerpt; relevant CLEAN-*/DRY-*/ERR-*/SOLID-*/ARCH-* rules from the Writ server, or the hardcoded fallback set |
| Dialectic | `thesis:steelman`, `antithesis:internal`, `antithesis:external` (parallel, mutually blind) | strongest honest case for the work; rule-grounded adversarial findings (structural before quality, per ENF-PROC-SDD-001); fresh-eyes findings from a reviewer given no project context |
| Verify | `refute-internal`, `refute-external` (each starts as soon as its reviewer finishes), `pattern-check` | per-finding verdicts (confirmed / refuted / unverified) with evidence re-checked against the repo; every design-pattern recommendation judged on scale, simplicity, proportionality |
| Synthesis | `reconcile`, then `format` | verdicts (confirmed_finding, confirmed_strength, rejected_critique, trade_off) and the final ordered report |

Design principles: **dialectic independence** (thesis and the two antithesis
reviewers never see each other's output), **external point of view** (one
reviewer is prompted as a senior developer meeting the project for the first
time: raw content only, no corpus rules, no rule IDs in its schema),
**refutation before synthesis** (a finding enters the report only after an
adversarial verifier re-checked its evidence against the repo), and
**pattern guarding** (a Strategy recommendation for a 2-branch switch dies in
the pattern check, not in the report).

## How to run

From the repo root, invoke the Claude Code `Workflow` tool with:

```
{ scriptPath: "scripts/dialectic-review-workflow.mjs",
  args: { mode: "plan", target: "plan.md" } }
```

```
{ scriptPath: "scripts/dialectic-review-workflow.mjs",
  args: { mode: "code", target: "writ/server.py,writ/cli.py", base: "HEAD~3" } }
```

```
{ scriptPath: "scripts/dialectic-review-workflow.mjs",
  args: { mode: "code", target: ".", base: "HEAD~1", focus: "error handling" } }
```

### Args

| Arg | Type | Required | Meaning |
|---|---|---|---|
| `mode` | `'plan'` or `'code'` | yes | review a design document vs a diff / file set |
| `target` | string | yes | plan mode: a file path; code mode: comma-separated paths, a branch/ref, or `"."` |
| `base` | string | no | code mode base ref, default `HEAD~1` |
| `focus` | string | no | narrows the lens, e.g. `"error handling"`, `"naming"`, `"architecture boundaries"`; also shapes the corpus query |
| `corpus` | boolean | no | default `true`; `false` skips the Writ server and uses the fallback rules directly |

Invalid args return a descriptive `{ error, usage }` object with zero agents
spawned.

## Output shape

The workflow returns one object:

- `meta`: mode, target, base, focus, `corpus_source` (`"corpus"` or
  `"fallback (unreachable | empty | disabled | agent-failed)"`), rule count,
  reviewer chain count, and `external_would_approve` (the fresh-eyes
  reviewer's raw yes/no).
- `executive_summary`: 3-5 sentences.
- `confirmed_findings[]`: ordered structural-first then quality
  (ENF-PROC-SDD-001), by severity within each group; each carries location,
  evidence-backed description, rule IDs when corpus rules apply, a concrete
  `recommended_fix`, and `recommended_pattern` only when the pattern check
  judged it appropriate.
- `confirmed_strengths[]`: thesis claims no confirmed finding contradicted.
- `rejected_critiques[]`: findings that died in refutation, with the
  refutation (kept visible, not silently dropped).
- `trade_offs[]`: tensions where both the thesis and antithesis sides hold
  real weight; both sides stated instead of a forced winner.
- `stats`: counts, including `patterns_flagged_overengineering`.

The orchestrator renders or saves the report; nothing is written to the repo.

## Rule grounding and fallback

The corpus agent queries `POST http://localhost:8765/query` twice (domains
`code-quality` and `architecture`, query built from `focus` and `mode`).
Fallback to the hardcoded 16-rule high-severity set (verbatim from
`bible/code-quality/rules.md` and `bible/architecture/rules.md`) triggers in
four cases, all reported in `meta.corpus_source`:

- the server is unreachable (curl failure),
- the server answers but returns zero rules combined (an empty index is
  treated as degraded, not as "no rules apply"),
- the corpus agent itself fails,
- `corpus: false` was passed.

The external reviewer never receives corpus rules in any case; only the
thesis, internal antithesis, and pattern-check prompts are rule-grounded.

## Known limits (by construction, not bugs)

- **The raw excerpt is capped at ~250 lines.** For large diffs the external
  reviewer judges a representative excerpt (`excerpt_is_partial` marks
  this). Narrow `target`/`base` or use `focus` for very large changes.
- **Verify agents are independent.** A refutation that would inform the
  other reviewer's verification does not propagate; that isolation is
  deliberate.
- **Unverified findings are dropped unless critical.** A finding the
  verifier could not check enters the report only at critical severity,
  flagged as uncertain.
- **Agent count is 8-10 per run** (corpus agent skipped when `corpus:
  false`; pattern check skipped when nobody recommended a pattern).
