---
type: Documentation Index
title: "Architecture"
description: The core stack for a first reading, then the module topography, the hook layer, the local service, the rule graph, retrieval, and the decision index.
---

# Architecture

The shape of the code: which directory holds what, how a hook reaches the local service, how the service reads the rule graph, how retrieval picks the rules for a prompt, and the decisions behind the design. Start with the core stack if the pieces (Neo4j, Tantivy, ONNX, hnswlib, the gates) are new.

- [The core stack](core-stack.md) - what each piece is for, and how one prompt uses all of them
- [Module topography](topography.md) - which directory holds what, the `writ/` subpackages and their import edges, how a hook reaches the code
- [Hooks](hooks.md) - what Writty does on each Claude Code event, which hooks can block, how to add one
- [Local service](local-service.md) - the daemon every hook calls: startup, route modules, error contract, health
- [Rule graph](rule-graph.md) - node types, where the corpus lives, how a proposed rule becomes canon, decision records
- [Retrieval](retrieval.md) - the ranked pipeline and its abstention exit, the always-on floor, the methodology companion
- [Design decisions](decisions.md) - the ADRs with their status, and decisions recorded in code and docs

The illustrated pages under `docs/architecture/` draw the same ground in more detail.
