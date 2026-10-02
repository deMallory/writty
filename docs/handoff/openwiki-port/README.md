# Handoff pack: openwiki port and the Writty workshop

**Current state moved to `docs/handoff/verify-1.7.3/README.md`** (after PR 18, 2026-09-28).
The steps, ground rules and gate mechanics below still hold; its resume table does not.

Written 2026-09-28 at the end of the session that finished step 1, updated the same day after
the step 2 workflows and operations sessions. Read this first, then
`openwiki/INSTRUCTIONS.md`. Everything below was checked against the repo on that date; a
claim marked "not verified" was not.

## Resume point

| What | Where | State |
|---|---|---|
| Step 1: wiki skeleton and structure checks | branch `feat/openwiki`, commit `948c357` | Merged on GitHub as PR 13 (`7dd0ee0`), 2026-09-28 |
| Side fix: plugin agent names in four hooks | branch `fix/plugin-role-names`, commit `0f15365` (off `main`) | Merged as PR 12 (`491657c`), before PR 13. Not live: the plugin cache is still 1.7.2 without it, and the fix did not bump the version |
| Step 2: wiki content | `feat/openwiki`: `1c584f1` workflows, `82bd2a9` architecture, `e00dc0f` operations | Three sections done, merged as PR 14 (`461afbd`), 2026-09-28. Next: integrations, then testing |
| Fix: GNU `timeout` in two hooks | branch `fix/session-start-timeout`, commits `0faf853` and `b250b0e` (off `origin/main`) | Merged as PR 15 (`c144c31`), 2026-09-28. Not live: same plugin update as the side fix |
| Step 3: environment-variable check | a new branch off `origin/main` | Not started |
| Step 4: GitHub Actions wiki refresh | a new branch off `origin/main` | Not started |
| Step 5: workshop touch-ups | raggidy repo, see below | Not started. Has a deadline |

The workshop is around 2026-10-09. Step 5 carries a factual error that must be fixed before
then whatever order the other steps take (see Step 5).

## Why this work exists

People were curious about Writty, so the owner is giving a 20-minute workshop to the dev team:
what Writty does, what it does not, how it helps. The wiki is the follow-up resource the
workshop points at. It mirrors paulinator's `openwiki/`
(/Users/david.malinen/Documents/laarge/dev/paulinator), which was hand-written and is kept
fresh by a scheduled CI job running the `openwiki` CLI. Writty needs the same, on GitHub.

The work is split into steps, one per session, because long sessions lose track of the
middle (lost-in-the-middle).

## Ground rules for every session

**Working style.** One step (in step 2, one wiki section) per session. Plan first, wait for
approval, write tests, wait for approval, then implement. Lead with the answer; short replies.

**Commits.** `type(domaine): sujet à l'impératif`, in French, one line that says why, no
body, no trailers (no Co-Authored-By). Stage only source and docs. Never stage the untracked
`CLAUDE.md`, `.docs/`, `inventory/`, `.claude/workflows/`, or any `settings.local.json`.
Commit only when asked; never push without asking.

**Punctuation.** No em dashes, no double hyphen used as a dash, in prose, commits and wiki
pages. The one exception is the `plan.md` Files grammar below, which the gate requires.

**Wiki writing.** Follow `openwiki/INSTRUCTIONS.md`: English, OKF front matter on line 1,
summarize and link out, never restate a contract from `docs/reference/`. Every backtick path
with a slash and a known extension must exist or the checks fail. Check every factual claim
against the code before writing it: the step 1 draft claimed "approuvé" is refused, and it is
accepted (see Step 5).

## Writ gate mechanics (learned the hard way)

The repo runs its own gates on itself. These cost turns this session:

- **New task, new plan.** After a task, the session sits in `implementation`. Reset to
  planning with `python3 bin/lib/writ-session.py mode set work <session_id>`.
- **Stale `plan.md`.** The repo-root `plan.md` and `capabilities.md` hold the last task's plan
  (the step 2 workflows section). Replace them outright for the next task.
- **Wiki writes are never gated.** `*.md` and `*/tests/*` are in the `exclusions` of
  `bin/lib/gate-categories.json`, so pages and wiki tests are writable in any phase. The
  plan, tests, pages order holds by discipline, not by the gate.
- **Files grammar.** Each `## Files` bullet is one line. A wrapped line, or a colon where the grammar puts its separator, is rejected:

  ```
  - `path` (create|modify|delete) -- reason
  ```
- **Rule IDs.** `## Rules Applied` may cite only IDs that appeared in a `--- WRIT RULES ---`
  block this session. Anything else is flagged as hallucinated and the approval is spent.
  The always-active block counts: the workflows plan passed citing ENF-COMMS-OUTPUT-001,
  ENF-OPS-001, ENF-GATE-007, ENF-PROC-TDD-001 and ENF-TEST-001.
- **Dry-run the gate before asking for approval:**
  `.venv/bin/python -c "from writ.session.approval_workflow import _validate_phase_a; print(_validate_phase_a('.', '<session_id>'))"`.
  `None` means it passes.
- **Quality judgment.** After writing `plan.md` and after writing tests, POST a self-review to
  `http://localhost:8765/session/<session_id>/quality-judgment` (the hook prints the command).
- **Locked plan.** `plan.md` cannot be edited during implementation; tick `capabilities.md`.
- **Approval refused with "Invalid or missing gate token".** The daemon runs older code than
  the hooks. `bash scripts/stop-server.sh; bash scripts/ensure-server.sh`, then approve again.
- **Running tests.** The isolated test Neo4j (port 7688) is not running, so `tests/conftest.py`
  refuses the session. Hook and wiki tests read files only:
  `.venv/bin/python -m pytest --noconftest <paths> -q -p no:randomly`. A test that spawns
  `writ-session.py mode set` must import the `sandbox_cwd` fixture from
  `tests/fixtures/session_state.py`, or it deletes this repo's gate files.
- **Sub-agents.** Until the side fix is live, dispatch `writ:writ-explorer` (and the other
  `writ:writ-*` roles) by that exact name. A generic `Explore` or `general-purpose` dispatch
  is rewritten to a bare name that does not exist, and the call fails.
- **Bash denials in auto mode.** Two multi-command Bash calls (a `cd` or a long `&&` chain)
  were denied by the permission check. Single commands with absolute paths, or the Read
  tool, went through.
- **Checking diagrams.** A Mermaid CLI sits in the npx cache:
  `~/.npm/_npx/d62b6517736c1e35/node_modules/.bin/mmdc -i <page>.md -o <scratchpad>/out.md`
  renders every chart in a page, and `-o <scratchpad>/x.png` gives an image the Read tool
  can show. The cache path is machine-specific and can be pruned.

## Pre-existing failures (not caused by this work)

- `tests/test_plugin_manifest.py::TestValidatePasses::test_the_plugin_manifest_validates_strictly`:
  the local `claude plugin validate --strict` now warns on 49 hooks using an unquoted
  `${CLAUDE_PLUGIN_ROOT}` and on the untracked root `CLAUDE.md`.
- `tests/test_hook_instrumentation.py::test_every_wired_hook_emits_hook_execution`:
  `hooks/scripts/writ-read-credential-gate.sh` never calls `hook_instrument`.
- `tests/plugin/test_hooks_routing.py::TestHooksJsonStructure::test_hooks_json_registration_count`:
  pins 48 registrations; PR 11's credential gate made 49.
- `tests/test_pol5e_hook_noise.py::TestRunPendingTestsBehavior::test_implementation_phase_still_nags`:
  writes its marker under `<repo>/cache`, so the Stop hook misses it when `WRIT_CACHE_DIR`
  is set (it is, on the owner's Mac). Unset, it also needs the test Neo4j on 7688.

All four fail identically on `origin/main` (checked 2026-09-28 in a clean worktree, and again
after PRs 14 and 15 merged).

## The side fix, and how it goes live

On a plugin install the agents are named `writ:writ-*` (the `name` in
`.claude-plugin/plugin.json`). Four hooks assumed bare names: two rewrote dispatches to agents
that do not exist, and two silently skipped their check, so a CRITICAL review never blocked a
commit and the spec-before-quality review order never held. Commit `0f15365` fixes all four;
`tests/test_plugin_role_names.py` pins it (11 tests). Upstream Writ has the same defect in
`writ-dispatch-discipline.sh`; the owner is telling its author directly.

The plugin installs from `deMallory/writty` on GitHub, from `main`, where PR 12 and PR 15 are
merged. To go live: run `claude plugin marketplace update writty` and
`claude plugin update writty@writty`, then restart Claude Code. Neither PR bumped the version
in `.claude-plugin/plugin.json` (still 1.7.2), and whether the update takes a new commit at
the same version is not verified. After it, check that the plugin's copy has
`bin/lib/run-bounded.py`. The workshop machine needs the same update (see Step 5).

## What step 1 left in place

- `openwiki/index.md`: root index, "Start here" order, links to the quickstart and the five
  section directories.
- `openwiki/INSTRUCTIONS.md`: format rules, wiki versus `docs/`, writing rules, how to run
  the checks.
- `openwiki/quickstart.md`: what Writty does and does not do, install (fork commands),
  first gated task, approval words, the five modes, when something blocks. Checked against
  the code.
- `openwiki/<section>/index.md` for workflows, architecture, testing, integrations,
  operations: front matter, one paragraph, and a pointer to the existing doc that covers the
  ground until pages land.
- `tests/openwiki/test_structure.py`: 13 checks. Root index type and links, dangling index
  links, orphan pages, front matter, cited paths exist, mermaid fences closed and typed,
  `| path | N |` rows match line counts, README points at the wiki, plus parser unit tests.
  Run: `.venv/bin/python -m pytest --noconftest tests/openwiki -q -p no:randomly`.
- `README.md`: one bullet under "Where to go next" pointing at `openwiki/index.md`.

## Step 2: wiki content, one section per session

For each section: write the pages, link each from the section `index.md` as
`[Title](file.md) - summary`, and remove the "Until pages land here" line. In the last
session of step 2, add the "When to update which page" table to `openwiki/INSTRUCTIONS.md`
(deferred from step 1 because its backtick paths are existence-checked). Paulinator's table
is the model: `openwiki/INSTRUCTIONS.md` there, section "When to update which page".

The pages below are a proposal from the sources, not a decision; confirm them in each step's
plan. Suggested order: workflows (the workshop leans on it), architecture, operations,
integrations, testing.

| Section | Proposed pages | Sources |
|---|---|---|
| workflows (done) | modes, work gates and approvals, sub-agents, helper workflows (dialectic review, inventory) | `HANDBOOK.md` sections 3 to 8, `docs/reference/session-and-gates.md`, `writ/session/mode_engine.py`, `bin/lib/approval_match.py`, `agents/`, `docs/dialectic-review-workflow.md`, `docs/inventory-workflow.md` |
| architecture | topography (module map with a mermaid flowchart), hooks, local service, rule graph, retrieval, decisions (index of the four ADRs plus decision memory) | `docs/reference/architecture.md`, `docs/reference/hooks.md`, `hooks/hooks.json`, `docs/reference/http-api.md`, `docs/reference/graph-schema.md`, `docs/reference/retrieval.md`, `writ/retrieval/pipeline.py`, `docs/adr/`, `HANDBOOK.md` sections 9 to 14, `docs/architecture/*.html` |
| operations | service lifecycle, project log (dated, newest first, seeded with 2026-09-28), upstream sync. `environment.md` belongs to step 3 and `wiki-refresh.md` to step 4 | `HANDBOOK.md` section 16, `docs/install.md` ("Restarting the daemon"), git remotes (`upstream` is `infinri/Writ`) |
| integrations | Claude Code plugin (including the `writ:` namespace), Neo4j, embedding model, upstream Writ, PyPI | `.claude-plugin/`, `docs/plugin-marketplace.md`, `docs/plugin-validation.md`, `docs/reference/configuration.md`, `.github/workflows/publish.yml` |
| testing | the suite and graph isolation, perf and bench | `HANDBOOK.md` section 19, `docs/reference/testing.md`, `docs/adr/ADR-test-graph-isolation.md`, `Makefile`, `.github/workflows/pr.yml` |

`docs/install.md` is upstream's page and partly wrong for the fork: it installs with
`claude plugin marketplace add infinri/Writ` and `writ@writ`, and counts 44 hook
registrations over 40 scripts where `hooks/hooks.json` has 49 over 45 across 12 events
(counted 2026-09-28, after the secret-read guard landed). Link it for "Restarting the
daemon" only; the fork's install
lives in `openwiki/quickstart.md`.

`inventory/*.json` (untracked) is a machine-readable map of the repo, but it dates from
2026-07-30 at `abaf7c0`, before the 1.7 sync. Use it to orient, never as a source of truth.

Paulinator analogs worth reading before writing a page: `openwiki/architecture/topography.md`,
`openwiki/architecture/decisions.md`, `openwiki/operations/project-log.md`,
`openwiki/integrations/external-services.md`.

### Workflows section: done in `1c584f1`

Four pages: `openwiki/workflows/modes.md`, `openwiki/workflows/work-gates.md`,
`openwiki/workflows/sub-agents.md`, `openwiki/workflows/helper-workflows.md`. 19 wiki tests
pass. Two test additions set the pattern for the other sections:

- `tests/openwiki/test_workflows.py` pins each page to the code it summarizes: the
  `MODE_CONFIG` keys (read with `ast`, no writ import), the work phases and gates, the `name:`
  of every `agents/*.md`, and an approval examples table run through
  `approval_match.classify` (it includes "approuvé"). Stdlib only, so it runs under
  `--noconftest`. Give each section its own `tests/openwiki/test_<section>.py` that reads the
  sources its pages summarize. For architecture, the obvious pins are a hook table against
  `hooks/hooks.json` and the decisions index against `docs/adr/`.
- `tests/openwiki/test_structure.py` now fails when a section index links a page but keeps
  the "Until pages land here" line.

**Merge order.** `sub-agents.md` and `work-gates.md` describe the review-order check and the
commit hold after a CRITICAL review as working. On a plugin install they only work with the
side fix, so merge `fix/plugin-role-names` before `feat/openwiki`. The dispatch rewrite is
described as "to the matching Writty role", without the target name, so that line is true on
both sides of the fix.

**Choices to keep.** The agent table has no model column: `writ-agent-hotswap.sh` stamps its
own model on some dispatches, so the front-matter model is not always what runs. The approval
flow is drawn once, as a sequence diagram in `work-gates.md`; an architecture page about
hooks should link it, not redraw it.

### Operations section

Three pages: `openwiki/operations/service-lifecycle.md`, `openwiki/operations/upstream-sync.md`,
`openwiki/operations/project-log.md`, pinned by `tests/openwiki/test_operations.py` (ports,
systemd unit, macOS realign, fork-only hooks, log date order). 36 wiki tests pass. The project
log is now the dated resume point for the whole project; keep its "Current state" current.

Found while writing it: SessionStart probed Neo4j through GNU `timeout`
(`hooks/scripts/session-start-bootstrap.sh:84`), which stock macOS lacks. The probe failed
with Neo4j up, so the macOS cache realign never ran; the prompt hook still started the
daemon. The Stop hook (`hooks/scripts/writ-run-pending-tests.sh:88`) had the same bug: no
pending test ever ran on macOS. Reproduced on the owner's Mac. PR 15 fixed both the same day
with `bin/lib/run-bounded.py`. After the merge, the "Known gap" paragraph in
`service-lifecycle.md` became a note for plugin copies older than the fix, the project log
moved the thread to its timeline, and `hooks.md` gained a "No GNU `timeout`" pattern.

Branch new wiki work off `origin/main`: `feat/openwiki` is merged, and the local `main` is
behind.

## Step 3: environment-variable check

Goal: a test that keeps the documented `WRIT_*` variables and the variables the code reads
in sync, both ways, like paulinator's `tests/openwiki/environment.test.ts` (an undocumented
read is undiscoverable; a documented row nobody reads outlives its deletion).

**Open decision.** `docs/reference/configuration.md` already holds the environment table
(section "Environment variables", 23 `WRIT_*` names). A second table in the wiki would restate
a contract, which `openwiki/INSTRUCTIONS.md` forbids. Recommendation: point the check at
`docs/reference/configuration.md`, and make `openwiki/operations/environment.md` a short
orientation page that links to it. The alternative is paulinator's shape, with the table in
the wiki.

**The hard part.** A naive grep over `writ/`, `bin/`, `hooks/`, `scripts/` finds about 117
distinct `WRIT_*` tokens. Most are internal plumbing, not operator settings: values handed
from bash to an embedded Python (`WRIT_PARSED_ENVELOPE`, `WRIT_DENY_REASON`), gate-log fields
(`WRIT_GD_*`), shell locals (`WRIT_DIR`). The plan must define "a read" precisely (for
example Python `os.environ` and `os.getenv` reads plus bash `${WRIT_X:-default}` defaults) and
keep a short exemption list with a reason per entry, as paulinator's `COMPOSED_AT_RUNTIME`
does.

## Step 4: GitHub Actions wiki refresh

Port paulinator's `openwiki-update` job (`.gitlab-ci.yml`) to
`.github/workflows/openwiki-update.yml`, and write `openwiki/operations/wiki-refresh.md` from
paulinator's page of the same name.

**What paulinator does.** Runs only on a schedule or manual run carrying `OPENWIKI_UPDATE=true`.
`npm install --global openwiki@0.5.2`, `openwiki code --update --print`, `git add openwiki`
only, exit if no diff, run the wiki tests, commit as
`docs: régénère openwiki depuis les sources en <short sha>`, force-push
`chore/openwiki-update`, open a merge request. The CLI's `AGENTS.md` and `CLAUDE.md` snippet
stays out of the commit.

**The CLI's own GitHub template** (`dist/ingestion/code-mode.js` in the npx cache for
openwiki 0.5.2): `workflow_dispatch` plus `schedule`; `permissions: contents: write,
pull-requests: write`; checkout with `fetch-depth: 0` (the update diffs against the last
documented commit); Node 22; `openwiki code --update --print` with `continue-on-error`;
`rm -f openwiki/.run.json`; `peter-evans/create-pull-request` v7 (pinned by SHA) on branch
`openwiki/update`; a final step that fails the job if the CLI failed. Its `add-paths` also
lists `AGENTS.md`, `CLAUDE.md` and the workflow file; drop those and keep `openwiki` only.

**Decisions for the step 4 plan:**

- API key. The CLI defaults to OpenAI (`OPENAI_API_KEY`). Anthropic works with
  `OPENWIKI_PROVIDER` set to anthropic, `ANTHROPIC_API_KEY`, and optionally
  `OPENWIKI_MODEL_ID`. The owner deferred this choice to step 4.
- Schedule. Paulinator runs weekly (`0 8 * * 1`, Europe/Paris). The CLI's default is daily
  (`0 8 * * *`).
- Whether to commit `openwiki/.page-manifest.json`, a second state file the CLI keeps
  (`dist/config/constants.js`). `git add openwiki` would pick it up; what it holds is not
  verified.

**Things the CLI does on its own** (read in `dist/ingestion/code-mode.js`):

- It writes its own `.github/workflows/openwiki-update.yml` only when the file is missing.
  Commit ours first and the CLI leaves it alone.
- It appends a managed block to `CLAUDE.md` and creates `AGENTS.md`. Locally that edits the
  owner's untracked root `CLAUDE.md`: back it up before the first local run, restore it and
  delete `AGENTS.md` after.

**GitHub gotchas:**

- A PR opened with `GITHUB_TOKEN` does not trigger `.github/workflows/pr.yml`, so the wiki
  checks must run inside the refresh job, before the PR step. They need Python 3.11+ and
  pytest only: `python -m pytest --noconftest tests/openwiki -q` (not verified in CI).
- Settings > Actions > General: enable "Allow GitHub Actions to create and approve pull
  requests", or the PR step fails.
- openwiki 0.5.2 needs Node 22.22.0 or newer.

**Risk, not verified.** Paulinator has no `openwiki/.last-update.json`, so no refresh has
ever completed there. What `--update` does on a first run with no marker (a full regeneration
could overwrite the hand-written pages) is unknown; paulinator's own
`openwiki/operations/wiki-refresh.md` flags the same risk under "Limits". Run it once
locally on a scratch branch and read the diff before scheduling anything. The project log is
a human log: if the CLI rewrites it, reject that hunk.

## Step 5: workshop touch-ups

Material: /Users/david.malinen/Documents/job/flatchr/raggidy/Library/DevDocs/writty/
(`deck/slides/*.html`, 18 slides in French; `demo-live.md`; `atelier-defi.md`;
`sources-du-deck.md`; `gouvernance-claude-code.md`). Online deck:
https://claude.ai/artifact/7Yodjr2RtmbLt9eYhqxtuZ.

**Must fix: the approval-word claim is wrong in three places.** They say "approuvé" is not
recognized. It is: `bin/lib/approval_match.py` accepts any prompt of 12 characters or fewer
within two edits of approved, approve, proceed, accepted or accept, and "approuvé" is two
edits from "approve" (verified by running the matcher). The places:

- `deck/slides/portes.html`: "À taper en anglais : approved, lgtm, go ahead… « approuvé » ne
  marche pas."
- `demo-live.md:32`: "« approuvé » n'est pas reconnu."
- `sources-du-deck.md:21`: "« approuvé » ne marche pas".

Honest phrasing: the listed words are English; a near miss within two letters also passes,
which is why "approuvé" works; an approval word inside a longer sentence makes Writty ask
instead of advancing.

**Also:**

- Re-check every number (they date from August 2026) against `README.md` section
  "Measured" and `HANDBOOK.md` section 20 "By the numbers". The hook count is already
  stale: the deck says 48 registrations over 44 scripts (`sources-du-deck.md:22`), and
  `hooks/hooks.json` now has 49 over 45.
- Rehearse `demo-live.md`; it has never been run end to end.
- Point the closing slide at `openwiki/index.md`. It currently points at `README.md`,
  `HANDBOOK.md` and `docs/architecture/`.
- Workshop machine: update the plugin after the merges (`atelier-defi.md:39` already says so
  for the secret-read guard). Without the side fix live, a demo that dispatches a generic
  agent fails, and a CRITICAL review does not block a commit. Without PR 15 live, SessionStart
  skips the realign on macOS and the Stop hook runs no test.
- `atelier-defi.md` already excludes the bypasses documented in `README.md` (line 55 there).

## Follow-ups outside the steps

- `hooks/scripts/writ-rag-inject.sh:184` says only investigate is auto-set, but the code
  also auto-sets work (`mode init "$MODE_HINT"`). Stale comment.
- `hooks/scripts/writ-rag-inject.sh:354` tells the model to dispatch the bare `writ-explorer`.
- `writ-dispatch-discipline.sh` and `writ-agent-hotswap.sh` both return `updatedInput` for the
  same dispatch; which one wins was never checked.
- The two pre-existing test failures listed above.
- `docs/install.md` still documents upstream's install commands and an old hook count (see
  Step 2).
- `HANDBOOK.md` section 8 says "five named roles" and lists the planner without Edit;
  `agents/` has seven files and `agents/writ-planner.md` grants Edit.
- `docs/reference/session-and-gates.md` section 5 says the token is minted "only if no token
  already exists"; `hooks/scripts/auto-approve-gate.sh:189` overwrites it on purpose.
- `docs/inventory-workflow.md` says `inventory/` is gitignored; `.gitignore` has no entry
  for it.
