<!-- RULE START: RESEARCH-CITE-001 -->
## Rule RESEARCH-CITE-001

**Domain**: research
**Category**: CAT-CODE-RESEARCH-001
**Severity**: High
**Scope**: Task
**Mandatory**: false

### Trigger
When stating an external fact in an investigation finding or synthesis.

### Statement
Every external claim carries a citation: a `ref` recorded in the session citation ledger (the INV-2 `citation_log`), with the supporting excerpt. A claim with no citation you can point to is dropped, not softened. No claim from memory.

### Violation
```
# "It's well known that X." -- no ref, no excerpt, no captured source.
```

### Pass
```
# "X (citation_log ref: https://primary.example/spec#sec-4, excerpt: '...')."
# The claim points at a captured source with the supporting span.
```

### Enforcement
The citation ledger is presence-checked: a finding's `ref` must resolve to a captured citation. Presence proves capture, never truth (the honest ceiling).

### Rationale
A citation makes a claim auditable. Presence of a source is the floor that lets a human adjudicate truth; absence of one means there is nothing to adjudicate.

Related rules: ENF-OPS-001, RESEARCH-CORROBORATE-001, RESEARCH-SOURCE-001.

<!-- RULE END: RESEARCH-CITE-001 -->
---

<!-- RULE START: RESEARCH-CORROBORATE-001 -->
## Rule RESEARCH-CORROBORATE-001

**Domain**: research
**Category**: CAT-CODE-RESEARCH-001
**Severity**: High
**Scope**: Task
**Mandatory**: false

### Trigger
When a factual claim gathered during investigation will drive a decision or an assertion in the synthesis.

### Statement
A decision-driving factual claim is corroborated by two or more INDEPENDENT sources. Sources that derive from a common origin (articles quoting one press release) count as one. A single source is a lead, not a fact.

### Violation
```
# Decision rests on one source.
# Three "sources" all quote the same upstream announcement -> effectively one.
```

### Pass
```
# Decision rests on two independent primary sources that do not share an origin.
# Their agreement raises confidence; their provenance is recorded separately.
```

### Enforcement
Enforced (INV-7a) by the `triangulation-gate` command: it counts INDEPENDENT source domains among the citation-ledger url rows and returns `blocked` until >=2 corroborate (fail-closed when zero sources are captured). The verdict is a hard stop, not a nudge.

### Rationale
Independent corroboration is what separates a fact from an echo. Counting echoes as corroboration manufactures false confidence.

Related rules: RESEARCH-CITE-001, RESEARCH-SOURCE-001.

### Edges
- DEPENDS_ON: RESEARCH-CITE-001

<!-- RULE END: RESEARCH-CORROBORATE-001 -->
---

<!-- RULE START: RESEARCH-SOURCE-001 -->
## Rule RESEARCH-SOURCE-001

**Domain**: research
**Category**: CAT-CODE-RESEARCH-001
**Severity**: High
**Scope**: Task
**Mandatory**: false

### Trigger
When citing a source to support a claim during investigation (research, audit, or exploration).

### Statement
A claim rests on the most authoritative source reachable, not the first hit. Primary sources (the spec, the code, the dataset, the original announcement) outrank secondary descriptions, which outrank tertiary aggregations. If a primary source is one click away, the secondary one is a lead, not a citation.

### Violation
```
# Claim: "The API rate limit is 100 req/min."
# Cited: a 2-year-old blog post summarizing the API.
# The official API reference -- the primary source -- was never opened.
```

### Pass
```
# Claim: "The API rate limit is 100 req/min."
# Cited: the official API reference, rate-limits section, retrieved today.
# The blog post was the lead that pointed there; the primary source is what is recorded.
```

### Enforcement
Review. The citation ledger records each source's `ref`; a reviewer checks that decision-driving claims cite primary/authoritative sources, not aggregators.

### Rationale
Most bad findings are a weak source over-trusted, not a fabrication. Climbing to the primary source removes the layer where summary error and staleness creep in.

Related rules: RESEARCH-CITE-001, RESEARCH-CORROBORATE-001, RESEARCH-STALENESS-001.

<!-- RULE END: RESEARCH-SOURCE-001 -->
---

<!-- RULE START: RESEARCH-STALENESS-001 -->
## Rule RESEARCH-STALENESS-001

**Domain**: research
**Category**: CAT-CODE-RESEARCH-001
**Severity**: Medium
**Scope**: Task
**Mandatory**: false

### Trigger
When citing a source for a time-sensitive or version-dependent claim.

### Statement
Time-sensitive facts record the retrieval date or the version they describe. Fast-moving domains (prices, APIs, releases, security advisories) are stale by default; re-verify before relying on a previously captured source.

### Violation
```
# "The current stable version is 3.2." -- no date, no version pin.
# Captured six months ago; silently treated as current.
```

### Pass
```
# "Stable version is 3.2 (retrieved 2026-06-01)."
# The date travels with the claim; a reader knows when to re-verify.
```

### Enforcement
Enforced (INV-7a) by the `staleness-check` command: each url citation carries an `excerpt_hash`, and a source re-captured with a changed hash is flagged `drifted` (its content moved since the earlier fetch). A reviewer re-verifies a drifted source before relying on it.

### Rationale
A correct-but-stale fact is still wrong when it matters. Dating the claim turns silent staleness into a visible, checkable property.

Related rules: PERF-CACHE-002, RESEARCH-SOURCE-001.

<!-- RULE END: RESEARCH-STALENESS-001 -->
