---
technique_id: TEC-META-KEYWORDS-001
node_type: Technique
domain: meta-authoring
severity: medium
scope: task
trigger: "When authoring or revising a methodology node, before committing it, to make the node discoverable by the agent that will later need it."
statement: "Seed the trigger and body with the exact terms an agent would search for: error-message strings, symptoms, synonyms, and tool/command/file-type names. Stage-2 retrieval is BM25 + vector embedding; a node missing the searcher's words is unreachable no matter how good its content."
rationale: "Writ is a retrieval system. A node that is never retrieved never changes behavior. Discoverability is a property of the words in the node, not its quality."
tags: [meta, authoring, keywords, retrieval, discoverability, bm25, technique]
confidence: peer-reviewed
authority: human
last_validated: 2026-06-02
staleness_window: 365
evidence: peer-reviewed
source_attribution: "writ-native"
source_commit: null
edges: []
category: CAT-META-001
trigger_keywords: ["keyword", "retrieval", "discoverable", "BM25"]
---

# Technique: Keyword coverage for retrieval

Cover the four search categories so BM25 and vector retrieval can find the node:

- **Error strings**: the literal message text an agent would paste (`"Hook timed out"`, `ENOTEMPTY`).
- **Symptoms**: how the problem is described in the moment (`flaky`, `hangs`, `pollution`, `stale`).
- **Synonyms**: alternates for the same idea (`timeout`/`hang`/`freeze`, `cleanup`/`teardown`).
- **Tools and types**: real command, library, and file-type names the task involves.

Put these in the `trigger` (the highest-weighted retrieval surface) and naturally in the body.
Describe the problem, not one language's symptom, unless the node is technology-specific.
