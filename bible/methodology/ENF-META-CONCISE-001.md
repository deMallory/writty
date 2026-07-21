---
rule_id: ENF-META-CONCISE-001
domain: meta-authoring
severity: low
scope: task
trigger: "When authoring or revising any methodology node, before committing it."
statement: "A node body must justify its token cost. The statement is the retrieval surface and carries the rule; the body stays lean. Per-node-type body budgets: Rule/AntiPattern <= 200 words, Technique/Skill <= 320, Playbook <= 600. Cut anything the agent already knows or that another node already says."
violation: "A node body restates context the trigger already gave, includes several examples of one pattern, or explains what is obvious from a command, pushing it past its per-type word budget."
pass_example: "The body states only the non-obvious, cross-references other nodes instead of repeating them, uses one strong example, and falls within the per-type budget."
enforcement: "Authoring-time word-budget check (tests/test_inc3_authoring_uplift.py::TestConcise asserts authored meta nodes are within budget); reviewers apply the budget to other node types during review."
rationale: "Frequently-loaded nodes enter every relevant context window; bloat taxes every conversation. Context is a shared resource, so each node pays for the tokens it spends."
mandatory: false
confidence: peer-reviewed
authority: human
last_validated: 2026-06-02
staleness_window: 365
evidence: peer-reviewed
mechanical_enforcement_path: "tests/test_inc3_authoring_uplift.py::TestConcise (per-node-type word-budget check on authored nodes)"
tags: [meta, authoring, conciseness, token-budget, quality]
source_attribution: "writ-native"
source_commit: null
edges:
  - { target: PBK-AUTHOR-001, type: GATES }
category: CAT-META-001
---

# Rule: Node bodies justify their token cost

Lean body, keyword-rich trigger. Reference other nodes; do not repeat them. One strong
example beats three. Companion to TEC-META-KEYWORDS-001 (discoverability) under PBK-AUTHOR-001.
