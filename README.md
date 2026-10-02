# Writ

[![License: MIT](https://img.shields.io/badge/license-MIT-yellow.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue.svg)](pyproject.toml)

**Claude Code can forget your rules. Writ can refuse the action.**

Writ is a local governance, context, and continuity runtime for Claude Code. It enforces selected boundaries when tools run, delivers the rules and methodology relevant to the work happening now, and preserves project memory and decision history across sessions.

| Writ provides | What that means |
|---|---|
| **Action** | Tool-time controls can allow, pause, confirm, or refuse an attempted action. |
| **Context** | Relevant rules, skills, and methodology arrive when the current task, file, tool, or workflow phase requires them. |
| **Continuity** | Decisions and project memory persist across sessions, while best-effort handoffs preserve active workflow state across context compaction. |

Ready to try it? Jump to [Install](#install), or read [how enforcement works](#how-enforcement-works).

## Why it exists

An instruction and an enforcement point are different things. A system prompt, a `CLAUDE.md`, a methodology document: all of them ask the model to remember. That works until context fills, a session compacts, or the model decides the rule does not apply this time.

Writ does not replace instructions. It adds the second primitive for the parts of your process you choose to gate, so those parts hold whether or not the model is still paying attention.

## How enforcement works

You tell Writ what kind of work you are doing. That is the mode. Conversation and review remain lightweight. Investigate and debug add evidence tracking and activity-specific controls. In Work mode, source writes are blocked until a human opens the plan and test gates.

Claude tries to write code before a plan has been approved:

```text
[ENF-GATE-PLAN] ALL writes blocked -- plan not yet approved. DO NOT attempt more writes.
Present your plan to the user and say: "Say approved to proceed."
Wait for the user to say "approved" before attempting ANY file writes.
```

You read the plan and type `approved`. That opens the first gate. The second gate requires at least one assertion-bearing test. You review the tests and approve them too. After both gates open, implementation writes are allowed while the remaining safeguards continue to operate.

The same boundary layer also covers credential paths, writes made through the shell, recognized external-data transfers, debugging, review findings, and sub-agent authorization.

## What using it feels like

You tell Writ what kind of work you are doing. That is the mode. In the read-only modes (conversation, review, investigate) Writ hands over relevant rules and otherwise stays quiet. In **Work mode**, writes to your source code are blocked until two gates open:

```text
[ENF-GATE-PLAN] ALL writes blocked -- plan not yet approved.
```

You read the plan. You type "approved." The gate opens. The next gate wants a test file that actually asserts something. Same pattern: write it, approve it, and the gate opens. After both gates clear, the AI writes implementation code freely.

**The AI cannot approve itself.** Opening a gate consumes a one-time secret written to a temporary file, and that secret is only created when *your typed message* matches an approval phrase. Claiming it is a single filesystem operation that exactly one caller can win, so one approval opens exactly one gate. An AI that tries to open its own gate finds no secret, gets refused, and the attempt is written to the audit log as `agent_self_approval_blocked`.

Worth being blunt about what the gate does and does not check. The validators confirm the plan **exists and has the right shape**. They cannot tell a thoughtful plan from a plausible-looking one. No pattern match can. What makes the gate meaningful is that a person reads the artifact before typing the approval. Writ relocates oversight. It does not remove it.

| Mode | For | What it blocks |
|---|---|---|
| `conversation` | Talking, asking, thinking out loud | Nothing |
| `review` | Judging code against the rules | Nothing |
| `investigate` | Auditing, exploring, researching | Web research cannot be summarized until sources come from two independent sites |
| `debug` | Chasing one specific failure | Source edits, until you have written down a root cause |
| `work` | Building or changing code | Source writes, until the plan gate and the test gate both open |

While Claude works, the hooks watch each write. Editing a file whose code touches SQL can pull the parameterized-query and injection rules into context at that moment, even if your prompt never mentioned SQL.

And when the work is committed, Writ can connect the resulting files back to the approved plan and the rules that governed the session.

## What it costs, and who it is for

**What it costs you.** For a typical Work-mode change, Writ adds two approvals: you read the plan and type "approved", then you read the tests and type "approved". After that the AI writes code without interrupting you again, with one exception: a review finding something serious adds a confirmation before the work is committed. So usually two, occasionally three. The other four modes add no approvals at all. The rulebook lives in a database on your own machine, so you need Docker installed, which is a normal application download. Your rules and your code stay on your machine; [`SECURITY.md`](SECURITY.md) lists the one thing that leaves and when.

**What you get for that.** On Writ's guarded path, configured gates are checked at tool time. Either their conditions have been satisfied or the attempted action is refused. When something is refused, there is a record of what was refused and why, which is the part that matters if you are the person answering for the code rather than writing it.

**Who it is for.** Engineers and engineering leads who need important coding-agent workflows to be governed outside the model rather than left as instructions. Writ ships opinionated plan-first and test-driven defaults, and its mode and gate system provides the machinery underneath them.

Writ deliberately trades some setup and workflow friction (Python, Docker, Neo4j, a background service, hooks, workflow state) for stronger control over agent behavior. The question is whether those guarantees are worth that tradeoff for your work. Everything below documents exactly what Writ controls, what it does not, and the evidence available today.

## What Writ does not guarantee

The limits are stated here rather than further down where they would look buried.

**Writ constrains a cooperative agent; it is not an adversarial sandbox.** Writ assumes the AI uses its tools in the ordinary way and is not deliberately searching for ways around the harness. Under that assumption the gates hold. Against an AI actively working around them they do not, and the gaps are written down here rather than glossed:

* Writes made through shell commands are inspected, and as of 1.7.0 that inspection reads inside interpreter one-liners too (`python -c`, `node -e`, `perl -e`, `ruby -e`, `php -r`, including heredoc and piped forms). The gaps that remain are named in the hook itself rather than left vague: a path assembled from shell variables, `eval` or base64, an `sh -c` wrapper, program text handed to awk or sed, an interpreter reached through a variable or alias, and `python -m MODULE`, which is deliberately unscanned because matching it would refuse every `python -m pytest` run.
* Reads of secret files are refused for the Read tool, for Grep aimed at the file, and for shell readers (`cat`, `head`, `source`, `grep`, `cp`, `base64`, ...) including interpreter one-liners that name the file. The same class of gaps remains: a path built from variables, `eval` or base64, an `sh -c` wrapper, a program file (`python read_env.py`), and Grep over a whole directory that holds a committed `.env`. Shell output that still carries a `PASSWORD=`, `SECRET_KEY=` or `user:pass@host` value is masked before the AI sees it.
* When the background service is unreachable, hooks **allow rather than block**. This is the specification, not a bug. An infrastructure outage must never lock you out of your own repository.
* Subagents (helper AIs spawned by the main one) skip the write gates by design. Their limits come from the tools their role grants them, not from re-checking work the human already approved.

If you need enforcement against an AI that is actively adversarial, Writ is not that tool. What Writ can do is mechanically refuse selected tool actions until configured workflow conditions are satisfied. Whether that produces better engineering outcomes is a different question, and the two limits below are why it is still open.

It can tell that a plan exists. It cannot tell whether the plan is any good. The checks confirm the shape of the thing, not the thought behind it. A plausible plan and a careful one look identical to a machine, so this replaces none of your judgement, and reviewing the work is still your job.

The main claim is not proven yet. Everything measured so far shows what the search costs and how well it ranks. None of it shows that an AI handed the right rule actually behaves better than one handed nothing. That is the whole point of the tool and it is currently unproven, with the reasoning and the missing experiment written up further down.

---

**Everything below this point assumes you write code.** The rest of this document is written for engineers evaluating whether to run it, and stops rationing vocabulary.
**The agent cannot approve itself.** Opening a gate spends a one-time secret, and that secret is created only when *your own typed message* matches an approval phrase. An agent that tries finds nothing to spend, is refused, and the attempt is written to the audit log. Editing the plan after approving it re-arms both gates, so an approval covers the plan you actually read.

## Install

**You will need Claude Code, Python 3.11 or newer, and Docker.** Python is a real requirement, not a packaging convenience: the enforcement logic runs in it. Docker runs the graph database that stores Writ's rules, methodology, project memory, and decision records.

### Let Claude Code do it

You already have an agent that reads instructions and runs commands. Point it at this page:

> Install Writ from https://github.com/infinri/Writ. Verify that Python 3.11+ and Docker are available, follow the plugin installation instructions, run the bootstrap command Writ prints after Claude Code starts, restart Claude Code, and verify that the Writ service is healthy. Stop and explain anything that requires me to install or approve it manually.

Claude Code can do the project setup. It cannot install Docker or Python for you, so if either is missing you will be asked to handle that part yourself.

### Or run it yourself

```shell
claude plugin marketplace add infinri/Writ
claude plugin install writ@writ
```

Open Claude Code once. It notices the un-bootstrapped install and prints a single absolute command on its own line, ready to paste. Run it, then restart Claude Code.

That one script does the rest: environment, database, rules, background service, permissions. It is idempotent, so re-running it after an update is the whole update procedure.

### Check it worked

```shell
writ status
```

Nothing breaks while you are partway through setup. Hooks stay out of the way until the install finishes, sessions are never blocked, and the startup hook prints what is still missing. Both install paths and troubleshooting are in [`docs/install.md`](docs/install.md).

## What Writ controls

### Action

| | |
|---|---|
| **Plan and test gates** | Work mode requires an approved plan, then approved tests, before implementation writes are allowed. |
| **Human-only approval** | The approval token is minted only from your typed words. The agent has no path to creating one, and the attempt is recorded when it tries. |
| **Credential protection** | Writes to keys, `.env` files, and SSH material are refused in every mode. The path is classified without the file ever being opened. |
| **Shell writes** | Writes made through redirection, `tee`, `cp`, or `sed -i` go through the same check as tool writes, not a separate weaker one. |
| **External data** | Outbound commands carrying a payload to a host outside your allowlist ask for confirmation. Writ cannot tell what a payload contains, so it asks rather than guessing. |
| **Debug gate** | In debug mode, source edits are refused until a root cause is written down. The refusal names the file and section that lifts it. |
| **Review escalation** | A serious review finding turns the next commit into a confirmation naming the unresolved findings. The agent cannot clear its own verdict. |
| **Sub-agent authorization** | A helper agent is refused any path its orchestrator would be refused at that moment, and each role carries its own write scope. |
| **Completion checks** | Pending tests, unresolved rule violations, and failed quality verification can stop a turn before the agent declares the work complete. |
| **Audit records** | What was allowed, what was refused, and why, in a stream kept separate from operational logs. |

### Context

Writ delivers both engineering rules and reusable methodology, including skills, playbooks, techniques, and known failure patterns. Delivery is driven by what is happening now: the prompt, the file being written, the tool running, and the workflow phase.

| | |
|---|---|
| **Selective delivery** | Rules arrive when they apply, so the rulebook can grow without every turn growing with it. |
| **A floor that cannot be ranked away** | Mandatory content is held out of the relevance ranking entirely and delivered on its own channel, so no retuning can drop it. |
| **Hybrid retrieval** | Combines exact-term and semantic search, then uses graph relationships to bring in connected guidance. |
| **Abstention** | When nothing is relevant enough, Writ delivers nothing rather than filling the turn with noise. |
| **Tool-output compression** | Large Write and Edit responses are stripped of redundant full-file echoes while preserving the patch and fields Claude still needs. |
| **Budgets** | Per-session and per-channel limits, so context is spent rather than flooded. |

Two boundaries hold no matter what, including when the background service is down and inside subagents. Writes to credential files (keys, `.env`, SSH material) are refused in every mode with no server involved, and so are reads: whatever the AI reads leaves your machine. Templates such as `.env.example` stay readable. And the approval token cannot be created or spent without a human keystroke, so **advancing the workflow and writing new rules into the rulebook halt even when raw file writes do not.**
### Continuity

Three different mechanisms, answering three different questions.

| Question | Mechanism |
|---|---|
| *Why was this code changed?* | **Decision memory.** Approved plan, governing rules, changed files, and the resulting commit are linked mechanically, not inferred from the conversation. The record replays as a new-session briefing, as git notes, and on supported pull requests. `writ recall` reads it back. |
| *What project knowledge did Claude save?* | **Auto-memory mirror.** Claude Code's own memory files are mirrored into the graph as they are written, scoped per project. `writ memory backfill`, `writ memory list`, and `writ memory audit` cover existing files, inspection, and scope errors. Deletions are tombstoned rather than destroyed. |
| *Where was the agent when its context disappeared?* | **Best-effort compaction handoff.** When the conversation is compacted, Writ writes a derived record of mode, phase, approvals, the files the plan declared, the files actually written, unfinished items, and the rules that were loaded. The next prompt points the agent at it. |

**The floor: rules that can never be dropped.** Thirty-two of the 297 shipped engineering rules are marked mandatory. (This fork also ships 39 editorial design rules, four of them mandatory; the counts below cover the engineering 32.) These are deliberately kept **out of the search index entirely** and delivered through a separate channel with its own budget. Seven of them carry universal scope and inject on every turn; the other 25 are scoped to writes and keyword-gated, so they arrive the moment a write matches them rather than every turn. That means no change to search ranking, no swap of the underlying model, and no retuning of anything can cause a mandatory rule to fall out of delivery because of ranking. A single definition in one file decides what belongs to the floor, and both the delivery code and the validation code read that same definition, so the two cannot drift apart. This closed a real bug where two parts of the system checked different fields and left 29 of 32 mandatory rules unreachable by either path.
Writ keys these records by project and scopes its normal recall, memory, and retrieval paths accordingly. The shared rules and methodology corpus remains available across projects, by design.

**The auto-memory mirror is not version history.** A memory record reflects its latest contents. `writ memory audit` reports scope and disk drift but intentionally performs no automatic repair.

## Modes

| Mode | Purpose | Governance behavior |
|---|---|---|
| `conversation` | Discussion and brainstorming | No workflow gates |
| `review` | Evaluate code against applicable rules | Adds no workflow gates and supplies relevant review guidance |
| `investigate` | Research and codebase exploration | Captures web citations and command evidence, and reports whether sources span independent domains |
| `debug` | Diagnose a specific failure | Blocks source edits until a root cause is written down; evidence and narrowing are recorded alongside it, but do not themselves gate the write |
| `work` | Build or modify code | Requires an approved plan, then approved tests, before implementation |

**Dedicated reviewer.** Writ also ships a separate read-only reviewer that examines the actual diff from a fresh context and has no tool capable of editing the code.

Modes can be suggested automatically, set explicitly, or switched temporarily. Switching out of Work and back restores your paused phase and approvals if the plan is unchanged, and re-arms both gates if it changed while you were away.

## How rules evolve

Writ can record feedback and accept agent-proposed rules, but a proposal does not silently become policy. A candidate stays provisional until a human promotes it, and promotion spends the same one-time approval secret as everything else. The agent may propose. It cannot promote its own proposal.

This is a control that exists, not evidence that automatically proposed rules are effective.

## Day-to-day use

For a typical Work-mode change, two approvals: you read the plan and type `approved`, then you read the tests and type `approved`. After that the agent works without interrupting you, with one exception, which is a serious review finding adding a confirmation before the commit lands.

The non-Work modes add no approval steps.

Writ's rule corpus, project records, session state, and logs remain local. Optional Bitbucket Cloud synchronization sends per-file decision context only when configured. Installation downloads Python dependencies and the local embedding model. [`SECURITY.md`](SECURITY.md) documents the complete trust model.

For operators: `writ doctor` diagnoses a live install, `writ trust-ledger` records the skills, agents, and local MCP configuration you have accepted and reports when they change, and typed log streams separate governance decisions from operational noise.

## Who it is for

Engineers and engineering leads who need parts of a coding-agent workflow governed outside the model rather than left as instructions, and who can answer for the code afterward. Writ ships opinionated plan-first and test-driven defaults, with the mode and gate machinery underneath them.

**Who it is not for.** If you need enforcement against an agent that is actively adversarial, this is not that tool. Writ constrains a cooperative agent. [`SECURITY.md`](SECURITY.md) writes the gaps down rather than glossing them.

The shipped rulebook is opinionated and reflects where its author has worked. Treat it as a working example rather than a universal standard; commands exist for adding and editing your own.

## Limits

These change what a block means, so they are stated here rather than buried.

- **When the background service is unreachable, hooks allow rather than block.** This is the specification, not a bug: an infrastructure outage must never lock you out of your own repository. Setting `WRIT_STRICT=1` inverts that for the write path.
- **The gate can tell that a plan exists. It cannot tell whether the plan is any good.** The validators check shape, not thought. A plausible plan and a careful one look identical to a machine. Writ relocates oversight; it does not remove it.
- **Some controls report rather than refuse.** The investigate-mode source check and the trust ledger record what they find and leave the judgment to you. The debug gate and the write gates refuse.
- **The egress guard asks, it does not block.** It cannot tell whether an outbound payload carries repository material, so it surfaces the decision instead of guessing.
- **Shell inspection is pattern-based, not a sandbox.** Writ recognizes common redirections, copy destinations, and interpreter one-liners, but it cannot detect every write assembled through wrappers, variables, modules, or `eval`. The known gaps are documented in [`SECURITY.md`](SECURITY.md).

Two boundaries hold regardless, including when the service is down and inside sub-agents. Writes to credential files are refused in every mode with no server involved. And the approval token cannot be created or spent without a human keystroke, so advancing the workflow and writing new rules into the rulebook halt even when raw file writes do not.

Pull request comments currently support Bitbucket Cloud only. The session briefing and git notes work anywhere.

## Evidence

Writ distinguishes three kinds of claim, and so should you when reading anything here.

- **Mechanisms that are implemented and testable.** The gates, the approval binding, the credential classifier, the handoff. You can read these in the source and trigger them yourself.
- **Measured outcomes.** Retrieval quality, retrieval cost, and how rule text per turn behaves as the rulebook grows. Method, figures, and corrections live in [`SCALE_BENCHMARK_RESULTS.md`](SCALE_BENCHMARK_RESULTS.md), which owns those numbers so this page does not go stale carrying copies.
- **Claims not yet demonstrated.** That an agent handed the right rule complies more often than one handed nothing. This is not demonstrated, and Writ runs no headless experiments to demonstrate it.

Two things are independently checkable before you install anything. [`docs/pressure-runs/`](docs/pressure-runs/) holds adversarial runs against real Claude Code sessions, each with the prompt, the full transcript, every enforcement decision as raw log lines, and a graded analysis of which rules held and which were bypassed, with the failures written up as failures. [`docs/monthly-reviews/`](docs/monthly-reviews/) holds operational reviews built from the system's own audit log.

## Documentation

| | |
|---|---|
| [`HANDBOOK.md`](HANDBOOK.md) | The operator manual. Modes, gates, helper agents, the rulebook, the command line. |
| [`docs/install.md`](docs/install.md) | Both install paths, background service, troubleshooting. |
| [`docs/instructions-vs-enforcement.md`](docs/instructions-vs-enforcement.md) | Why an instruction and an enforcement point are different primitives. |
| [`docs/reference/`](docs/reference/) | Precise contracts: architecture, schema, retrieval, sessions and gates, configuration, logging, decision memory, testing. |
| [`SECURITY.md`](SECURITY.md) | The trust model, what leaves the machine, and how to report a vulnerability. |
| [`CONTRIBUTING.md`](CONTRIBUTING.md) | Authoring rules, review cadence, triaging agent proposals. |
| [`CHANGELOG.md`](CHANGELOG.md) | Release history. |
| [`ERRATA.md`](ERRATA.md) | Corrections to figures this project has published. |

Skills are discovered from context and selected by the model. Writ can also react to what the agent is actually doing.

A rule that should fire because Claude is editing a controller containing a raw SQL query does not need the user to have typed "SQL." Writ can observe the write, inspect the file and tool context, and deliver the relevant rule at that moment.

That moves rule selection away from:

> Does the model realize this skill is relevant?

toward:

> What action is actually happening right now?

For small skill counts, discrete behaviors, model-side selection, and zero infrastructure, Skills are the simpler answer.

For large rulebooks, action-sensitive rules, human approval boundaries, and workflows whose mandatory steps must be capable of refusing an action, Writ is solving a different problem.

## Decision provenance: why each file changed

This is not conversational memory. Writ does not read your chat history and guess what mattered. It builds the record mechanically, from things that already exist.

When you commit, a git hook joins the commit's files against the **approved plan**, the rules each session and helper AI actually looked up for each file, and any earlier open decisions. It writes three kinds of record into the same graph as the rulebook, connected by typed relationships, with identifiers derived from content so that amending a commit updates the record instead of duplicating it. The hook never blocks a commit and does nothing harmful when the service is down. A backfill command reconstructs the history for commits made before you installed it.

Each file-change record carries the reason for the change, the rules the AI was shown, and the rules it cited. That last grounding is the distinguishing property: every decision stays tied to the rule identifiers that governed it, and those survive every round of trimming when the record gets too large.

The record plays back in three places:

* **A session briefing.** Recent decisions get compiled into a size-limited digest and the top of it is injected into your first message of a new session, so the AI starts knowing what was decided and why. Under pressure the reasoning trims first, then the per-file notes, then the oldest decisions. Identifiers, titles, and governing rules are never trimmed.
* **Pull request comments.** One comment per changed file: why it changed, which rules the AI was shown, and which it cited. It updates its own comments rather than piling up duplicates. Reviewers read the reasoning next to the diff instead of reconstructing it.
* **Git notes.** The same content is written into git itself, which needs no server and travels with the repository anywhere.

**Be clear on what this is.** It is an attribution trail: what the AI was shown and what it claimed to apply. It is not proof that a rule was followed. That is still a reviewer's job, which is exactly why the pull request channel exists. And it is only possible because Writ owns the approval gate. A memory layer bolted onto an AI has no approved plan to join against.

Pull request comments currently support Bitbucket Cloud only, and self-hosted Bitbucket Server is explicitly rejected rather than silently broken. The briefing and git notes channels work anywhere. Full detail in [`docs/reference/decision-memory.md`](docs/reference/decision-memory.md).

## Measured

**Evidence today.** Every figure below is a dated measurement, not a live readout, taken on one developer machine with an uncapped database container, so your numbers will differ.

* **Search quality.** 0.923 hit rate at 5 across the 169 index-eligible questions of the gold set, and 0.608 mean reciprocal rank at 5 across the 47 deliberately ambiguous ones (2026-08-06).
* **Search cost.** A warm 95th percentile of 0.827 ms in the published synthetic run against 10,000 rules (2026-08-01).
* **Rule text per turn stays roughly flat as the rulebook grows.** About 2,000 tokens against the live 287-rule corpus (2026-08-05), about 1,590 against the 10,000-rule synthetic one (2026-08-01).
* **The floors are gates, not aspirations.** Seventeen benchmark targets run in continuous integration on every push and every pull request, and they passed 17 of 17 on 2026-08-14.

Full dated measurements, the methodology behind each one, the corrections, and the historical runs live in [`SCALE_BENCHMARK_RESULTS.md`](SCALE_BENCHMARK_RESULTS.md).

## Not measured

Everything above measures what the search **costs** and how well it ranks. None of it measures whether an AI given the right rule **actually complies** more often than one given nothing. That is Writ's central claim and it is currently unproven.

The harness to test it exists. It runs matched Claude Code sessions with Writ on and Writ off against a deliberately planted security defect, scoring whether the defect was caught and at what cost. It has not been run at a scale that proves anything. At one repetition the result is reported as insufficient by design, because a single run cannot beat the randomness in how AI sessions unfold. What is still needed: many repetitions with a noise floor, a defect suite broader than the single planted case, and a cheaper scoring judge.

A second thing is unproven, and smaller only by comparison. The search runs five stages, one of which walks the rule graph, and **that stage is the reason this project needs a graph database at all**. Its individual contribution has never been isolated. Nobody has run the test set with graph traversal disabled and compared the ranking quality, so the honest position is that the dependency is justified by design reasoning rather than by a measurement. The nondeterminism finding makes this more pressing rather than less: if iteration order was quietly deciding thirty questions' results, per-stage attribution was even shakier than it looked. The number will be published wherever it lands, including at or near zero.

Until those experiments exist, treat the enforcement claim as a designed mechanism with an honestly documented failure posture, not a demonstrated outcome.

What **is** independently checkable today lives in the repository rather than in assertions. [`docs/pressure-runs/`](docs/pressure-runs/) contains adversarial test runs against real Claude Code sessions: the exact prompt used, the full transcript, every enforcement decision as raw log lines, and a graded analysis scoring each targeted rule as held or bypassed, including the failures, documented as failures. [`docs/monthly-reviews/`](docs/monthly-reviews/) contains operational reviews built from the system's own audit log.

## The rulebook is opinionated

336 rules ship in the box: 76 security, 45 code quality, 41 communication (39 of them the fork's editorial design rules), 28 architecture, 21 testing, 19 performance, 19 process, and smaller sets besides. The shape reflects where its author has worked. There are 12 Magento 2 rules and exactly one PHP typing rule, which tells you something true about where it came from.

Treat the shipped rulebook as a working example, not a universal standard. Commands for adding and editing rules exist so you can grow your own, and there is a full lifecycle for rules the AI itself proposes: a proposed rule lands marked provisional, gets promoted to a review queue only after enough real-world evidence accumulates, and enters the canonical rulebook only through a human approval that requires the same one-time secret as everything else. The statistics never promote anything on their own.

## Where Writ sits against other approaches

These are approaches to coding-agent governance, not products. Each is a reasonable way to give an agent rules, and each runs into a structural limit that shaped Writ's design.

* **Rules stuffed into the context.** Cost grows with the rulebook and the signal gets buried in it. Writ retrieves instead, so the per-turn cost stays roughly flat as the rulebook grows.
* **Static skill files.** Point-in-time bundles with no relationships between them. Writ keeps rules in a knowledge graph with typed links, so a matched rule can pull in its neighbors, including ones that share no words with what you asked.
* **Per-repo rules as code.** Nothing propagates between repositories, and each copy drifts on its own. Writ keeps one shared graph with per-project isolation.
* **An AI validator on every diff.** A model call per change, and the same code can be judged differently twice. Writ's gates are code, so an ordinary turn costs no model call at all.
* **Rules in the system prompt.** Editing the rulebook changes the prefix every request shares. Writ injects per turn instead, and keeps rule ordering stable so the shared prefix does not churn.

## Research and reference artifacts

Two things in this repository are reference material rather than product documentation, and both stand on their own.

### The Claude Code hook black box

[`docs/reference/claude-code-blackbox.md`](docs/reference/claude-code-blackbox.md) is a version-pinned, empirical map of exactly what Claude Code hands a hook script and exactly what a script can hand back. Captured live on build 2.1.220 and compared against 2.1.183. Every single field carries an evidence tag: observed in real data, documented but not seen, or unverified. The build pin covers the original capture, and the file has kept growing since: it also carries findings observed on 2026-08-11 and 2026-08-14, each stamped with its own date. Read the tag next to a claim rather than the version at the top.

It records five events that moved from documented only to actually observed, payload fields the public changelog never announced, and the mechanism that lets a script rewrite a tool call before it runs without the AI ever seeing the change. It is written so a non-engineer can follow the idea in Part 1 and an engineer can build against the detail in Part 2.

It is useful whether or not you use Writ. It is the reference this project wishes had existed.

### Architecture, in your browser

Six self-contained pages with interactive diagrams and a live explorer for the graph itself:
[`docs/reference/claude-code-blackbox.md`](docs/reference/claude-code-blackbox.md) is reference material that stands on its own: an empirical map of what Claude Code hands a hook and what a hook can hand back, with an evidence tag on every field. Useful whether or not you use Writ.

**Architecture in your browser:**
[overview](https://infinri.github.io/Writ/docs/architecture/index.html) |
[data model](https://infinri.github.io/Writ/docs/architecture/data-model.html) |
[retrieval](https://infinri.github.io/Writ/docs/architecture/retrieval-pipeline.html) |
[injection channels](https://infinri.github.io/Writ/docs/architecture/injection-channels.html) |
[graph explorer](https://infinri.github.io/Writ/docs/architecture/knowledge-graph.html) |
[corpus round trip](https://infinri.github.io/Writ/docs/architecture/corpus-roundtrip.html)

## Contributing and support

* [`openwiki/index.md`](openwiki/index.md): the wiki. A reading order for newcomers, a quickstart, and one section per area.
* [`HANDBOOK.md`](HANDBOOK.md): the operator manual. Modes, gates, helper AIs, the rulebook, the command line, day-to-day use.
* [`docs/reference/`](docs/reference/): precise contracts. Architecture, graph schema, retrieval, sessions and gates, configuration, logging, decision memory, testing.
* [`docs/install.md`](docs/install.md): both install paths, running it as a background service, and troubleshooting.
* [`CONTRIBUTING.md`](CONTRIBUTING.md): how to author rules, the review cadence, and triaging AI proposals.
* [`CHANGELOG.md`](CHANGELOG.md): release history through v1.7.0.
* [`SECURITY.md`](SECURITY.md): the trust model stated plainly, how to report a vulnerability, and why auditing what you install stays your job.
* [`ERRATA.md`](ERRATA.md): corrections to figures this project has published, including the ones with no consumer that are deliberately kept out of this file.
Found a bypass, or a case where a rule you relied on did not hold? That is the most valuable thing you can send. Open an issue with the transcript. For anything exploitable, report privately through [GitHub Security Advisories](https://github.com/infinri/Writ/security/advisories/new) rather than in public.

Want to contribute rules or code? [`CONTRIBUTING.md`](CONTRIBUTING.md) covers authoring, the review cadence, and how agent-proposed rules are triaged.

Writ is free and developed in my own time. If it saves you some of yours, you can optionally support its continued development with [a coffee](https://buymeacoffee.com/infinri).

## Acknowledgements

**[Superpowers](https://github.com/obra/superpowers), by Jesse Vincent**, for formalizing the discipline Writ builds enforcement around. The architectural disagreement is argued in [`docs/instructions-vs-enforcement.md`](docs/instructions-vs-enforcement.md#superpowers-and-the-definition-of-mandatory).

**[Jolli](https://www.jolli.ai/), by [JolliAI](https://github.com/jolliai/jolliai)**, for work on preserving development reasoning after a session ends. Writ's digest eviction policy is adapted from Jolli's ContextCompiler, the policy rather than the code, and `writ/session/recall.py` documents the adaptation.

---

License: MIT. Authored by Lucio Saldivar.
