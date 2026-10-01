---
type: Documentation Index
title: "Writty wiki"
description: Root index of the Writty documentation, with the reading order for a developer meeting the tool for the first time.
---

# Writty wiki

Writty is a Claude Code plugin that puts guardrails around the AI while it codes. It blocks source writes until a human approves a plan and then its tests. It hands the AI the engineering rules that fit the task in front of it. It records which plan and which rules led to each commit. Everything runs on your machine: hook scripts, a local service on port 8765, and a Neo4j graph in Docker.

Writty is a fork of [Writ](https://github.com/infinri/Writ) by Lucio Saldivar.

## Start here

1. First contact: [Quickstart](quickstart.md). What Writty does and does not do, install, a first gated task.
2. The stack, for a first reading: [The core stack](architecture/core-stack.md). Claude Code, the gates, the librarian, and why Neo4j, Tantivy, ONNX and hnswlib are all in the box.
3. Daily use: `HANDBOOK.md` at the repo root is the operator manual.
4. Exact contracts (hooks, HTTP API, graph schema, gates): `docs/reference/`.
5. Editing this wiki: `INSTRUCTIONS.md` in this folder holds the format rules and the checks.

## Files

- [Quickstart](quickstart.md) - what it is, install, first gated task, approval words, when something blocks

## Directories

- [workflows](workflows/) - the five modes, the gated Work workflow, approvals, helper workflows
- [architecture](architecture/) - topography, hooks, the local service, the rule graph, retrieval, decisions
- [testing](testing/) - the suite, graph isolation, perf gates and benchmarks
- [integrations](integrations/) - Claude Code plugin, Neo4j, the embedding model, upstream Writ, PyPI
- [operations](operations/) - environment, wiki refresh, project log, upstream sync

## Related files outside the wiki

- `README.md`: the pitch, install, what is measured and what is not.
- `HANDBOOK.md`: the operator manual.
- `docs/reference/`: precise contracts, one file per subsystem.
- `docs/adr/`: architecture decision records.
- `docs/architecture/`: the architecture as interactive HTML pages.
