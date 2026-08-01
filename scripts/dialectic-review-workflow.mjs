// Dialectic clean-code review workflow (Claude Code dynamic workflow)
// ====================================================================
// Reviews a plan (design document) or code (diff / file set) through a
// dialectic structure adapted from the elenchus playbook
// (PBK-EDIT-ELENCHUS-001): a thesis agent steelmans the work, two
// antithesis agents critique it adversarially, refuting verifiers kill
// plausible-but-wrong findings, and a synthesis stage reconciles every
// tension into a verdict. The workflow reports; it never edits files.
//
// Design principles baked in:
//   - Dialectic independence: thesis and the two antithesis reviewers are
//     mutually blind. None sees another's output. They run in parallel.
//   - External point of view: one antithesis reviewer is prompted as a
//     senior developer seeing the project for the first time. It receives
//     raw content only: no corpus rules, no project jargon, no rule IDs in
//     its schema. Insider blind spots are its whole job.
//   - Rule grounding: the internal reviewer cites Writ corpus rules
//     (CLEAN-*, DRY-*, ERR-*, SOLID-*, ARCH-*) retrieved live from the
//     Writ server, with a hardcoded high-severity fallback when the server
//     is down OR returns an empty rule set (an empty set is treated as
//     degraded, not as "no rules apply").
//   - Findings must survive refutation: every antithesis finding passes an
//     adversarial verify stage before synthesis. Default is skepticism.
//   - Pattern recommendations are guarded: a dedicated check judges every
//     recommended design pattern on scale, simplicity, and proportionality,
//     so pattern-for-pattern's-sake advice dies before the report.
//   - Review ordering per ENF-PROC-SDD-001: structural/compliance concerns
//     are ordered before quality/style concerns in the final output.
//
// How to run (from the repo root), via the Claude Code Workflow tool:
//   { scriptPath: "scripts/dialectic-review-workflow.mjs",
//     args: { mode: "plan", target: "plan.md" } }
//   { scriptPath: "scripts/dialectic-review-workflow.mjs",
//     args: { mode: "code", target: "writ/server.py,writ/cli.py", base: "HEAD~3" } }
//
// Args contract:
//   mode:   'plan' | 'code'   required
//   target: string            required: file path (plan mode), or paths /
//                             branch / "." (code mode)
//   base:   string            optional, code mode only, default HEAD~1
//   focus:  string            optional lens, e.g. "error handling"
//   corpus: boolean           optional, default true; false skips the Writ
//                             server query and uses the fallback rules
//
// Returns one structured report object (see FORMAT_SCHEMA at the bottom).
// The orchestrator renders or saves it; nothing is written to the repo.

export const meta = {
  name: 'dialectic-review',
  description: 'Dialectic clean-code review of a plan or diff: thesis steelman, internal rule-grounded and external fresh-eyes antithesis, adversarial verification, synthesis into verdicts',
  phases: [
    { title: 'Gather', detail: 'read the review target; query the Writ corpus for relevant rules (fallback when down or empty)' },
    { title: 'Dialectic', detail: 'thesis steelman plus internal and external antithesis reviewers, mutually blind, in parallel' },
    { title: 'Verify', detail: 'adversarial refutation of every finding; over-engineering check on pattern recommendations' },
    { title: 'Synthesis', detail: 'reconcile thesis vs verified antithesis into verdicts, structural concerns first' },
  ],
}

// ----- args -----------------------------------------------------------------

// Some harness versions deliver args as a JSON string rather than an object.
let a = args || {}
if (typeof a === 'string') {
  try { a = JSON.parse(a) } catch { a = {} }
}
const VALID_MODES = ['plan', 'code']
if (typeof a.mode !== 'string' || !VALID_MODES.includes(a.mode)) {
  return {
    error: `args.mode must be one of ${JSON.stringify(VALID_MODES)}, got ${JSON.stringify(a.mode)}`,
    usage: { mode: "'plan' | 'code' (required)", target: 'string (required)', base: 'string (code mode, default HEAD~1)', focus: 'string (optional)', corpus: 'boolean (default true)' },
  }
}
if (typeof a.target !== 'string' || a.target.trim() === '') {
  return {
    error: `args.target must be a non-empty string (file path, comma-separated paths, branch, or "."), got ${JSON.stringify(a.target)}`,
    usage: { mode: "'plan' | 'code' (required)", target: 'string (required)', base: 'string (code mode, default HEAD~1)', focus: 'string (optional)', corpus: 'boolean (default true)' },
  }
}
const mode = a.mode
const target = a.target.trim()
const base = typeof a.base === 'string' && a.base.trim() !== '' ? a.base.trim() : 'HEAD~1'
const focus = typeof a.focus === 'string' && a.focus.trim() !== '' ? a.focus.trim() : null
const useCorpus = a.corpus !== false

// ----- shared constraints ---------------------------------------------------

const READONLY = `Constraints, non-negotiable:
- This is a REVIEW. Do not modify, create, or delete any file in the repo. No git commands that change state (no checkout, no stash, no commit). Read-only commands only: git diff, git show, git log, git ls-files, cat, grep, wc.
- Do not start or stop any server, container, or database.
- Every finding or claim about the target MUST carry a location (file:line, section heading, or diff hunk) and the actual text or code it refers to. A finding with no evidence is worth less than no finding: drop it.
- Do not fabricate findings to appear thorough. If the target is clean on some axis, say so.
- Return ONLY the structured data via the required schema. No prose outside the fields.`

// ----- fallback rules (verified against bible/ on 2026-08-01) ---------------
// Used when the Writ server is unreachable OR returns zero rules. IDs and
// statements are copied verbatim from bible/code-quality/rules.md and
// bible/architecture/rules.md.

const FALLBACK_RULES = [
  { id: 'CLEAN-FUNC-001', domain: 'code-quality', severity: 'High', statement: 'Functions do one thing. Command-Query Separation: a function either returns a computed value (query) or mutates state (command), never both. Functions that mutate-and-return are split.' },
  { id: 'CLEAN-NAME-001', domain: 'code-quality', severity: 'Medium', statement: 'Identifiers use descriptive, domain-meaningful names. Single-letter names are reserved for loop counters (i, j, k) and short lambda parameters. Abbreviations are reserved for established conventions (id, url, http).' },
  { id: 'CLEAN-NEST-001', domain: 'code-quality', severity: 'High', statement: 'Maximum nesting depth is 3 levels. Deeper code is extracted via early returns, guard clauses, or helper functions. Pyramids of doom are violations.' },
  { id: 'CLEAN-MAGIC-001', domain: 'code-quality', severity: 'High', statement: 'Magic literals are extracted to named constants with domain context. Numbers like 86400, 1000, 3, strings like admin or success are replaced with named constants.' },
  { id: 'CLEAN-ERR-001', domain: 'code-quality', severity: 'High', statement: 'No empty catch blocks. Caught exceptions are either re-raised (preserving cause), logged with full context, or converted to a domain-specific error type. Swallowing exceptions silently is forbidden.' },
  { id: 'CLEAN-SIDE-001', domain: 'code-quality', severity: 'High', statement: 'Functions named as getters, computers, builders, or formatters (get_*, compute_*, build_*, to_*, as_*, format_*) have no side effects: no I/O, no mutation of arguments, no state changes. Naming and behavior agree.' },
  { id: 'CLEAN-COUPLING-001', domain: 'code-quality', severity: 'High', statement: 'Modules depend on abstractions (interfaces, protocols, base classes), not concrete implementations. Direct construction of concrete classes inside business logic is a violation; dependencies are injected.' },
  { id: 'CLEAN-DEAD-001', domain: 'code-quality', severity: 'Medium', statement: 'No unreachable code, unused imports, unused variables, or unused functions in committed code.' },
  { id: 'DRY-DUP-001', domain: 'code-quality', severity: 'High', statement: 'Duplicated logic of 5+ substantively identical lines must be extracted to a shared function or module. Cosmetic differences (variable names, formatting) do not exempt duplication.' },
  { id: 'DRY-CONFIG-001', domain: 'code-quality', severity: 'High', statement: 'Each configuration value has exactly one source of truth (env var, config file, constants module, feature-flag service). Multiple definitions across files are violations.' },
  { id: 'ERR-HANDLE-001', domain: 'code-quality', severity: 'High', statement: 'Every external call is wrapped in error handling with an explicit timeout. Bare network or file calls without try/except plus timeout are violations. The handler logs, maps to a domain error, or retries deliberately.' },
  { id: 'SOLID-SRP-001', domain: 'architecture', severity: 'High', statement: 'Each class has exactly one reason to change. A class that handles both HTTP parsing and business logic, both persistence and validation, both presentation and computation, is split.' },
  { id: 'SOLID-OCP-001', domain: 'architecture', severity: 'High', statement: 'Behavior is extended via composition, strategy, plugin/extension hooks, or framework-native mechanisms (decorators, observers, middleware). Modifying existing code to support a new variant is a violation.' },
  { id: 'SOLID-DIP-001', domain: 'architecture', severity: 'High', statement: 'High-level modules depend on abstractions (protocols, interfaces, ABCs), not on concrete implementations. The abstraction is owned by the high-level module; the implementation conforms to it.' },
  { id: 'ARCH-BOUNDARY-001', domain: 'architecture', severity: 'High', statement: 'External service calls are wrapped in an adapter/client class. Business logic invokes the adapter, never the raw HTTP/SDK call. The adapter centralizes retries, timeouts, error mapping, and observability.' },
  { id: 'ARCH-LAYER-001', domain: 'architecture', severity: 'High', statement: 'Layer boundaries are enforced: presentation calls service, service calls data-access. Layers are not skipped. The dependency graph flows in one direction.' },
]

// ----- schemas --------------------------------------------------------------

const TARGET_SCHEMA = {
  type: 'object',
  properties: {
    purpose: { type: 'string', description: 'one-paragraph summary of what the target does or proposes' },
    scope: { type: 'array', items: { type: 'string' }, description: 'files or areas touched' },
    key_decisions: { type: 'array', items: { type: 'string' } },
    open_questions: { type: 'array', items: { type: 'string' }, description: 'ambiguities or unstated assumptions' },
    raw_excerpt: { type: 'string', description: 'verbatim representative content, max ~250 lines; the raw material, not a paraphrase' },
    excerpt_is_partial: { type: 'boolean', description: 'true if raw_excerpt omits part of the target' },
  },
  required: ['purpose', 'scope', 'key_decisions', 'raw_excerpt', 'excerpt_is_partial'],
}

const CORPUS_SCHEMA = {
  type: 'object',
  properties: {
    rules: {
      type: 'array',
      items: {
        type: 'object',
        properties: {
          id: { type: 'string' },
          domain: { type: 'string' },
          severity: { type: 'string' },
          statement: { type: 'string' },
        },
        required: ['id', 'statement'],
      },
    },
    source: { type: 'string', description: '"corpus" if rules came from the server, "empty" if the server answered with zero rules, "unreachable" if curl failed' },
    query_used: { type: 'string' },
  },
  required: ['rules', 'source', 'query_used'],
}

const THESIS_SCHEMA = {
  type: 'object',
  properties: {
    core_intent: { type: 'string' },
    strengths: {
      type: 'array',
      items: {
        type: 'object',
        properties: {
          claim: { type: 'string' },
          evidence: { type: 'string' },
          rule_ids: { type: 'array', items: { type: 'string' } },
        },
        required: ['claim', 'evidence'],
      },
    },
    patterns_used: {
      type: 'array',
      items: {
        type: 'object',
        properties: {
          pattern: { type: 'string' },
          where: { type: 'string' },
          appropriate: { type: 'boolean' },
        },
        required: ['pattern', 'where', 'appropriate'],
      },
    },
    overall_quality: { type: 'string' },
  },
  required: ['core_intent', 'strengths', 'patterns_used', 'overall_quality'],
}

const INTERNAL_FINDINGS_SCHEMA = {
  type: 'object',
  properties: {
    findings: {
      type: 'array',
      items: {
        type: 'object',
        properties: {
          concern_type: { type: 'string', enum: ['structural', 'quality'] },
          severity: { type: 'string', enum: ['critical', 'important', 'minor'] },
          description: { type: 'string' },
          location: { type: 'string' },
          rule_id: { type: ['string', 'null'] },
          recommended_pattern: { type: ['string', 'null'] },
          evidence: { type: 'string' },
        },
        required: ['concern_type', 'severity', 'description', 'location', 'evidence'],
      },
    },
    summary: { type: 'string' },
  },
  required: ['findings', 'summary'],
}

const EXTERNAL_FINDINGS_SCHEMA = {
  type: 'object',
  properties: {
    findings: {
      type: 'array',
      items: {
        type: 'object',
        properties: {
          concern: { type: 'string', enum: ['clarity', 'complexity', 'maintainability', 'assumptions'] },
          severity: { type: 'string', enum: ['critical', 'important', 'minor'] },
          description: { type: 'string' },
          location: { type: 'string' },
          newcomer_impact: { type: 'string' },
          simpler_alternative: { type: ['string', 'null'], description: 'a simpler design that would do the same job, if the concern is over-engineering' },
        },
        required: ['concern', 'severity', 'description', 'location', 'newcomer_impact'],
      },
    },
    overall_impression: { type: 'string' },
    would_approve: { type: 'boolean' },
  },
  required: ['findings', 'overall_impression', 'would_approve'],
}

const REFUTE_SCHEMA = {
  type: 'object',
  properties: {
    verified: {
      type: 'array',
      items: {
        type: 'object',
        properties: {
          original_finding_index: { type: 'integer' },
          status: { type: 'string', enum: ['confirmed', 'refuted', 'unverified'] },
          refutation: { type: ['string', 'null'] },
          adjusted_severity: { type: ['string', 'null'] },
          notes: { type: 'string' },
        },
        required: ['original_finding_index', 'status', 'notes'],
      },
    },
    overall_verdict: { type: 'string', enum: ['all_confirmed', 'some_refuted', 'mostly_refuted', 'no_findings'] },
  },
  required: ['verified', 'overall_verdict'],
}

const PATTERN_CHECK_SCHEMA = {
  type: 'object',
  properties: {
    checks: {
      type: 'array',
      items: {
        type: 'object',
        properties: {
          pattern: { type: 'string' },
          source: { type: 'string', enum: ['internal', 'external'] },
          verdict: { type: 'string', enum: ['appropriate', 'over-engineering', 'insufficient-context'] },
          reasoning: { type: 'string' },
        },
        required: ['pattern', 'source', 'verdict', 'reasoning'],
      },
    },
    flagged_count: { type: 'integer' },
  },
  required: ['checks', 'flagged_count'],
}

const RECONCILE_SCHEMA = {
  type: 'object',
  properties: {
    verdicts: {
      type: 'array',
      items: {
        type: 'object',
        properties: {
          type: { type: 'string', enum: ['confirmed_finding', 'confirmed_strength', 'rejected_critique', 'trade_off'] },
          concern_type: { type: 'string', enum: ['structural', 'quality'] },
          severity: { type: ['string', 'null'] },
          description: { type: 'string' },
          evidence: { type: 'string' },
          rule_ids: { type: 'array', items: { type: 'string' } },
          recommended_fix: { type: ['string', 'null'] },
          recommended_pattern: { type: ['string', 'null'] },
          rejection_reason: { type: ['string', 'null'] },
          trade_off_thesis: { type: ['string', 'null'] },
          trade_off_antithesis: { type: ['string', 'null'] },
        },
        required: ['type', 'concern_type', 'description', 'evidence'],
      },
    },
    tensions_resolved: { type: 'integer' },
  },
  required: ['verdicts', 'tensions_resolved'],
}

const FORMAT_SCHEMA = {
  type: 'object',
  properties: {
    executive_summary: { type: 'string', description: '3-5 sentences' },
    confirmed_findings: {
      type: 'array',
      description: 'ordered: structural concerns first, then quality, per ENF-PROC-SDD-001',
      items: {
        type: 'object',
        properties: {
          concern_type: { type: 'string' },
          severity: { type: 'string' },
          description: { type: 'string' },
          location: { type: 'string' },
          rule_ids: { type: 'array', items: { type: 'string' } },
          recommended_fix: { type: 'string' },
          recommended_pattern: { type: ['string', 'null'] },
        },
        required: ['concern_type', 'severity', 'description', 'location', 'recommended_fix'],
      },
    },
    confirmed_strengths: {
      type: 'array',
      items: {
        type: 'object',
        properties: {
          description: { type: 'string' },
          evidence: { type: 'string' },
          rule_ids: { type: 'array', items: { type: 'string' } },
        },
        required: ['description', 'evidence'],
      },
    },
    rejected_critiques: {
      type: 'array',
      items: {
        type: 'object',
        properties: {
          original_critique: { type: 'string' },
          rejection_reason: { type: 'string' },
        },
        required: ['original_critique', 'rejection_reason'],
      },
    },
    trade_offs: {
      type: 'array',
      items: {
        type: 'object',
        properties: {
          description: { type: 'string' },
          thesis_side: { type: 'string' },
          antithesis_side: { type: 'string' },
        },
        required: ['description', 'thesis_side', 'antithesis_side'],
      },
    },
    stats: {
      type: 'object',
      properties: {
        findings_confirmed: { type: 'integer' },
        findings_rejected: { type: 'integer' },
        strengths_confirmed: { type: 'integer' },
        trade_offs: { type: 'integer' },
        patterns_recommended: { type: 'integer' },
        patterns_flagged_overengineering: { type: 'integer' },
      },
      required: ['findings_confirmed', 'findings_rejected', 'strengths_confirmed', 'trade_offs', 'patterns_recommended', 'patterns_flagged_overengineering'],
    },
  },
  required: ['executive_summary', 'confirmed_findings', 'confirmed_strengths', 'rejected_critiques', 'trade_offs', 'stats'],
}

// ----- prompt builders ------------------------------------------------------

function readTargetPrompt() {
  const focusLine = focus ? `\nThe review has a declared focus: "${focus}". Weight your summary and excerpt selection toward it.` : ''
  if (mode === 'plan') {
    return `${READONLY}

Read the design document at "${target}" (repo-relative). Summarize its stated purpose, scope (files or areas it touches), key design decisions, and any ambiguities or unstated assumptions you notice.${focusLine}

For raw_excerpt: include the document verbatim if it is under ~250 lines; otherwise include the most decision-dense sections verbatim and set excerpt_is_partial true. The excerpt must be raw source text, not your paraphrase: a later reviewer who has never seen this project judges the document from your excerpt alone.`
  }
  return `${READONLY}

Characterize the code under review. Target: "${target}". Base ref: "${base}".
- If target is "." or a comma-separated list of paths: run \`git diff ${base}..HEAD -- <paths>\` (all paths if "."). If the diff is empty, read the files themselves instead and say so in purpose.
- If target names a branch or ref: run \`git diff ${base}..${target}\`.
- If it is ambiguous whether target is a ref or paths, disambiguate first with \`git rev-parse --verify --quiet ${target}\`: success means it is a ref.

Summarize what changed, the apparent intent of each change, the files touched (scope), key design decisions visible in the code, and open questions.${focusLine}

For raw_excerpt: include the diff (or file contents) verbatim up to ~250 lines, preferring complete hunks over fragments; set excerpt_is_partial true if you had to cut. The excerpt must be raw source, not paraphrase: a later reviewer who has never seen this project judges the code from your excerpt alone.`
}

function corpusPrompt() {
  const q = focus
    ? `${focus} in a ${mode === 'plan' ? 'design plan' : 'code change'}`
    : `clean code review: function size, naming, nesting, error handling, coupling, duplication, architecture boundaries in a ${mode === 'plan' ? 'design plan' : 'code change'}`
  return `${READONLY}

Retrieve clean-code and architecture rules from the Writ server. Run exactly these two commands:

curl -s -f --connect-timeout 1 --max-time 5 -X POST http://localhost:8765/query -H 'Content-Type: application/json' -d '{"query": ${JSON.stringify(q)}, "domain": "code-quality", "budget_tokens": 3000}'

curl -s -f --connect-timeout 1 --max-time 5 -X POST http://localhost:8765/query -H 'Content-Type: application/json' -d '{"query": ${JSON.stringify(q)}, "domain": "architecture", "budget_tokens": 2000}'

Parse the JSON responses. Each response has a "rules" array; collect every rule's rule_id, domain, severity, and statement into the output "rules" array (deduplicate by id).

Set "source":
- "corpus" if at least one rule came back
- "empty" if both curls succeeded but returned zero rules combined (report this honestly; do not invent rules)
- "unreachable" if curl failed (non-zero exit, connection refused, timeout)

Set "query_used" to ${JSON.stringify(q)}. Do not retry more than once per command. Do not query any other endpoint.`
}

function rulesBlock(rules) {
  const lines = rules.map((r) => `- ${r.id} [${r.domain || '?'} / ${r.severity || '?'}]: ${r.statement}`)
  return `RULES CONTEXT (Writ corpus):\n${lines.join('\n')}`
}

function targetBlock(t) {
  return `TARGET SUMMARY:
Purpose: ${t.purpose}
Scope: ${(t.scope || []).join(', ')}
Key decisions: ${(t.key_decisions || []).join(' | ')}
Open questions: ${(t.open_questions || []).join(' | ') || 'none noted'}

TARGET CONTENT${t.excerpt_is_partial ? ' (partial excerpt)' : ''}:
${t.raw_excerpt}

The content above${t.excerpt_is_partial ? ' is a partial excerpt;' : ' may omit context;'} when you need more, read the actual files in the repo (read-only). Never cite a location you have not seen.`
}

function thesisPrompt(t, rules) {
  return `${READONLY}

You are the THESIS in a dialectic review: the design advocate. Articulate the strongest honest case for this ${mode === 'plan' ? 'plan' : 'code change'}. Identify:
(a) the core problem it solves and why this approach is reasonable;
(b) which clean-code and architecture principles it already follows well, citing rule IDs from the rules context where one genuinely applies;
(c) design patterns it uses appropriately (name them: Strategy, Adapter, Guard Clause, Pipeline, and so on) and whether each use is justified;
(d) strengths a hurried critic would overlook.

Be genuine, not sycophantic: a strength you cannot ground in evidence is not a strength, and if some part is merely adequate, do not praise it. Do NOT critique; that is another agent's job.

${rulesBlock(rules)}

${targetBlock(t)}`
}

function internalAntithesisPrompt(t, rules) {
  return `${READONLY}

You are the internal ANTITHESIS in a dialectic review: an adversarial reviewer who knows this project's rule corpus. Find real problems. Review in this order (ENF-PROC-SDD-001: structural before style):

1. STRUCTURAL (concern_type "structural"): does the ${mode === 'plan' ? 'plan' : 'change'} match its own stated intent? Are contracts and interfaces honored? Are layer and module boundaries respected? Are there silent scope additions, missing error paths, or unhandled failure modes?
2. QUALITY (concern_type "quality"): naming, function size and single responsibility, nesting depth, magic literals, duplication, coupling, dead code, side effects hiding behind getter-like names.

For each finding: cite the rule ID from the rules context when one applies (rule_id null otherwise), and quote the actual text or code as evidence. If a violation implies a missing design pattern (a long type-switch implies Strategy, scattered external calls imply Adapter, duplicated construction implies Factory, cross-cutting notification implies Observer), set recommended_pattern to that pattern name; otherwise null.

Severity: critical = would break or corrupt in production; important = hurts maintainability or correctness confidence; minor = style preference.

Do not fabricate findings to appear thorough. If an axis is clean, leave it out of findings and note it in summary.

${rulesBlock(rules)}

${targetBlock(t)}`
}

function externalAntithesisPrompt(t) {
  return `${READONLY}

You are a senior developer seeing this project for the FIRST TIME. You have no familiarity with its internal conventions, rule systems, or terminology, and you have deliberately been given none. Below is the raw ${mode === 'plan' ? 'design document' : 'diff/code'}${t.excerpt_is_partial ? ' (a partial excerpt)' : ''}. Judge it purely on what you can see, in plain engineering terms:

(a) Clarity: is this understandable to someone who did not build it? Are names and abstractions clear without insider context?
(b) Complexity: is the complexity proportional to the problem being solved, or over-engineered? If over-engineered, describe the simpler design in simpler_alternative.
(c) Maintainability: would you be comfortable owning this? What would bite the next person?
(d) Assumptions: what is obvious to the author but invisible to a newcomer?

For each finding, state newcomer_impact: why this matters for someone new. Quote the text or code you are reacting to in evidence via the location field plus description. Do not use any project-specific rule IDs or jargon. Finish with an honest overall impression and whether you would approve this in code review.

RAW TARGET:
${t.raw_excerpt}`
}

function refutePrompt(sourceKey, findingsObj) {
  const extra = sourceKey === 'external'
    ? `\nAdditional check for this reviewer: it reviewed as an outsider with no project context. For each "confusing" or "over-engineered" claim, check whether the confusion would survive reading the project's CLAUDE.md and the surrounding code. Convention-backed design is not a defect just because a newcomer had not met the convention yet; but "documented somewhere" does not excuse genuinely misleading names or gratuitous complexity.`
    : `\nAdditional check for this reviewer: it cited rule IDs. For each cited rule, confirm the rule actually says what the finding implies (the rules live under bible/ in this repo; grep for the rule ID). A finding stretching a rule beyond its statement is refuted.`
  return `${READONLY}

You are an ADVERSARIAL VERIFIER, not a confirmer. Below are findings from the ${sourceKey} reviewer in a dialectic code review. Try to BREAK each finding, one entry in verified[] per finding, indexed by its position in the findings array (0-based):
(a) Is the evidence real? Does the cited location actually contain what the finding claims? Check the actual file or diff in this repo, do not trust the quote.
(b) Is the severity honest, or inflated? Suggest adjusted_severity if inflated (null if fine).
(c) Is the implied fix proportionate to the problem?${extra}

Default to skepticism: confirmed only when you independently verified the evidence; refuted (with the refutation stated) when the finding is wrong or stretched; unverified when you could not check. If there are zero findings, return an empty verified[] and overall_verdict "no_findings".

FINDINGS FROM THE ${sourceKey.toUpperCase()} REVIEWER (JSON):
${JSON.stringify(findingsObj, null, 2)}`
}

function patternCheckPrompt(recs, t) {
  return `${READONLY}

You are the over-engineering guard in a dialectic code review. Below are design-pattern recommendations and simpler-alternative claims made by two reviewers about the same target. For EACH one, judge:
- Scale: is the actual complexity sufficient to warrant the pattern? A Strategy for 2 branches is over-engineering; for 5+ extensible branches it earns its keep.
- Simplicity: would a simpler move (extract function, rename, inline, delete) solve the same problem?
- Proportionality: does the pattern add more abstraction layers than the problem requires?

Verdict per item: "appropriate", "over-engineering", or "insufficient-context" (with what context is missing in reasoning). flagged_count = number of "over-engineering" verdicts. Judge against the target content below, not in the abstract.

RECOMMENDATIONS (JSON):
${JSON.stringify(recs, null, 2)}

${targetBlock(t)}`
}

// Drop bulky fields before feeding synthesis; keep what reconciliation needs.
function condenseForSynthesis(t, thesis, reviews, patternCheck) {
  const summary = { ...t }
  delete summary.raw_excerpt
  return {
    target: summary,
    thesis,
    reviews: reviews.map((r) => ({ key: r.key, findings: r.findings, verification: r.verification })),
    pattern_check: patternCheck,
  }
}

function reconcilePrompt(condensed) {
  return `${READONLY}

You are the SYNTHESIS in a dialectic review. Inputs: (1) the thesis (steelman), (2) findings from an internal rule-grounded reviewer and an external fresh-eyes reviewer, each with an adversarial verification verdict per finding, (3) an over-engineering check on every recommended pattern.

Build verdicts[]:
- Each antithesis finding whose verification status is "confirmed" becomes a confirmed_finding with a concrete recommended_fix. Carry recommended_pattern ONLY if the pattern check judged it "appropriate"; if it was flagged "over-engineering", state the simpler fix instead. Use the verifier's adjusted_severity when given. Findings from the two reviewers about the same location are merged into one verdict.
- Each finding whose status is "refuted" becomes a rejected_critique carrying the refutation.
- "unverified" findings: include as confirmed_finding only if severity critical (flag the uncertainty in description); otherwise drop them.
- Each thesis strength that no confirmed finding contradicts becomes a confirmed_strength.
- Where a confirmed finding directly contradicts a thesis strength and both sides hold real weight, produce a trade_off stating both sides instead of picking a winner arbitrarily.

concern_type: "structural" or "quality" per the internal reviewer's tag; map external-reviewer concerns to "quality" unless they describe broken contracts or scope drift (then "structural"). tensions_resolved = number of thesis-vs-antithesis contradictions you reconciled.

Verdicts, not opinions: every verdict carries evidence.

INPUTS (JSON):
${JSON.stringify(condensed, null, 2)}`
}

function formatPrompt(reconciled, corpusSource) {
  return `${READONLY}

You are the report formatter for a dialectic review. Turn the reconciliation below into the final report:
- confirmed_findings ordered with ALL structural concerns before ALL quality concerns (ENF-PROC-SDD-001), and within each group by severity (critical, important, minor).
- confirmed_strengths, rejected_critiques, trade_offs as given (deduplicated, tightened wording).
- stats computed from what you actually output (patterns_recommended counts distinct recommended_pattern values in confirmed_findings; patterns_flagged_overengineering comes from the reconciliation's dropped patterns).
- executive_summary: 3-5 sentences: what was reviewed, the overall verdict, the most important finding, the strongest strength, and the rule-grounding status. The corpus source for this run was "${corpusSource}": if that value is not exactly "corpus", you MUST state that rule grounding ran in degraded fallback mode; never claim live-corpus grounding otherwise.

Do not invent content not present in the reconciliation. No emojis. No em dashes.

RECONCILIATION (JSON):
${JSON.stringify(reconciled, null, 2)}`
}

// ----- execution ------------------------------------------------------------

phase('Gather')
log(`Dialectic review: mode=${mode} target=${target}${focus ? ` focus=${focus}` : ''}${useCorpus ? '' : ' (corpus disabled)'}`)

const [targetInfo, corpusRaw] = await parallel([
  () => agent(readTargetPrompt(), { label: 'gather:read-target', phase: 'Gather', schema: TARGET_SCHEMA }),
  () => useCorpus
    ? agent(corpusPrompt(), { label: 'gather:corpus', phase: 'Gather', schema: CORPUS_SCHEMA, effort: 'low' })
    : Promise.resolve({ rules: [], source: 'disabled', query_used: null }),
])

if (!targetInfo) {
  return { error: `Could not read the review target "${target}" in mode "${mode}". The read-target agent failed; check that the target exists.` }
}

// Fallback covers: server unreachable, server up but empty index, agent failure,
// and corpus explicitly disabled. "corpus" is the only non-degraded source.
const corpusDegraded = !corpusRaw || corpusRaw.source !== 'corpus' || corpusRaw.rules.length === 0
const rules = corpusDegraded ? FALLBACK_RULES : corpusRaw.rules
const corpusSource = corpusDegraded ? `fallback (${corpusRaw ? corpusRaw.source : 'agent-failed'})` : 'corpus'
log(`Rule grounding: ${corpusSource}, ${rules.length} rules`)

// Thesis and both antithesis reviewers are mutually blind: all three depend
// only on Gather, so they run concurrently. Each reviewer's refutation starts
// as soon as that reviewer finishes (no barrier between the two chains).
const REVIEWERS = [
  { key: 'internal', prompt: internalAntithesisPrompt(targetInfo, rules), schema: INTERNAL_FINDINGS_SCHEMA },
  { key: 'external', prompt: externalAntithesisPrompt(targetInfo), schema: EXTERNAL_FINDINGS_SCHEMA },
]

const [thesis, reviewPairs] = await parallel([
  () => agent(thesisPrompt(targetInfo, rules), { label: 'thesis:steelman', phase: 'Dialectic', schema: THESIS_SCHEMA }),
  () => pipeline(
    REVIEWERS,
    (r) => agent(r.prompt, { label: `antithesis:${r.key}`, phase: 'Dialectic', schema: r.schema }),
    (findings, r) => findings
      ? agent(refutePrompt(r.key, findings), { label: `verify:refute-${r.key}`, phase: 'Verify', schema: REFUTE_SCHEMA })
        .then((verification) => ({ key: r.key, findings, verification }))
      : null,
  ),
])

const reviews = (reviewPairs || []).filter(Boolean)
if (!thesis || reviews.length === 0) {
  return { error: `Dialectic stage incomplete: thesis ${thesis ? 'ok' : 'failed'}, ${reviews.length}/2 reviewer chains completed. Cannot synthesize.` }
}
log(`Dialectic complete: thesis + ${reviews.length}/2 verified reviewer chains`)

// Collect pattern recommendations and simpler-alternative claims for the
// over-engineering check. Skip the agent entirely when there is nothing to check.
const patternRecs = []
for (const r of reviews) {
  for (const f of r.findings.findings || []) {
    if (f.recommended_pattern) patternRecs.push({ source: r.key, pattern: f.recommended_pattern, context: f.description, location: f.location })
    if (f.simpler_alternative) patternRecs.push({ source: r.key, pattern: `simplification: ${f.simpler_alternative}`, context: f.description, location: f.location })
  }
}
for (const p of thesis.patterns_used || []) {
  if (p.appropriate === false) patternRecs.push({ source: 'internal', pattern: p.pattern, context: `thesis flagged this existing pattern use as questionable at ${p.where}`, location: p.where })
}

const patternCheck = patternRecs.length > 0
  ? await agent(patternCheckPrompt(patternRecs, targetInfo), { label: 'verify:pattern-check', phase: 'Verify', schema: PATTERN_CHECK_SCHEMA })
  : { checks: [], flagged_count: 0 }

phase('Synthesis')
const reconciled = await agent(
  reconcilePrompt(condenseForSynthesis(targetInfo, thesis, reviews, patternCheck)),
  { label: 'synthesis:reconcile', phase: 'Synthesis', schema: RECONCILE_SCHEMA },
)
if (!reconciled) {
  return { error: 'Reconciliation agent failed; partial data follows.', thesis, reviews, patternCheck }
}

const formatted = await agent(
  formatPrompt(reconciled, corpusSource),
  { label: 'synthesis:format', phase: 'Synthesis', schema: FORMAT_SCHEMA, effort: 'low' },
)
if (!formatted) {
  return { error: 'Format agent failed; reconciliation follows.', reconciled }
}

return {
  meta: {
    mode,
    target,
    base: mode === 'code' ? base : null,
    focus,
    corpus_source: corpusSource,
    rules_used: rules.length,
    reviewer_chains: reviews.length,
    external_would_approve: (reviews.find((r) => r.key === 'external') || {}).findings?.would_approve ?? null,
  },
  ...formatted,
}
