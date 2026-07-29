// Codebase inventory workflow (Claude Code dynamic workflow)
// ============================================================
// Fans out one read-only survey agent per subsystem (service / harness /
// corpus / tests / periphery / runtime-trace), adversarially verifies each
// survey's numeric claims, then synthesizes a joined report. Produces raw,
// fine-grained structured data (one record per file / hook / node / event)
// intended as material for a later visualization -- NOT a prose report.
//
// Design principles baked in:
//   - Grain: one row per thing, never a pre-aggregated count. You can always
//     sum; you can't unsum.
//   - Evidence: every numeric/structural claim carries an `evidence` string
//     (the command or file:line it came from). A claim with no evidence is
//     worth less than no claim.
//   - Adversarial verify: each survey is re-derived from scratch by a second
//     agent prompted to refute, not confirm. Numbers that don't survive are
//     reported, not silently reconciled.
//   - Off-disk only: works with Neo4j down and the Writ server (port 8765)
//     down. No `docker`, no `writ serve`.
//
// How to run (from the repo root):
//   Invoke the Claude Code `Workflow` tool with { scriptPath: "scripts/inventory-workflow.mjs" }.
//   The workflow returns { subsystems, synthesis }; the orchestrator writes the
//   per-subsystem data, the mechanically-materialized events table, and a
//   manifest (git sha, row counts, verification verdicts, corrections, gaps)
//   into an `inventory/` directory (gitignored -- regenerable raw output).
//
// Notes for anyone re-running:
//   - The corpus survey deliberately does NOT return all nodes through its
//     schema (that overflows the 64k output-token cap at ~430 nodes); it dumps
//     the full parse to disk and returns samples + breakdowns.
//   - The trace survey returns a `normalization_spec` + sample rows, not the
//     full event table; the orchestrator materializes the full `events.json`
//     mechanically from the two raw logs using that spec.
//   - server.log is truncated fresh on every SessionStart, so its access-line
//     layer is one server lifetime, not longitudinal. The friction log is
//     live-appending, so any single row count is stale the moment it's read.

export const meta = {
  name: 'writty-codebase-inventory',
  description: 'Fan out per-subsystem surveys of the Writty codebase, adversarially verify each, then synthesize a joined inventory as raw material for a visualization',
  phases: [
    { title: 'Survey', detail: 'one agent per subsystem: service, harness, corpus, tests, periphery, runtime trace' },
    { title: 'Verify', detail: 'adversarial re-derivation of a sample of each survey\'s numeric claims' },
    { title: 'Synthesize', detail: 'merge into one joined report, resolve cross-subsystem keys, list gaps' },
  ],
}

const READONLY = `Constraints, non-negotiable:
- READ-ONLY. Do not write, edit, or delete any file. Do not run "docker", "docker compose", "writ serve", or anything that starts a server or a database.
- Neo4j and the Writ HTTP server are both DOWN. Do not attempt to connect to localhost:8765 or bolt://localhost:7687. Any code you run must work purely off disk and git.
- Work from the repo root using \`git ls-files\` (not \`find\`) to enumerate tracked files so you automatically skip .venv/node_modules/build artifacts.
- Every numeric or structural claim (line counts, counts of things, "this hook is registered on event X") MUST carry an "evidence" string: the exact command you ran or the file:line you read it from. A claim with no evidence is worth less than no claim — do not guess.
- Return ONLY the structured data via the required schema. No prose commentary outside the fields.`

const SUBSYSTEMS = [
  {
    key: 'service',
    label: 'survey:service',
    territory: 'writ/',
    prompt: `${READONLY}

Survey the Python service package at writ/ (this is the FastAPI + retrieval-pipeline daemon; do not include writ/graph/schema.py's node-type vocabulary here, just the modules themselves).

For EVERY .py file under writ/ (use \`git ls-files writ/'*.py'\`), produce one record:
- path: repo-relative path
- lines: from \`wc -l\`
- role: one sentence, grounded in what you actually read (top-level docstring + function/class names), not a guess
- public_api: names of top-level functions/classes (skip leading-underscore names)
- imports: notable internal imports (other writ.* modules, or key externals like fastapi/neo4j/onnxruntime)
- talks_to: concrete downstream things this module reaches at runtime if any (e.g. "Neo4j via bolt", "bin/lib/writ-session.py by dynamic file load", "workflow-friction.log", "$TMPDIR/writ-session-*.json") — leave empty array if none
- evidence: the command or file:line you used for the lines/role claim

Also return a one-paragraph "summary" describing the package's overall shape (is it one monolith or well-separated modules, where's the biggest file, etc).`,
    schema: {
      type: 'object',
      properties: {
        subsystem: { const: 'service' },
        records: {
          type: 'array',
          items: {
            type: 'object',
            properties: {
              path: { type: 'string' },
              lines: { type: 'integer' },
              role: { type: 'string' },
              public_api: { type: 'array', items: { type: 'string' } },
              imports: { type: 'array', items: { type: 'string' } },
              talks_to: { type: 'array', items: { type: 'string' } },
              evidence: { type: 'string' },
            },
            required: ['path', 'lines', 'role', 'evidence'],
          },
        },
        summary: { type: 'string' },
      },
      required: ['subsystem', 'records', 'summary'],
    },
  },
  {
    key: 'harness',
    label: 'survey:harness',
    territory: '.claude/hooks/ and bin/',
    prompt: `${READONLY}

Survey the bash hook harness: .claude/hooks/*.sh, hooks/hooks.json (the event->matcher->script registration map), hooks/scripts/*.sh, and bin/ + bin/lib/ (the shared libraries and CLI shims the hooks call into).

First read hooks/hooks.json to get the real event/matcher registration for each script (do not guess registration from filename).

For EVERY hook script, produce one record:
- path
- event: the Claude Code hook event it's registered under (SessionStart, UserPromptSubmit, PreToolUse, PostToolUse, PostToolUseFailure, SubagentStart, SubagentStop, Stop, PreCompact, PostCompact, SessionEnd, CwdChanged, InstructionsLoaded)
- matcher: the tool matcher string if any, "" if event-wide, or "*" if explicitly empty-matcher (meaning it fires on every tool call — flag this clearly if so)
- lines
- http_paths: any HTTP paths it curls (e.g. "/session/{id}/mode", "POST /query") — grep for curl/http calls
- tmp_files: any /tmp/* or $TMPDIR paths it reads or writes
- blocking: true if it can exit with a blocking exit code (grep for "exit 2"), false if it fails open
- evidence

Also include bin/lib/common.sh and bin/lib/writ-session.py as records even though they're libraries not hooks (event: "library", matcher: null) — they're load-bearing for almost every hook.

Return a "summary" noting anything structurally notable (e.g. hooks that fire on every single tool call, hooks with duplicate registrations, hooks that silently no-op if a dependency like jq is missing).`,
    schema: {
      type: 'object',
      properties: {
        subsystem: { const: 'harness' },
        records: {
          type: 'array',
          items: {
            type: 'object',
            properties: {
              path: { type: 'string' },
              event: { type: 'string' },
              matcher: { type: 'string' },
              lines: { type: 'integer' },
              http_paths: { type: 'array', items: { type: 'string' } },
              tmp_files: { type: 'array', items: { type: 'string' } },
              blocking: { type: 'boolean' },
              evidence: { type: 'string' },
            },
            required: ['path', 'event', 'lines', 'blocking', 'evidence'],
          },
        },
        summary: { type: 'string' },
      },
      required: ['subsystem', 'records', 'summary'],
    },
  },
  {
    key: 'corpus',
    label: 'survey:corpus',
    territory: 'bible/',
    prompt: `${READONLY}

Survey the bible/ knowledge corpus (do not assume a node count going in — the number of parsed nodes is well above the count of markdown files, because domain rollup files re-embed rules that also exist as standalone per-rule files; treat any node count in the docs as unverified, not as ground truth). Two coexisting formats: legacy "<!-- RULE START: id -->" blocks, and YAML-frontmatter methodology nodes.

Do NOT hand-parse the markdown files yourself one by one. From the repo root, run a python script that reuses the repo's own parser so results are grounded in real code:

python3 -c "
import sys, json; sys.path.insert(0, '.')
from pathlib import Path
from writ.graph.ingest import discover_rule_files, parse_nodes_from_file
files = discover_rule_files(Path('bible'))
recs = []
for f in files:
    for node in parse_nodes_from_file(f):
        recs.append(node)
Path('/tmp/writty-corpus-nodes.json').write_text(json.dumps(recs, indent=1))
print(len(files), 'files ->', len(recs), 'nodes, written to /tmp/writty-corpus-nodes.json')
"

(read writ/graph/ingest.py first to confirm the real function signatures and returned dict shape before relying on it — do not fabricate fields it doesn't return. If this import fails for any reason, fall back to careful manual parsing of a representative sample and say so explicitly in "summary".)

IMPORTANT — do NOT return all node records through this schema; that overflows the output-token limit at this volume. Instead:
1. Write the full parsed node list to /tmp/writty-corpus-nodes.json as shown above (or under whatever path you actually used — report it in "full_dump_path").
2. Reshape each node dict into the flatter target shape (id, node_type, domain, severity, authority, always_on, tags, edges, format, source_file, evidence) and ALSO write that reshaped list as JSONL to /tmp/writty-corpus-records.jsonl, one record per line, evidence = "writ/graph/ingest.py parse_nodes_from_file(<source_file>)".
3. Check for duplicate ids (a node id appearing in more than one source_file, or twice in the parsed list) and report the count and a few examples — this is a real thing to check for, not a formality.
4. Return via schema: total_count, node_type_breakdown, format_breakdown, duplicate_id_count, duplicate_id_examples, full_dump_path (the reshaped JSONL path), and "sample_records": 15-20 real reshaped records spanning multiple node_types and both formats, so the full dump can be spot-checked against this sample.

Also return "summary" describing what you found, including how the actual node count compares to the count of markdown files and why (e.g. per-domain rollup files re-embedding per-rule files).`,
    schema: {
      type: 'object',
      properties: {
        subsystem: { const: 'corpus' },
        total_count: { type: 'integer' },
        node_type_breakdown: { type: 'array', items: { type: 'object', properties: { node_type: { type: 'string' }, count: { type: 'integer' } } } },
        format_breakdown: { type: 'array', items: { type: 'object', properties: { format: { type: 'string' }, count: { type: 'integer' } } } },
        duplicate_id_count: { type: 'integer' },
        duplicate_id_examples: { type: 'array', items: { type: 'string' } },
        full_dump_path: { type: 'string' },
        sample_records: {
          type: 'array',
          items: {
            type: 'object',
            properties: {
              id: { type: 'string' },
              node_type: { type: 'string' },
              domain: { type: 'string' },
              severity: { type: 'string' },
              authority: { type: 'string' },
              always_on: { type: 'boolean' },
              tags: { type: 'array', items: { type: 'string' } },
              edges: { type: 'array', items: { type: 'object', properties: { edge_type: { type: 'string' }, target: { type: 'string' } } } },
              format: { type: 'string' },
              source_file: { type: 'string' },
              evidence: { type: 'string' },
            },
            required: ['id', 'node_type', 'source_file', 'format', 'evidence'],
          },
        },
        evidence: { type: 'string' },
        summary: { type: 'string' },
      },
      required: ['subsystem', 'total_count', 'node_type_breakdown', 'format_breakdown', 'full_dump_path', 'sample_records', 'evidence', 'summary'],
    },
  },
  {
    key: 'tests',
    label: 'survey:tests',
    territory: 'tests/ and benchmarks/',
    prompt: `${READONLY}

Survey tests/ (test_*.py files, pytest, some driving bash hooks via subprocess) and benchmarks/.

For each test file, use python's ast module (or careful grep on "def test_") to count test functions accurately rather than eyeballing. Produce one record per test file:
- path
- subject: what module/hook/behavior this file is testing, inferred from filename + a skim of the file (e.g. "test_retrieval.py" -> "writ/retrieval/pipeline.py")
- test_count: number of test_* functions (from ast, evidence should say so)
- markers: any @pytest.mark.* markers used in the file (e.g. "asyncio", "perf", "integration")
- uses_subprocess: true if the file imports/uses subprocess (a sign it's driving a bash hook rather than testing Python directly)
- evidence

Also survey benchmarks/*.py the same way but with subject = benchmark target instead of test subject, test_count = number of benchmark functions.

Return "summary" with total test function count across all files (and how it compares, if at all, to any number claimed in docs like HANDBOOK.md or CODEBASE.md — flag if those docs are stale relative to what you counted).`,
    schema: {
      type: 'object',
      properties: {
        subsystem: { const: 'tests' },
        records: {
          type: 'array',
          items: {
            type: 'object',
            properties: {
              path: { type: 'string' },
              subject: { type: 'string' },
              test_count: { type: 'integer' },
              markers: { type: 'array', items: { type: 'string' } },
              uses_subprocess: { type: 'boolean' },
              evidence: { type: 'string' },
            },
            required: ['path', 'test_count', 'evidence'],
          },
        },
        summary: { type: 'string' },
      },
      required: ['subsystem', 'records', 'summary'],
    },
  },
  {
    key: 'periphery',
    label: 'survey:periphery',
    territory: 'scripts/, docs/, templates/, and root config files',
    prompt: `${READONLY}

Survey the periphery: scripts/ (installers, corpus seeders, instrumentation one-offs), docs/ (extraction series, pressure-runs, monthly reviews), templates/ (files copied into a user's ~/.claude/ by installers), and root-level config (pyproject.toml, writ.toml, docker-compose.yml, Makefile, .pre-commit-config.yaml).

Produce one record per artifact (file or, for docs/pressure-runs/, one record per PSR-* directory rather than per file inside it):
- path
- kind: one of "installer", "corpus-seeder", "instrumentation", "doc-narrative", "doc-reference", "pressure-run-fixture", "config", "template"
- purpose: one sentence, grounded in what you read
- is_entry_point: true if a human or CI is meant to invoke this directly (e.g. scripts/bootstrap.sh, Makefile targets) vs. true library/vendored/generated
- evidence

Return "summary" noting anything surprising: e.g. seed_phase_*.py files' total line count and what fraction of scripts/ they represent, any docs that look stale (compare a claim in them against something you can verify, similar to how CODEBASE.md is known to under-report test counts).`,
    schema: {
      type: 'object',
      properties: {
        subsystem: { const: 'periphery' },
        records: {
          type: 'array',
          items: {
            type: 'object',
            properties: {
              path: { type: 'string' },
              kind: { type: 'string' },
              purpose: { type: 'string' },
              is_entry_point: { type: 'boolean' },
              evidence: { type: 'string' },
            },
            required: ['path', 'kind', 'purpose', 'evidence'],
          },
        },
        summary: { type: 'string' },
      },
      required: ['subsystem', 'records', 'summary'],
    },
  },
  {
    key: 'trace',
    label: 'trace:runtime',
    territory: 'workflow-friction.log and ~/.cache/writ/server.log',
    prompt: `${READONLY}

This is the temporal/runtime layer: two log surfaces recording what the system has actually done across past sessions.

Source A: ./workflow-friction.log (at the repo root) — JSONL, one event object per line, has a real "ts" field (UTC). Read writ/analysis/friction.py first (FrictionEvent model, parse_log, resolve_log_path) to understand the canonical schema before you characterize it.

Source B: ~/.cache/writ/server.log — raw uvicorn stdout/stderr. Access lines look like: INFO:     ::1:49954 - "POST /session/5b4fde07-2a99-4301-8c41-061d47736cbf/context-percent HTTP/1.1" 200 OK
These lines have NO timestamp and the client port is meaningless (a fresh ephemeral port per curl call). The only signal is the path, and file order is the only temporal ordering available.

Do NOT try to dump every row through this schema — that's wasteful and error-prone for an LLM to hand-copy at this volume. Instead:
1. Get exact row/line counts for both sources (evidence: your count command, e.g. \`wc -l\` for the friction log, \`grep -c 'INFO:.*"' \` for access lines).
2. Note that three distinct session-id SHAPES coexist across both sources: a 36-char UUID, a ~17-hex subagent agent_id, and a bare PID (from a ps-based fallback some hooks use when they get no stdin envelope — see .claude/hooks/writ-session-end.sh). Give an example of each shape actually found in the logs, with which source it came from.
3. Return a "normalization_spec": the exact field mapping you'd use to normalize both sources into one row shape (source, ts-or-null, session, session_shape, event-or-method+path, status, hook_name, duration_ms, rule_ids) — precise enough that someone could implement it mechanically without further judgment calls.
4. Return "sample_rows": 15-20 real rows manually normalized per your own spec, deliberately including at least one example of each session_shape and both sources, so the spec can be checked against ground truth.
5. Return "event_type_breakdown": counts per distinct "event" value in the friction log (e.g. hook_execution, rag_query, subagent_start, ...).
6. Note whether the server is currently running (check \`lsof -iTCP:8765 -sTCP:LISTEN\` or similar) and what that implies about how current server.log's contents are (it gets truncated fresh on every SessionStart per hooks/scripts/session-start-bootstrap.sh — confirm by reading that file, don't assume).`,
    schema: {
      type: 'object',
      properties: {
        subsystem: { const: 'trace' },
        friction_row_count: { type: 'integer' },
        access_line_count: { type: 'integer' },
        session_shape_examples: {
          type: 'array',
          items: { type: 'object', properties: { shape: { type: 'string' }, example: { type: 'string' }, source: { type: 'string' } } },
        },
        normalization_spec: { type: 'string' },
        sample_rows: {
          type: 'array',
          items: {
            type: 'object',
            properties: {
              source: { type: 'string' },
              ts: { type: ['string', 'null'] },
              session: { type: 'string' },
              session_shape: { type: 'string' },
              event_or_path: { type: 'string' },
              status: { type: ['string', 'integer', 'null'] },
            },
          },
        },
        event_type_breakdown: { type: 'array', items: { type: 'object', properties: { event: { type: 'string' }, count: { type: 'integer' } } } },
        server_currently_running: { type: 'boolean' },
        evidence: { type: 'string' },
        summary: { type: 'string' },
      },
      required: ['subsystem', 'friction_row_count', 'access_line_count', 'normalization_spec', 'sample_rows', 'evidence', 'summary'],
    },
  },
]

const VERIFY_SCHEMA = {
  type: 'object',
  properties: {
    subsystem: { type: 'string' },
    checks: {
      type: 'array',
      items: {
        type: 'object',
        properties: {
          claim: { type: 'string' },
          claimed_value: { type: 'string' },
          rederived_value: { type: 'string' },
          match: { type: 'boolean' },
          method: { type: 'string' },
        },
        required: ['claim', 'claimed_value', 'rederived_value', 'match', 'method'],
      },
    },
    overall_verdict: { type: 'string' },
    issues_found: { type: 'array', items: { type: 'string' } },
  },
  required: ['subsystem', 'checks', 'overall_verdict'],
}

function verifyPrompt(subsystemKey, surveyResult) {
  return `${READONLY}

You are an ADVERSARIAL verifier, not a confirmer. Below is a survey of the "${subsystemKey}" subsystem of the Writty codebase, produced by another agent. Your job is to try to BREAK it: pick 6-10 of its records/claims (spread across the file, not just the first few), independently re-derive each claimed number or fact from scratch using your own commands (git ls-files, wc -l, grep -c, python ast, direct file reads — do not trust the survey's "evidence" string, actually run it or an equivalent yourself), and report whether it matches.

Default to skepticism: if you're not sure a claim is right, mark match: false and explain, don't give the benefit of the doubt.

Survey to verify (JSON):
${JSON.stringify(surveyResult, null, 2).slice(0, 12000)}

Report checks[] for each thing you independently tested, and an overall_verdict ("pass" if everything you sampled checked out, "issues" otherwise with issues_found[] listing what's wrong).`
}

phase('Survey')
const surveyed = await pipeline(
  SUBSYSTEMS,
  (s) => agent(s.prompt, { label: s.label, phase: 'Survey', schema: s.schema }),
  (surveyResult, s) => agent(verifyPrompt(s.key, surveyResult), { label: `verify:${s.key}`, phase: 'Verify', schema: VERIFY_SCHEMA })
    .then((verification) => ({ key: s.key, survey: surveyResult, verification }))
)

const results = surveyed.filter(Boolean)
log(`Survey+verify complete for ${results.length}/${SUBSYSTEMS.length} subsystems`)

phase('Synthesize')
const SYNTH_SCHEMA = {
  type: 'object',
  properties: {
    join_map: {
      type: 'array',
      description: 'Concrete cross-subsystem join keys someone building a visualization would actually use',
      items: { type: 'object', properties: { from: { type: 'string' }, to: { type: 'string' }, key: { type: 'string' }, note: { type: 'string' } } },
    },
    gaps: { type: 'array', items: { type: 'string' } },
    headline_shapes: { type: 'array', items: { type: 'string' }, description: 'Interesting structural facts worth building a visualization around' },
    overview: { type: 'string' },
  },
  required: ['join_map', 'gaps', 'headline_shapes', 'overview'],
}
// Full record arrays would blow well past any safe prompt-truncation slice (corpus alone
// is 400+ nodes) and a blind .slice() on the stringified JSON risks cutting off mid-object,
// silently dropping later subsystems AND their verification/correction data. Condense instead:
// keep summary-level fields + verification issues (what synthesis actually needs), drop bulk
// record arrays (illustrated with a small sample so the agent still sees real shapes).
const condensed = results.map((r) => {
  const survey = { ...r.survey }
  const fullRecords = survey.records || survey.sample_records
  if (Array.isArray(fullRecords)) {
    const key = survey.records ? 'records' : 'sample_records'
    survey[`${key}_total_count`] = fullRecords.length
    survey[key] = fullRecords.slice(0, 4)
    survey[`${key}_note`] = `truncated to 4 of ${fullRecords.length} for this synthesis step; full data lives in inventory/${r.key}.json`
  }
  return { key: r.key, survey, verification: r.verification }
})

const synthesis = await agent(
  `${READONLY}

You are the final synthesis step. Below are six verified subsystem surveys of the Writty codebase (service=writ/ Python package, harness=bash hooks, corpus=bible/ knowledge nodes, tests=tests/+benchmarks/, periphery=scripts/docs/templates/config, trace=runtime log analysis). Each has already been adversarially checked. A "verification.overall_verdict" of "issues" means treat that survey's SUMMARY claims with caution — read verification.issues_found and use the corrected values it gives, not the original survey summary's numbers, when they conflict. Record arrays below are truncated to a few examples each (see "*_total_count" and "*_note" fields) — full data lives in separate per-subsystem files, you don't need to enumerate every record here.

Condensed results, ALL SIX subsystems (JSON):
${JSON.stringify(condensed, null, 2)}

Produce:
1. join_map: concrete, field-level join keys someone would use to cross-reference these datasets for a visualization — e.g. a harness record's http_paths should link to something in the trace normalization_spec's event_or_path, a corpus record's edges[].target should link to another corpus record's id. Name the actual field names.
2. gaps: anything a verifier flagged as failing, anything a survey admitted it couldn't determine, anything structurally missing (e.g. "trace only has a sample of rows, not the full normalized set — that still needs to be materialized mechanically from the logs using the normalization_spec").
3. headline_shapes: 5-8 concrete, surprising structural facts pulled from the actual data (not restating known context) that would make good raw material for a visualization — think in terms of things that could become axes, groupings, or a striking single number.
4. overview: 3-5 sentences tying it together.`,
  { label: 'synthesize', phase: 'Synthesize', schema: SYNTH_SCHEMA }
)

return { subsystems: results, synthesis }
