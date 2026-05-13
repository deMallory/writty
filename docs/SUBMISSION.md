# Anthropic plugin marketplace submission packet

Maintainer reference for submitting `writ@writ` to the official Anthropic
plugin marketplace at https://claude.ai/settings/plugins/submit.

## Pre-submission checklist

Run through this before opening the form. Every box must be checked.

- [x] **Manifest validates**: `claude plugin validate
      /home/lucio.saldivar/.claude/skills/writ/` exits 0 with no warnings.
      Verified during Phase D end-to-end (commit `278128c`).
- [x] **Marketplace name is not reserved**: `writ` is not on the reserved
      list at code.claude.com/docs/en/plugin-marketplaces#required-fields.
- [x] **Plugin source is publicly reachable**: marketplace.json points at
      `./` and the repo is published at
      https://github.com/infinri/Writ (public).
- [x] **README documents install + usage**: README.md "Install as a Claude
      Code plugin" section ships the install + bootstrap + patch-global-config
      sequence. The patch step is plugin-mode-only and merges Writ's
      permissions allowlist plus the global CLAUDE.md into the user's
      `~/.claude/` (idempotent, backup-on-write).
- [x] **Plugin works on a fresh checkout**: layered end-to-end verification
      passed (clone -> validate -> SessionStart probes -> editable install
      -> writ-rag-inject under plugin env returns rule block ->
      pytest 53 passed, 2 skipped). See e2e report from the commit message
      of `278128c` and `docs/plugin-validation.md`.
- [x] **License is OSI-approved**: MIT (verified in plugin.json).
- [x] **No secrets in repo**: `writ.toml` ships a development Neo4j
      password (`writdevpass`) that users override at bootstrap; documented
      in README. No API keys, tokens, or production credentials.
- [ ] **Screenshots captured**: see "Screenshots" section below; capture
      before opening the form.
- [ ] **First-run UX walked**: open Claude Code in a clean home (or a
      throwaway VM) and run through README install steps end to end.
      Confirms documentation matches reality.

## Listing copy

### Plugin name

`writ`

### Tagline (single sentence, 120 char max)

> A hybrid-RAG knowledge service plus session-aware workflow enforcement
> that picks the right coding rules per prompt and blocks risky writes
> until you've approved a plan.

### Short description (one paragraph)

> Writ is a Claude Code harness with two co-equal layers. A fast
> librarian retrieves the rules that fit the current task via a
> five-stage hybrid pipeline (BM25 keyword + ANN vector + graph
> traversal + reciprocal-rank fusion + context budget) over a
> Neo4j-backed knowledge graph; ranked results return in 0.59 ms at the
> 95th percentile against a 276-rule corpus, and scale-test latency
> holds at 0.557 ms at 10,000 rules while reducing context tokens 726x
> versus loading the whole rulebook every turn. A process keeper made
> of 30 hook scripts and a session state machine enforces mode-based
> workflow gates (plan, tests, implementation) and blocks risky writes
> until you have approved a plan and tests.

### Long description (markdown allowed; mirror README "The problem")

```
Three things break when you give a coding agent a large rulebook the
obvious way (paste it all into the prompt):

1. Token cost grows with the rulebook, not the work. At 80 rules:
   ~13,876 tokens of rule text every turn. At 10,000 rules:
   1,174,142 tokens. Cache hit rates collapse, latency climbs.
2. Relevance degrades. A model handed every rule treats none of them
   as load bearing. Specific rules drown in general advice.
3. Workflow drift. Without enforced phase boundaries (plan -> tests ->
   implementation), agents skip the parts that catch errors.

Writ fixes all three. The librarian injects only the rules that match
the current prompt at sub-millisecond p95 latency, against a corpus
that can grow to 10k+ rules without retrieval slowing down. The
process keeper makes plan + test approval a hard gate before any
production code lands. Modes (conversation, debug, review, work)
scope the ceremony to the actual task at hand.

Two co-equal layers, one harness. Knowledge service runs as a FastAPI
daemon on localhost:8765 (statless retrieval). Enforcement layer is
30 hook scripts wired into Claude Code's hook events (PreToolUse,
PostToolUse, SessionStart, etc.) plus a session state machine.

276 rules ship out of the box across Security, Clean Code, DRY,
SOLID, Architecture, Testing, Error Handling, Performance, Scaling,
API Design, Process, and Documentation. Authoring tooling included
for adding your own rules.
```

### Suggested category

`Development workflows` (per the official marketplace categorization at
code.claude.com/docs/en/discover-plugins#development-workflows).

If a finer-grained `code-quality` or `enforcement` category exists in
the submission form's dropdown, prefer that.

### Tags / keywords (mirror plugin.json keywords field)

`claude-code`, `rag`, `rules`, `enforcement`, `neo4j`, `fastapi`,
`hooks`, `workflow`, `code-quality`, `ai-tooling`

### Author

- Name: Lucio Saldivar
- GitHub: https://github.com/infinri
- Email: lucio.saldivar@2ndswing.com (use a public-facing alias if
  you'd rather not expose this to the marketplace listing)

### URLs

- Homepage / repository: https://github.com/infinri/Writ
- Issues: https://github.com/infinri/Writ/issues
- Documentation: https://github.com/infinri/Writ#readme
- Changelog: https://github.com/infinri/Writ/blob/main/CHANGELOG.md

## Screenshots

Capture each item below as a PNG or short MP4 / GIF before opening the
submission form. The form likely accepts a small number of media
assets per listing; prioritize the first three.

1. **Rule injection in action**: a Claude Code session screenshot
   showing the `--- WRIT RULES (N rules, mode) ---` block injected at
   the start of a turn. Sample prompt: "how do I write a unit test for
   an async function in pytest?" Expected output: ARCH-ASYNC-001 +
   TEST-FIXTURE-001 + PY-ASYNC-001 in the injection.
2. **Gate denial preventing risky write**: Claude Code session where
   the user asks for a code change without an approved plan, and the
   plan-gate hook denies the Write with a `[ENF-GATE-PLAN]` message.
   Demonstrates the "process keeper" half.
3. **`writ status` output**: terminal showing `writ status` (or a curl
   to `http://localhost:8765/stats`) listing 276 rules, 30 mandatory
   rules, and the warm index state. Demonstrates the corpus shape.
4. **Friction-log dashboard (if you ship one)**: any visual showing
   rule frequency, violations over time, or rule-effectiveness
   telemetry. Optional but compelling.
5. **5-stage pipeline diagram**: an architecture diagram showing the
   five retrieval stages. Optional; consider drafting one in
   diagrams.net or Excalidraw if not already in HANDBOOK.md.

For all terminal captures: prefer a dark theme, 14-16pt font, redact
any personal paths under `/home/<you>/`.

## Submission procedure

1. **Log in** at https://claude.ai/settings/plugins/submit. The form
   requires an authenticated Claude.ai account.
2. **Fill the form** using the listing copy above. The form is
   web-only; we have not been able to inspect the exact field list
   beforehand. Expect at minimum: plugin name, marketplace source URL,
   description, category, author, license, screenshots upload.
3. **Marketplace source**: provide `github.com/infinri/Writ` (or the
   form's expected shape; the marketplace name `writ` is declared in
   `.claude-plugin/marketplace.json` at the repo root).
4. **Submit** and note the submission ID / confirmation email.
5. **Wait for review**: Anthropic's review cadence is not publicly
   documented. Expect days, not minutes.

## Post-submission

- Add a "Recommend your plugin from your CLI" hook per
  code.claude.com/docs/en/plugin-hints once the listing is live.
- Cross-link the listing from the README ("Available on the official
  Anthropic plugin marketplace").
- Re-export the marketplace listing copy back into README.md "Why
  Writ?" if Anthropic edits the description during review.

## If review rejects

Capture the rejection reason verbatim, file an issue in this repo,
and address before resubmitting. Common reasons (extrapolating from
plugin spec defaults): manifest schema drift, missing screenshots,
ambiguous description, security concerns about hook scripts.
