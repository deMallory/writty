---
technique_id: TEC-META-PERSUASION-001
node_type: Technique
domain: meta-authoring
severity: medium
scope: task
trigger: "When authoring a discipline-enforcing node (Rule, AntiPattern, ForbiddenResponse) that must hold while the agent is under time, sunk-cost, or authority pressure."
statement: "Match the persuasion lever to the node's job. Discipline nodes lead with authority (imperative MUST/never, 'no exceptions'), commitment (require an explicit announcement or checklist tick), and social proof (cite the established convention). Do not lean on liking or reciprocity for discipline; they invite negotiation."
rationale: "LLMs respond to the same persuasion principles as people (Cialdini 2021; Meincke et al. 2025 measured compliance roughly doubling, 33%->72%). A rule phrased as a suggestion gets rationalized away under pressure; a rule phrased with authority and commitment holds."
tags: [meta, authoring, persuasion, compliance, authority, commitment, technique]
confidence: peer-reviewed
authority: human
last_validated: 2026-06-02
staleness_window: 365
evidence: peer-reviewed
source_attribution: "writ-native"
source_commit: null
edges: []
category: CAT-META-001
trigger_keywords: ["persuasion", "authority", "commitment", "social proof"]
---

# Technique: Persuasion levers by node type

| Node intent | Levers to use | Avoid |
|-------------|---------------|-------|
| Discipline (Rule/AntiPattern/ForbiddenResponse) | Authority (imperative, no-exceptions), Commitment (announce/checklist), Social proof (cite convention) | Liking, Reciprocity (invite negotiation) |
| Technique / Skill (how-to) | Concrete authority of a worked example; scarcity of the failure it prevents | Over-imperative framing (it is advisory) |

Authority: "Write code before the test? Delete it. No exceptions." beats "consider tests first."
Commitment: require the agent to announce the rule or tick a checklist item before proceeding.
Use this to make discipline nodes bulletproof, not to manipulate; the goal is compliance under pressure.
