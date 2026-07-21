# ACS Absorption Plan for Writ (verified)

Competitive analysis between this project (`~/.claude/skills/writ`) and the
**Anthropic-Cybersecurity-Skills** repository ("ACS", `~/workspaces/Anthropic-Cybersecurity-Skills`,
*not* affiliated with Anthropic PBC).
Captures what ACS does that Writ does not, where the two overlap, which ACS
features are worth absorbing into Writ (done Writ's way), and who does the
overlapping things better. Modeled on the format of `hcf_absorption.md` and
`jolli_absorption.md`.

---

## Provenance and verification status

There was **no prior ACS absorption plan in the Writ repo.** The only absorption
plans present were `hcf_absorption.md` (HCF, Mark Shust) and `jolli_absorption.md`
(Jolli). The user's recollection of an "Anthropic-Cybersecurity-Skills absorption
plan" did not match a file on disk (grep for `cybersecurity|mukul|att&ck|mitre|d3fend`
across `bible/` and the repo root returned only `bible/enforcement/reasoning-discipline.md`).
This document is the first, produced **2026-06-02** from a full audit.

**What was read (no-skip mandate):**

- **ACS infrastructure, in full:** `README.md`, `CONTRIBUTING.md`, `index.json`
  (schema + all 754 entries), `ATTACK_COVERAGE.md`, `tools/validate-skill.py`,
  `mappings/` (mitre-attack/owasp/nist-csf READMEs + coverage-summary +
  attack-navigator-layer.json), `.claude-plugin/{plugin,marketplace}.json`.
- **All 754 ACS skill directories.** 608 skills (8 of 10 alphabetical batches)
  were deep-read by sub-agents: every `SKILL.md` in full plus every
  `references/*` and `scripts/*` file. The remaining 152 skills (batches
  `analyzing-windows-shellbag…→configuring-microsegmentation…` and
  `performing-kubernetes-etcd…→performing-vlan-hopping`) tripped the Claude
  cyber-content safeguard inside the reader sub-agents and were instead covered
  by a **mechanical structural/metadata sweep** (file inventory, frontmatter
  fields, version/subdomain/author values, templated-filler and stub detection)
  computed directly from the files. Their structure is identical to the other
  eight batches; I did not deep-read their offensive prose, and the body/script
  quality claims for those 152 are inferred from the convergent pattern, not
  individually verified.
- **Writ, in full:** `HANDBOOK.md`, `README.md`, `bible/` corpus (schema +
  representative nodes across domains), `writ/` Python package (`cli.py`,
  `retrieval/pipeline.py`, `graph/schema.py`, `graph/methodology_ingest.py`,
  `graph/integrity.py`, `gate.py`, `frequency.py`), `bin/lib/writ-session.py`,
  `.claude/hooks/`, `.claude/agents/`, `templates/settings.json`,
  `out-of-the-box-rules.md`, and both existing absorption plans for format.

Every "Writ today" line below is verified against source. ACS counts are exact
where mechanically computed and qualitative where they describe content quality.

### The single most important framing

**ACS and Writ are different genres, not competitors at the same layer.**

- **ACS is a content library**: 754 cybersecurity *task playbooks* (how to run
  Volatility, hunt Cobalt Strike beacons, kerberoast under authorization, write
  Suricata rules), each a directory of `SKILL.md` + references + runnable scripts,
  mapped to security frameworks, discoverable by scanning frontmatter. It is a
  **breadth** asset with **almost no enforcement and loose internal consistency**.
- **Writ is an enforcement engine**: a Neo4j-backed RAG pipeline over a
  ~283-node rule/methodology corpus, plus a hook-driven session state machine that
  gates code writes. It is a **depth/governance** asset with **deep enforcement
  and tight schema discipline, but almost no security *content*** (≈74 defensive
  coding rules; zero offensive/DFIR/threat-hunting playbooks).

Because of this, the audit is lopsided: ACS has a great deal Writ lacks
(content, framework mapping, the agentskills.io packaging), Writ has a great deal
ACS lacks (retrieval, validation, dedup, evolution, enforcement), and the genuine
head-to-head overlaps are few. The high-value move is **Writ ingesting ACS's
content and metadata into Writ's disciplined substrate**, not Writ copying ACS's
loose authoring conventions.

---

## Enforcement floor: do not erode

Same load-bearing set as the HCF/Jolli plans. Anything absorbed from ACS must
**extend Writ's primitives, never swap them for ACS's looser ones.** ACS is
permissive precisely because it has no enforcement floor; importing its
conventions naively would erode Writ's defining feature.

- Mechanical write-gates in `bin/lib/writ-session.py` (`_can_write_check`:
  design-approved, phase-a/plan, test-skeletons) and the validator hooks.
- The ~30-33 mandatory always-on rules loaded out-of-band via `/always-on` with
  their own 5,000-token budget, excluded from the pipeline at index-build time.
- The one-time, session-keyed approval token (`/tmp/writ-gate-token-{sid}`);
  agent self-approval is blocked and logged.
- Sub-agent isolation (`writ-subagent-start.sh`, `is_subagent:true`).
- Authority preference (human rules outrank AI rules at equal relevance).
- The ingestion gate (`writ/gate.py::structural_gate`): schema, vague-language,
  redundancy ≥0.95, novelty ≥0.85, conflict edges. **This is exactly the gate ACS
  lacks; absorbing ACS content must pass through it, not around it.**

---

## Verified baseline: what Writ has today

| Area | Writ today (verified) | Evidence |
|---|---|---|
| Knowledge model | 12 node types (Rule + Skill/Playbook/Technique/AntiPattern/ForbiddenResponse + 5 non-retrievable); 14 edge types | `writ/graph/schema.py` |
| Corpus size | ~283 rules live, ~33 mandatory, ~17 domains | `writ status`, `out-of-the-box-rules.md` |
| Security content | ~74 security **Rule** nodes (defensive coding) in 9 SEC-* families; **0 security Skill/playbook nodes** | `bible/security/rules.md` |
| Retrieval | 5-stage pipeline (domain → BM25/Tantivy → ANN/hnswlib → graph → RRF rank), ~0.34 ms median / 0.59 ms p95 | `writ/retrieval/pipeline.py`, `README.md` |
| Indexing | BM25 keyword + 384-dim MiniLM ONNX vectors + graph adjacency, corpus-hash-cached | `build_pipeline` |
| Ingestion | `import-markdown` → Pydantic validation → Neo4j, typed `IngestError`, auto-export | `graph/methodology_ingest.py` |
| Integrity | conflicts / orphans / stale / redundant(cosine≥0.95) / unreviewed-AI / frequency-stale | `graph/integrity.py`, `writ validate` |
| Quality gate | structural gate (schema, vague-language, redundancy, novelty, conflict) + mandatory-rule mechanical-enforcement-path requirement | `writ/gate.py` |
| Framework mapping | **none** — no CWE/OWASP/MITRE/NIST field on any node; 3 incidental OWASP mentions in prose | `grep` across `bible/` |
| Staleness | `last_validated` + `staleness_window` (default 365d) per node | `schema.py`, `integrity.detect_stale` |
| Evolution | propose (ai-provisional/speculative) → frequency graduation (n≥50, ratio≥0.75) → human `writ review --promote` | `gate.py`, `frequency.py` |
| Packaging | Claude Code plugin (`.claude-plugin/plugin.json` v1.5.0); ships 2 agentskills.io `SKILL.md` skills (jolli-recall, writ-approve); corpus is graph nodes, not SKILL.md dirs | `.claude-plugin/`, `.claude/skills/` |
| Enforcement | modes (conversation/debug/review/work + investigate); Work gates; approval token; mandatory floor; ~35 hooks | `writ-session.py`, `.claude/hooks/` |

## What ACS is (verified)

| Area | ACS today (verified) | Evidence |
|---|---|---|
| Genre | 754 cybersecurity task playbooks, 26 README domains | `README.md`, `ls skills/` |
| Skill layout | `SKILL.md` (YAML frontmatter + body) + `references/` + `scripts/` (+ `assets/`); agentskills.io standard | skill dirs |
| File completeness | 754 SKILL.md, 753 agent.py, 753 LICENSE, 751 api-reference.md — but only **289 standards.md / 288 workflows.md / 280 template.md / 275 process.py** (~37% "full") | `find skills -type f` |
| Framework mapping | **nist_csf on all 754**; d3fend 139 (18%), nist_ai_rmf 85 (11%), atlas 81 (11%), ATT&CK-in-frontmatter 48 (6%) | `grep` over frontmatter |
| Discovery | scan all 754 frontmatters (~30 tok each) + thin `index.json` (name/truncated-description/domain/path only) | `index.json`, `README.md` |
| Validation | `tools/validate-skill.py`: **frontmatter only** (5 required fields, kebab name, desc≥50 chars, subdomain in allow-list, ≥2 tags). Bodies, scripts, mappings, file-completeness: unvalidated | `tools/validate-skill.py` |
| Coverage docs | `ATTACK_COVERAGE.md` (291 techniques / 14 tactics), `mappings/*/coverage-summary.md`, ATT&CK Navigator layer | repo root, `mappings/` |
| Scripts | genuinely runnable, real tool APIs, no stubs in the deep-read 608 (rare exception: `reverse-engineering-rust-malware` stub refs) | sub-agent deep reads |
| Enforcement | **none.** No gates, no retrieval, no dedup, no staleness, no conflict detection | (absence) |

---

## Q1 — What ACS does that Writ does not

1. **Security task-playbook content at scale.** 754 offensive/defensive/DFIR/
   threat-hunting/cloud/OT procedures. Writ has ~74 *defensive coding rules* and
   zero attack/response playbooks. This is the largest single gap and the whole
   reason to look at ACS.
2. **External-framework mapping on every item.** Every skill is cross-walked to
   NIST CSF (universal), and many to MITRE ATT&CK / ATLAS / D3FEND / NIST AI RMF.
   Writ maps to *nothing* external — no CWE, OWASP, MITRE, or NIST field exists on
   any node.
3. **Coverage analytics over a framework.** `ATTACK_COVERAGE.md` and
   `mappings/*/coverage-summary.md` answer "which ATT&CK tactics/techniques are
   covered, where are the gaps." Writ has corpus-health checks but no
   coverage-vs-external-standard view.
4. **Runnable helper scripts shipped with knowledge.** `scripts/agent.py` /
   `process.py` are real, executable analysis tools bundled with the procedure.
   Writ nodes are text-only; they carry `mechanical_enforcement_path` pointers but
   ship no executable artifact.
5. **Reusable report/checklist templates.** `assets/template.md` (filled-in IR
   checklists, severity matrices, decision trees). Writ has no per-node artifact
   layer of this kind.
6. **agentskills.io packaging as the unit of distribution.** ACS skills are
   directory-mounted, model-invocable skills loadable by 26+ platforms
   (Cursor, Copilot, Codex CLI, etc.). Writ retrieves *into* context as RAG and is
   bound to its own Claude Code harness; it ships only 2 SKILL.md skills.
7. **Localization (nascent).** 6 skills carry a Spanish `SKILL.es.md`. Writ has
   no i18n concept. (Listed for completeness; low priority.)

## Q2 — What exists in both

These are real overlaps where a head-to-head "who does it better" applies:

| Capability | ACS | Writ |
|---|---|---|
| **Structured knowledge units with YAML frontmatter + Markdown body** | `SKILL.md` per skill | methodology/rule nodes per `.md` |
| **A taxonomy / domain classification** | `subdomain` (allow-list of ~30, alias-canonicalized in the validator) | `Rule.domain` (single-valued) + node types |
| **A discovery/index layer** | `index.json` + frontmatter scan | 5-stage retrieval + 3 indexes |
| **A metadata validator** | `validate-skill.py` (frontmatter only) | `writ validate` + ingestion gate (full schema + corpus health) |
| **Progressive disclosure** | frontmatter (~30 tok) → body → references | summary/standard/full budgets, mandatory out-of-band |
| **Claude Code plugin packaging** | marketplace.json / plugin.json | `.claude-plugin/plugin.json` |
| **A versioning field per unit** | `version:` (inconsistent `'1.0'` vs `1.0.0`) | `confidence` + `last_validated` + `staleness_window` |
| **A contribution/authoring path** | PR + CONTRIBUTING.md template | `writ add/edit/propose` + gates |

## Q4 — On the overlaps: who does it better

- **Knowledge unit schema → Writ, decisively.** ACS validates 5 frontmatter
  fields and never looks at the body, scripts, mappings, or file-completeness.
  Result (measured): version field split `'1.0'`/`1.0.0` repo-wide; ~37% of skills
  have the "full" file set the README claims is universal; ~48% of skills carry a
  templated boilerplate "When to Use" ("…security assessments that involve
  performing `<skill>`"); ATLAS/AI-RMF framework blocks copy-pasted verbatim onto
  non-AI skills (e.g. PhotoRec file-carving tagged with `AML.T00xx`); D3FEND
  (defensive) IDs tagged on offensive "exploiting-*" skills. Writ's Pydantic
  schema + structural gate would reject most of this at ingest.
- **Discovery/retrieval → Writ, decisively.** ACS discovery = scan 754
  frontmatters at runtime + a thin `index.json` whose descriptions are truncated
  mid-word. Writ = precomputed BM25 + ANN + graph traversal at 0.59 ms p95,
  scaling sublinearly to 10K nodes. ACS's only structured cross-reference (the
  framework tags) is not even indexed.
- **Validation/integrity → Writ, decisively.** ACS has no dedup (the audit found
  many near-duplicate skills: pass-the-hash vs pass-the-ticket; process-injection
  ×3; JWT ×2; XSS ×2; Nessus ×2; Calico/k8s-netpol trio; C2-beaconing trio), no
  conflict detection, no staleness. Writ has all three plus cosine-redundancy and
  frequency-staleness.
- **Versioning/freshness → Writ.** ACS `version:` is a free-text field nobody
  enforces. Writ ties freshness to `last_validated`/`staleness_window` with an
  integrity check that fails the build.
- **Doc/source-of-truth consistency → Writ.** ACS docs disagree with each other:
  ATT&CK version cited as **v18** (README), **v16** (ATTACK_COVERAGE.md), **v15**
  (mappings); domain count **26** (README) vs **24** (CONTRIBUTING) vs **34**
  (validator allow-list); body-section schema differs README vs CONTRIBUTING; the
  README's "every skill has standards/workflows/process/template" is false for
  ~63%. Writ exports its corpus from one graph (SSOT) and tests manifest lockstep.

**Where ACS does an overlapping thing better than Writ (Q5 candidates):**

- **Breadth and concreteness of content.** Even granting all the hygiene
  problems, ACS's *bodies and scripts are genuinely good*: real `tshark`/Zeek/
  Suricata/Volatility/Impacket commands, working entropy/beaconing detectors,
  RFC-accurate DMARC validators, IEC-62443 zone configs. Writ has nothing
  comparable in the security-operations space. **ACS wins on content; Writ should
  absorb it.**
- **External-standard cross-walk as a first-class field.** ACS treats "which
  control/technique does this map to" as structured metadata. Writ treats it as
  absent. **ACS's *idea* (not its sloppy execution) wins; Writ should absorb a
  validated version.**
- **Shipping invocable, self-contained skill units.** ACS's agentskills.io
  packaging makes a unit portable and directly model-invocable. Writ's
  retrieve-into-context model is better for *enforcement* but ACS's is better for
  *distribution*. **Hybrid opportunity (H-items).**

---

## Q3 / Q5 — Absorb (ACS has, Writ lacks), done Writ's way

Items are ordered by leverage. Each carries Touch points, Effort, Risk, Done-when,
in the HCF/Jolli idiom. Item codes: **A** = absorb a capability ACS has and Writ
lacks; **H** = hybrid/new design that takes ACS's idea but does it Writ's way.

### A1. External-framework mapping as a validated node field
- **ACS**: every skill carries `nist_csf` (754/754) and some carry
  `atlas_techniques` / `d3fend_techniques` / `nist_ai_rmf`; ATT&CK IDs live in
  `references/standards.md` prose. The *idea* is sound; the *execution* is sloppy
  (copy-pasted/mis-domained tags, ATT&CK not in frontmatter).
- **Writ today (verified)**: no external-standard field on `Rule` or any
  methodology node (`schema.py`); only 3 incidental "OWASP Top 10" prose mentions.
- **Writ's way**: add an optional, **validated** `framework_refs` block to the
  node schema (`{cwe: [...], owasp: [...], mitre_attack: [...], nist_csf: [...],
  d3fend: [...], atlas: [...]}`). Validate at ingest: IDs must match the
  framework's ID regex, and **domain-consistency** is enforced (ATLAS/AI-RMF only
  permitted when the node is AI/ML-scoped) — the exact check ACS lacks and that
  would have caught its mis-tagging. Index the field so retrieval can answer "rules
  mapped to T1003" or "controls for NIST CSF DE.CM."
- **Touch points**: `writ/graph/schema.py` (new optional field + validators),
  `graph/methodology_ingest.py` (parse), `gate.py` (domain-consistency check),
  `retrieval/pipeline.py` (Stage-1 optional framework filter + a `--framework`
  query flag in `cli.py`).
- **Depends on**: nothing. **Effort**: 3-4 days. **Risk**: medium (schema
  migration + re-ingest).
- **Done when**: a node can declare `framework_refs`, ingest rejects malformed or
  domain-inconsistent IDs, and `writ query --framework T1003` returns mapped nodes.

### A2. Coverage map over an external framework
- **ACS**: `ATTACK_COVERAGE.md` (291 techniques across 14 tactics) and
  `mappings/*/coverage-summary.md` — a static, hand/generated coverage view.
- **Writ today (verified)**: integrity checks report corpus *health* (orphans,
  stale, conflicts) but nothing maps coverage against an external standard.
- **Writ's way**: a `writ coverage <framework>` CLI command computed live from
  the A1 `framework_refs` index (not a hand-maintained markdown that drifts — ACS's
  three-different-ATT&CK-versions problem is the failure mode to avoid). Output:
  per-tactic/-category covered vs total, and the gap list.
- **Touch points**: new `cli.py` subcommand; a small framework-catalog data file
  (the ID universe per framework); reads the A1 index.
- **Depends on**: A1. **Effort**: 2 days. **Risk**: low.
- **Done when**: `writ coverage mitre-attack` prints coverage % per tactic and the
  uncovered-technique list, regenerated on demand.

### A3. Bulk import of ACS content into the Writ corpus (the big one)
- **ACS**: 754 task playbooks (bodies + scripts + mappings) — the content Writ
  most lacks.
- **Writ today (verified)**: ~74 defensive coding rules, 0 security playbooks;
  `Technique` and `Playbook` node types **already exist** in the schema and are
  exactly the right shape for ACS's procedural content.
- **Writ's way**: a one-time `scripts/import_acs.py` adapter that maps each
  `SKILL.md` → a `Technique`/`Playbook` node: frontmatter → node fields,
  `nist_csf`/ATT&CK → A1 `framework_refs`, body sections → node body,
  `references/standards.md` ATT&CK IDs hoisted into structured refs. **Every
  imported node passes the structural gate** — which means the import will *reject*
  the ~48% with templated filler bodies and the copy-pasted framework tags until
  they're cleaned. That is the feature: Writ ingests ACS's good content and its
  gate filters ACS's hygiene debt. Set `authority: ai-provisional`,
  `confidence: speculative`, `source_attribution: "ACS@<commit>"`, then let human
  review + frequency graduation promote. Do **not** import scripts as executable
  artifacts in v1 (no artifact layer yet — see H2); keep them as referenced source.
- **Touch points**: new `scripts/import_acs.py`; reuse `methodology_ingest.py`,
  `gate.py`; a dedup pass against existing nodes via the cosine check (ACS has
  internal near-duplicates A1's import must collapse).
- **Depends on**: A1 (so mappings survive import). **Effort**: 1-2 weeks
  (adapter + cleanup loop on gate rejections + dedup). **Risk**: high
  
- **Done when**: a defined subset (e.g. the ~280 "full" skills, highest quality)
  is imported as gate-passing `Technique`/`Playbook` nodes, retrievable, with
  ATT&CK/CSF mappings indexed and ACS attribution preserved; rejected skills are
  logged with the gate reason.

### A4. A skill/playbook *linter* mirroring ACS's gaps as Writ rules
- **ACS**: its `validate-skill.py` checks only frontmatter; the audit surfaced a
  precise list of what it *should* check (version-format normalization, subdomain
  alias canonicalization, no slug-derived tag lists, no truncated descriptions,
  no templated-filler bodies, full-set file completeness, domain-consistent
  framework tags, mandatory authorization banner on offensive content).
- **Writ today (verified)**: the ingestion gate already does the *kind* of check
  ACS lacks, but has no notion of these specific authoring smells.
- **Writ's way**: encode each smell as a methodology/anti-pattern node or a gate
  sub-check, so they apply to A3's imports *and* to native authoring. The
  "authorization banner required when content is offensive" rule is a clean
  policy-gate candidate Writ can enforce mechanically (ACS leaves it to prose, and
  the audit found several dual-use skills — ASM, burpsuite-intercept,
  darkweb-monitoring, AiTM — missing the banner).
- **Touch points**: `gate.py` sub-checks; new `ANT-*`/`ENF-*` nodes in
  `bible/`. **Depends on**: pairs with A3. **Effort**: 2-3 days. **Risk**: low.
- **Done when**: importing or authoring a node with templated filler, a
  domain-inconsistent framework tag, or offensive content lacking an authorization
  declaration is flagged/denied with the specific reason.

### H1. agentskills.io export of Writ's retrievable nodes
- **ACS**: every unit is a portable, model-invocable `SKILL.md` directory loadable
  by 26+ platforms.
- **Writ today (verified)**: packaged as a Claude Code plugin and ships 2 SKILL.md
  skills, but its corpus is graph-only and bound to its own harness; `Skill`/
  `Playbook` nodes already carry frontmatter + body.
- **Writ's way (hybrid)**: a `writ export-skills` command that renders selected
  retrievable nodes (Skills/Playbooks/Techniques) to agentskills.io `SKILL.md`
  directories — the inverse of A3. Writ keeps enforcement/retrieval as its
  internal model; the export makes its *content* portable without giving up the
  graph as SSOT. This is the "best of both": ACS's distribution format on top of
  Writ's disciplined corpus.
- **Touch points**: new `cli.py` subcommand reusing the `render_agent_md`-style
  renderer pattern already used for `.claude/agents/`. **Depends on**: A3 gives it
  content worth exporting. **Effort**: 3-4 days. **Risk**: low.
- **Done when**: `writ export-skills --domain security` emits valid agentskills.io
  skill dirs that pass ACS's own `validate-skill.py`.

### H2. Optional executable-artifact layer for nodes
- **ACS**: ships real `scripts/*.py` next to each procedure.
- **Writ today (verified)**: nodes are text + a `mechanical_enforcement_path`
  string; no bundled executable artifact.
- **Writ's way (hybrid, deferred)**: allow a node to reference a vetted script in
  a Writ-owned `scripts/library/` (not arbitrary imported code), surfaced when the
  node is retrieved. Keep it optional and reviewed — importing 753 third-party
  scripts wholesale would blow past Writ's quality floor and is a supply-chain
  surface. **Defer until A3 proves the content is worth it.**
- **Touch points**: schema (`artifact_path`), retrieval surfacing, a review gate
  for any script entering the library. **Depends on**: A3. **Effort**: 1 week.
  **Risk**: medium-high (supply chain; scope creep). **Do last.**

---

## Explicitly NOT absorbing (and why)

- **ACS's frontmatter-only validation model** — it is the cause of every hygiene
  defect the audit found. Writ's gate is strictly better; do not soften it.
- **ACS's free-text `version` field and subdomain alias tolerance** — Writ already
  has `confidence`/`last_validated` and a typed domain; adding ACS's looser fields
  would regress.
- **Hand-maintained coverage markdown** (`ATTACK_COVERAGE.md` style) — it drifted
  into three ATT&CK versions. A2 computes coverage live instead.
- **Wholesale script import as executables** — supply-chain risk; H2 gates it.
- **ACS's templated body scaffolding** (byte-identical `workflows.md`/
  `template.md` across skills) — low-information filler; A4 flags it.

---

## Priority, critical path, and first sprint

| Item | Type | Effort | Risk | Unlocks |
|---|---|---|---|---|
| A1: validated `framework_refs` field | Absorb | 3-4d | medium | A2, A3, coverage queries |
| A4: skill/playbook linter (ACS-gap rules) | Absorb | 2-3d | low | clean A3 imports |
| A2: live coverage map command | Absorb | 2d | low | gap analysis |
| A3: bulk ACS content import (gated) | Absorb | 1-2wk | high | the security-content gap |
| H1: agentskills.io export | Hybrid | 3-4d | low | distribution |
| H2: executable-artifact layer | Hybrid | 1wk | med-high | parity w/ ACS scripts (defer) |

**Critical path:**
- **A1 is the bottleneck**: A2, A3, and H1 all want structured framework refs.
- **A4 should land alongside A1** so A3's import is filtered by the right rules.
- **A3 is the highest-value, highest-risk item** — it closes Writ's defining
  weakness (no security playbooks) but only pays off if A1/A4 keep ACS's hygiene
  debt out of the corpus. Do A1 + A4 first, then A3 on a quality-ranked subset.

### Ready to start: first sprint (low risk, high leverage)
1. **A1 (3-4d)**: add the validated `framework_refs` field + ingest validators +
   `--framework` query flag. Re-ingest.
2. **A4 (2-3d, parallel)**: encode the ACS-gap authoring rules (version-format,
   subdomain canonicalization, no-filler-body, full-set completeness,
   domain-consistent framework tags, mandatory authorization banner on offensive
   content) as gate sub-checks / `ANT-*` nodes.
3. **A2 (2d)**: `writ coverage <framework>` from the A1 index.

After the first sprint, scope **A3** against the ~280 "full" ACS skills (highest
quality), import as `ai-provisional` `Technique`/`Playbook` nodes with ACS
attribution, and let human review + frequency graduation promote. Then **H1** to
make the result portable.

When any item becomes active implementation, it moves into a `plan.md` at the repo
root with the four required sections (`## Files`, `## Analysis`, `## Rules
Applied`, `## Capabilities`), per the Work-mode workflow Writ enforces on itself.
