# ADR: token-audit bills per API response, prices per model, and adds up the subagent tree

Status: accepted
Date: 2026-09-29
Plan: `.claude/plans/54fe1ac9-a554-401f-bbe7-2419043b40f2/plan.md`
Touches: `writ/analysis/token_audit.py`, `writ/analysis/token_tree.py`, `writ/cli.py`,
`writ/analysis/efficacy_ab.py`, `tests/test_token_audit_accounting.py`,
`tests/test_token_audit_tree.py`, `tests/test_efficacy_ab.py`,
`tests/fixtures/token_audit_helpers.py`

## Context

`writ token-audit` is the denominator instrument: every later model, effort or routing
experiment reads its dollar figure. Four defects made that figure wrong.

1. **Record-level double billing.** `parse_turns` appended every `type == "assistant"`
   record that carried `message.usage`. Claude Code writes one record per content block of
   a single API response, and every one of those records repeats the same `message.id` and
   the same `message.usage`. On the session that motivated this change there were 116
   assistant records but 64 unique `message.id`; output counted 105,770 against 49,675
   deduped, and cache_read 17,040,667 against 9,401,992. Every measured figure, the
   compounding curve, the compaction segments and the attributed re-read cap inherited the
   inflation.
2. **One model for the whole transcript.** Every turn was priced with the CLI `--model`
   (default `claude-opus-4-8`) times universal COST_WEIGHTS. The per-record model was
   parsed and never read, so mixed-model sessions, dated ids such as
   `claude-haiku-4-5-20251001`, and models whose cache-read ratio is not 0.1x
   (`claude-opus-5-5` at 0.05x, `claude-fable-5-1` at 0.025x) priced wrongly or not at all.
3. **Subagents ignored.** Main-thread usage lives in the main transcript; each subagent's
   usage lives only in `<session>/subagents/agent-<id>.jsonl`. The audit read only the main
   file, so all subagent spend was missing.
4. **Subagent transcripts are ephemeral.** Claude Code deletes them; after that the spend
   is unrecoverable unless something records it at SubagentStop (Task 2, appended later).

## Decision

### Billing unit: the API response, keyed by `message.id`

One response per unique `message.id`. `requestId` is not used as a key; the validation
below checks whether it maps 1:1 with `message.id`.

- Records with no `message.id` are each a separate response. Every pre-existing fixture is
  id-less, so their totals are unchanged.
- Every repeat of an id is counted in `duplicates_collapsed` (records minus responses).
  The LAST record in file order supplies usage and model, because it is the latest snapshot
  of the response. The response keeps the position of its FIRST record, so turn order for
  the compounding curve and segments is stable. The records of one id are then classified
  three ways:
  1. **Identical:** every record has the same `usage` and `model`. Collapsed silently.
  2. **Streaming snapshot:** the model is the same on every record, every non-output usage
     field is identical (`input_tokens`, `cache_read_input_tokens`,
     `cache_creation_input_tokens`, and the `cache_creation` 5m/1h split), and
     `output_tokens` never decreases across the records in file order and increases at
     least once. This is Claude Code writing a response's usage while it is still
     streaming. No warning is emitted; the response is counted once in
     `streaming_snapshot_updates`.
  3. **Conflict:** anything else, meaning the model differs, any non-output field differs,
     or output decreases at any step. A `duplicate_id_conflict` warning names the id, the
     record count and the differing fields (`usage`, `model`), and the response is counted
     in `duplicate_conflicts`.
- `measured` (main thread) and `aggregate_file_usage` (per file) both expose
  `streaming_snapshot_updates` and `duplicate_conflicts`. The per-file `conflicts` key stays
  equal to `duplicate_conflicts`, so the Task 2 summary row contract holds. The ACCOUNTING
  WARNINGS section of `render_text` prints the session-wide totals over the main thread
  plus accounted dispatches, for example `records 117, responses 62, collapsed 55,
  streaming_snapshot_updates 26, duplicate_conflicts 0`.
- Rejected: warning on every repeat whose usage differs. Streaming snapshots are the normal
  case on real transcripts, so the real conflicts would be buried under noise.
- A `message.id` seen in two files of one tree is counted once (main first, then walk
  order) and warns `cross_file_duplicate_id`. The evidence says this does not happen; it is
  an invariant check.
- `parse_turns` keeps its signature and return shape but returns deduped responses. The
  schema canary still runs on the main transcript before anything is computed, and a
  subagent or orphan file whose usage record lacks a required field raises the same
  `TokenAuditSchemaError` (CLI exit 2).

Rejected: billing per record. It is what the code did, and it double-bills every
multi-block response.

### Rate card: USD per MTok per model, five categories

`RATE_CARD` holds `input`, `output`, `cache_read`, `cache_write_5m` and `cache_write_1h`
for exactly the approved models; `"<synthetic>"` (Claude Code internal, never billed) is
all zeros and never reported as unpriced. The 5m/1h split comes from the existing
`_split_cache_creation`; an unsplit `cache_creation_input_tokens` prices as 5m, the cheaper
tier, so the figure never overstates. `INPUT_USD_PER_MTOK` is derived from the card, so its
existing keys keep their values for importers.

For opus-4-8/4-7/4-6, sonnet-4-6, haiku-4-5 and fable-5 the card equals COST_WEIGHTS times
the old input rate exactly, so on the same deduped responses the new USD equals the old
formula; a test pins this. `COST_WEIGHTS`, `weighted_cost`, `compounding_curve`,
`segment_lengths`, `attribute_writ`, `attribute_prevented` and `render_json` are unchanged
(corpus_footprint and injection_footprint import them).

Rejected: universal multipliers on a per-model input rate. They are wrong for every model
whose cache-read ratio is not 0.1x.

### Model normalization and precedence

`normalize_model(raw)` returns the exact RATE_CARD key, or the base of a trailing
`-YYYYMMDD` suffix when that base is an exact key, else None. There is no prefix or fuzzy
matching: `claude-opus-5-6` is unpriced and never priced as 5.5.

Per response, the record's `message.model` is authoritative when it is a non-empty string,
even if it does not normalize. Only a record with no model uses the `scorecard` `model`
argument (CLI `--model`) as a fallback. Anything else is UNPRICED. The CLI default changed
from `claude-opus-4-8` to None, because a default fallback silently prices model-less
records as Opus, which is a guess. `scorecard(transcript_path, friction_path, model)` keeps
its positional signature; efficacy_ab still passes `claude-opus-4-8`, which is now only a
fallback.

### Unpriced and partial semantics

- `card["unpriced"]` lists every unpriced model key (raw id, or `"<none>"` for model-less
  records) across the main thread and all accounted dispatches, with raw token counts and
  a `scope` list (`"main"` and dispatch ids). Each adds an `unpriced_model` warning.
- `measured` stays MAIN THREAD ONLY and keeps every legacy key. `measured.total_cost` is the
  unchanged COST_WEIGHTS weighted-token score over deduped responses (also exposed as
  `weighted_token_cost`). `measured.total_usd` is the priced main-thread USD when at least
  one main-thread response is priced, a floor when `usd_partial` is true, and None when no
  main-thread response is priced.
- `session.partial` is true iff the main thread or any accounted dispatch has unpriced
  usage, or any dispatch is `missing_transcript` or `missing_metadata`.
- `render_text` never presents a partial figure as the total: the TOTAL and session lines
  say PARTIAL and name the unpriced response count.

### Tree linkage (`writ/analysis/token_tree.py`)

Linkage is kept out of the pricing module. The session directory is the transcript path
without `.jsonl`. Subagent files are indexed from `subagents/agent-*.jsonl` (layout
`flat`) and `subagents/*/*/agent-*.jsonl` (layout `workflow`), with the sibling
`.meta.json` sidecar (`agentType`, `toolUseId`, `spawnDepth`, `model`, `stoppedByUser`);
agent ids pass the same allowlist shape as `subagent_role._VALID_AGENT_ID`.

A dispatch is an assistant `tool_use` block named `Agent`. It links to an agent id through
the matching user record's top-level `toolUseResult.agentId`, else through the file whose
`meta.toolUseId` equals the dispatch id. The walk starts at the main transcript and
recurses into each accounted subagent's own transcript (parent dispatch id, depth + 1, a
visited set against cycles); a nested child is found wherever its file sits in the index.
A second dispatch resolving to an already-linked agent is dropped with a
`duplicate_agent_link` warning so no file is billed twice.

Each dispatch is `accounted` (source `transcript`), `missing_transcript` (agent id known,
no file) or `missing_metadata` (no agent id resolvable). Every indexed file the walk never
reaches is an orphan: priced and listed in `orphans` with layout, spawn depth and role, but
EXCLUDED from the session total, with the excluded dollars shown as
`session.orphan_usd_excluded`. Workflow-layout files have no Agent tool_use in the main
thread, so they always surface as orphans and `dispatch_coverage.workflow_layout` reads
`"unsupported: listed as orphans, not in session total"`.

Role is `meta.agentType`, else the dispatch input `subagent_type`, else `"unknown"`, with a
leading `"writ:"` stripped; the main thread's role is `"main"`.

Rejected: summing every file under `subagents/`. It counts files that belong to no
dispatch of this session (workflow runs, stale files), and it cannot say which dispatches
are missing.

### Attribution outputs and invariant

New card keys: `session`, `cost_by_model`, `cost_by_role`, `cost_by_dispatch`, `orphans`,
`dispatch_coverage` and `reconciliation`. The existing friction-advisory `coverage` key is
untouched, which is why the new one is named `dispatch_coverage`.

Invariant, asserted in tests: `session.total_usd == main_usd + sum(usd of every accounted
dispatch at every depth) == sum(cost_by_model usd) == sum(cost_by_role usd)`. All sums use
the priced floor; orphans are never in them.

### Cost-state reconciliation

The LAST `type == "cost-state"` record of the main transcript is compared with the Writ
session figure. The record is flat, verified against a real Claude Code transcript: the
top level carries `type`, `sessionId`, `totalCostUSD`, `modelUsage`,
`hasUnknownModelCost`, `startTime` and the duration and lines-changed totals, and each
`modelUsage[model]` entry carries `inputTokens`, `outputTokens`, `cacheReadInputTokens`,
`cacheCreationInputTokens`, `costUSD`, `thinkingTokens` and `webSearchRequests`. Model keys
can be dated (`claude-haiku-4-5-20251001`) and are normalized with `normalize_model`
before comparison. Only this flat shape is read. The report carries
`cc_total_usd`, `writ_session_usd`, `delta_usd` (writ minus cc),
`has_unknown_model_cost`, and per-model USD and token differences. `scope` is derived from
the data: `main_only` when cost-state per-model tokens equal the main-thread totals,
`main_plus_subagents` when they equal main plus the accounted tree, else
`superset_or_unknown` (expected when cost-state lists models the tree never used, such as
Claude Code internal calls). It never raises and never changes the exit code; absent, it
is `{present: false}`.

### Experiment contract (efficacy_ab)

`score_run` rows keep `total_cost` and `total_usd` with their legacy main-thread meaning,
and `compare_arms` still compares on `total_cost`. Rows additively gain `session_usd`,
`session_partial` and `session_dispatch_coverage`, read straight from the card.

Model and effort routing experiments must use `session_usd`, not the legacy
`total_cost`/`total_usd` fields, because routing moves spend between the main thread and
subagents. A row with `session_partial == true` is an incomplete observation (for example
a missing subagent transcript) and must never be read as a cheaper completed task. A
`--cost-scope main|session` flag for efficacy_ab is deferred; it would change A/B behavior
before a baseline exists.

## Consequences

- Dollar figures drop on every multi-block session (dedup) and rise on every session with
  subagents (tree). Neither is comparable with pre-change numbers.
- An unknown model is visible (unpriced list, warning, PARTIAL label) instead of silently
  priced as Opus or dropped.
- Workflow-layout subagent spend is listed but not attributed to the session; that limit
  is stated in the output rather than hidden.
- Spend in a subagent whose transcript Claude Code has already deleted appears only as a
  `missing_transcript` gap with `session.partial` true until the durable summary (Task 2)
  lands.

## Validation result: requestId to message.id mapping

Command, run against the session transcript `T` named in the plan's validation step:

    jq -s '[.[] | select(.type=="assistant" and .message.id != null) | [.message.id, .requestId]] | unique | {pairs: length, ids: (map(.[0])|unique|length), reqs: (map(.[1])|unique|length)}' "$T"

If `pairs == ids == reqs`, `requestId` and `message.id` are 1:1 on that transcript.

Observed on a snapshot of session `54fe1ac9-a554-401f-bbe7-2419043b40f2` (2026-09-29): `pairs 56, ids 56, reqs 56`, so the two keys are 1:1 and `message.id` stays the dedup key. On the same snapshot the audit's 56 responses, 57,700 output tokens and 10,704,650 cache-read tokens equal an independent Python dedup count exactly.

Conflicting duplicates in real data: across the full session tree (main plus 9 subagents), 26 response ids carried differing usage. In all 26, only `output_tokens` differed and the last record held the largest value (streaming snapshots written before the final count). Last-record-wins is therefore the correct rule; a first-record rule would undercount output.
