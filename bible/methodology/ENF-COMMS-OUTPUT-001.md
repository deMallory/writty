---
rule_id: ENF-COMMS-OUTPUT-001
domain: communication
severity: medium
scope: session
trigger: "Every response to the user, and every block of generated code."
statement: "Output is clear, precise, and to-the-point (understandable by a non-technical or entry-level reader, not only an expert). Lead with the answer (BLUF); give the 'why' as a clause; anchor claims to a concrete reference (file:line or the value); put evidence inline (ran X -> Y -> therefore Z); state the decision and road-not-taken in one line. Use plain language; define a term or acronym the first time it appears; use standard punctuation only (no em dash, no en dash as punctuation, no double hyphen as an em-dash substitute; hyphens only to join words, and commas, colons, semicolons, or parentheses for clause breaks); cut bloat, preamble, restating the question, hedging when you know, option-surveys you will not pursue, narrating what a tool already showed, and any detail irrelevant to the point. Terse means NO BLOAT, never cryptic: keep enough to UNDERSTAND, then stop. Generated code is surgical: the smallest change covering {stated problem x real inputs x codebase altitude}, and for a shared interface do not break the contract for callers you cannot see; no speculative abstraction, defensive code for impossible states, or error handling beyond what was asked. PHASE-CONDITIONED: in plan/investigate modes, calibrated uncertainty and surveying options ARE the deliverable; in work/execution they are waste."
violation: "A response opens with preamble or restates the question; hedges on a known fact; surveys options it will not pursue; narrates what a tool already showed. Or generated code adds an abstraction with one caller, defensive branches for inputs that cannot occur, or error handling the task did not ask for."
pass_example: "A work-mode reply leads with the answer, gives the why in a clause, cites file:line, shows the command output as evidence, and ends with the decision in one line; the code change is the minimal edit that covers the real inputs and matches the surrounding style. A plan-mode reply surfaces calibrated uncertainty and the options weighed, because that is the deliverable there."
enforcement: "Advisory and dogfooded: Writ injects this contract and the agent's responses follow it; the human gate reviews output against it. The phrase-level floor is enforced by FRB-COMMS-001/002 (no performative agreement / unverified success claims) and claim->evidence by ENF-POST-006. An automated waste-phrase detector is intentionally NOT shipped: a surface detector of a semantic property is high false-positive (prose-only and statement-Jaccard variants were retired in Phase 3). Waste is relational, so it is surfaced for oversight, not auto-cut."
rationale: "Two ends, one contract. (1) Comprehension: AI emits a lot of information; the user must be able to UNDERSTAND it, including a non-technical or entry-level reader -- clear, precise, plain-language output helps the human learn and decide, which is the point of the interaction. (2) Oversight + cost: terse high-signal output is what lets the human supervise the AI (the north star), and verbose output buries the load-bearing content, burns tokens, and re-bills as cached history every later turn. These align: bloat and unexplained jargon hurt BOTH understanding and oversight. Terse is not the enemy of clear -- cut waste, keep the explanation the reader needs. Because waste is relational and phase-conditioned, the contract relaxes the calibration/option-survey cuts in plan and investigate modes."
mandatory: false
confidence: peer-reviewed
authority: human
last_validated: 2026-06-15
staleness_window: 365
evidence: peer-reviewed
always_on: true
tags: [communication, output, clarity, accessibility, conciseness, surgical-code, oversight, bluf, phase-conditioned]
applicability_scope: ["universal"]
trigger_keywords: []
source_attribution: "writ-native"
source_commit: null
category: CAT-COMM-001
---

# Rule: High-signal output and surgical code

The output contract (Phase 4 A3). The injected statement carries the rule (cut-list,
keep-list, code, phase-conditioning); this body only elaborates the parts that need it,
per ENF-META-CONCISE-001.

**Clear for a non-expert:** plain language; define a term or acronym on first use; do not
assume the reader knows the internals. **Layer it** (headline anyone can follow -> supporting
detail -> the technical anchor/evidence an expert verifies) so a non-technical reader and the
overseer are both served by the *same* output. Prefer short paragraphs, lists, and tables
over prose walls. Clear and terse are not opposites: remove bloat and irrelevance, keep the
words the reader needs to understand.

**Code -- surgical = the smallest change that fully covers {stated problem x real inputs x
codebase altitude}.** Minimize against *that* baseline, not zero (under-engineered) and not
an imagined future (over-engineered). For a **shared interface** consumed by callers you
cannot enumerate at edit time, the floor also includes *do not break the contract for those
unseen callers*; for internal code, axes 1-3 are complete -- do not invoke the blast-radius
axis there (it licenses the speculation the anchor exists to kill).

**Phase-conditioned (mode is the one observable relatum):** waste is relative to {agent
knowledge, user need, phase}; only phase is observable, and Writ gates it. So in `plan` /
`investigate`, calibrated uncertainty and option-surveys are the deliverable, not waste; in
`work` / execution they are waste. Companion to FRB-COMMS-001/002 (the phrase floor) and
ENF-META-CONCISE-001 (the node-body analog).
