---
type: Guide
title: "Wiki maintenance instructions"
description: How this openwiki folder is structured, the OKF rules it follows, how it splits the work with docs/, and how to check it.
---

# Wiki maintenance instructions

This folder is the map of Writty, for a developer and for an AI session. It follows OKF v0.1 (the OpenWiki format), the format the `openwiki` CLI reads and writes. Keeping to it lets the CLI update pages in place instead of rewriting them.

## Format rules

1. Every page starts with front matter on line 1. No blank line before the first key.

```
---
type: Guide
title: "Page title"
description: One sentence saying what the page covers.
---
```

2. Only three keys are read: `type`, `title`, `description`. Values in use: `Guide`, `Documentation Index`. Keep a colon followed by a space out of unquoted values, so a real YAML parser reads them too.
3. `index.md` files are tables of contents. They link pages as `[Title](file.md)` and directories as `[name](dir/)`. Only those links count.
4. The walk is two levels deep: the root `index.md`, one `index.md` per section directory, then pages. Do not nest deeper.
5. `index.md` and `INSTRUCTIONS.md` are reserved names at any level. They are never content.
6. Sections, in reading order: `quickstart`, `workflows`, `architecture`, `testing`, `integrations`, `operations`. Every new page goes inside one of the five section directories and is linked from that section's `index.md`.

## Wiki versus docs/

| Where | Holds | Rule |
|---|---|---|
| `openwiki/` | The map: what exists, how the parts connect, how to do a task | Summarize and link out. Never restate a contract |
| `docs/reference/` | Precise contracts: hooks, HTTP API, graph schema, gates, configuration | The wiki points here for exact behavior |
| `docs/adr/` | Architecture decisions | The wiki indexes them, never rewrites them |
| `HANDBOOK.md` | The operator manual | The wiki links sections, never copies them |
| `README.md` | The pitch and the install | Points at this wiki |

Where the wiki and the code disagree, the code wins. Fix the page.

## Writing rules

- English. Lead with the answer. Short sentences. Tables for inventories.
- Standard punctuation only: no em dashes, no double hyphen as a dash.
- Every backtick path with a slash and a known extension, such as `writ/session/mode_engine.py`, must exist on disk, or the check fails. Paths outside this repo go without backticks.
- No counts that drift (hooks, rules, tests) unless a check pins them. A table row shaped `| path | N |` is checked against the file's line count.
- Diagrams are fenced mermaid blocks, which GitHub renders. Use `flowchart LR` for structure, `sequenceDiagram` for runtime flows, `stateDiagram-v2` for state machines. Never draw an edge you have not seen in an import or a call.

## Verification

`tests/openwiki/test_structure.py` walks this folder the way an OKF reader does, then checks the root index, dangling index links, orphan pages, front matter, backtick paths, mermaid fences, Lines columns, and the pointer in `README.md`. It reads files only, so it runs without Neo4j:

```
python -m pytest --noconftest tests/openwiki -q
```

`--noconftest` skips `tests/conftest.py`, which refuses to start without the isolated Neo4j instance. `make test` runs `pytest tests/`, so the checks also run with the full suite.
