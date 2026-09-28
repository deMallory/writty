---
type: Guide
title: "Upstream sync"
description: How this fork tracks infinri/Writ, how to measure the gap, what a merge must keep, the steps of a sync, and the sync history.
---

# Upstream sync

Writty is a fork of Writ. `origin` is deMallory/writty, the repo the plugin installs from; `upstream` is infinri/Writ. The fork takes upstream by merging `upstream/main` on a branch, keeping the fork-only surface below, and re-aligning the pins. How far behind the fork is today: [Project log](project-log.md).

## Measure the gap

```
git fetch upstream
git merge-base main upstream/main          # the last upstream commit the fork has
git rev-list --count main..upstream/main   # upstream commits not merged yet
git log --oneline main..upstream/main      # what they are
```

A fresh clone has no `upstream` remote: `git remote add upstream git@github.com:infinri/Writ.git`.

## What a merge must keep

Hooks only this fork has, each registered in `hooks/hooks.json`. None exists on `upstream/main` (checked 2026-09-28).

| Fork hook | Event | What it does |
|---|---|---|
| `writ-agent-hotswap.sh` | PreToolUse | Rewrites a generic sub-agent dispatch to the matching Writty role and stamps its model |
| `writ-sdd-review-order.sh` | PreToolUse | Refuses a code-quality review before the spec review of the same task |
| `writ-output-rewrite.sh` | PostToolUse | Redacts secrets and truncates oversized Bash output before the model sees it |
| `writ-bash-failure.sh` | PostToolUseFailure | Logs failed Bash commands to the friction log |
| `writ-read-credential-gate.sh` | PreToolUse | Refuses reads of secret files, whose content would leave the machine |

`tests/test_fork_hooks_ported.py` pins the first four; `tests/test_read_credential_gate.py` pins the last.

Also fork-only:

- **Plugin identity.** The marketplace entry in `.claude-plugin/marketplace.json` is named writty and points at deMallory/writty. On a conflict, keep ours, or every install would pull upstream.
- **Corpus.** The editorial (`-EDIT-`) and animation (`-ANIM-`) rule namespaces and the category `CAT-COMM-EDIT-001` live in `writ-corpus.cypher`. Take upstream's new nodes and keep these. `tests/test_node_routes_wiring.py` exempts the two namespaces from its semantic-route pin (`FORK_SEMANTIC_NAMESPACES`).
- **Plugin agent names.** PR 12 made four hooks expect the plugin's `writ:writ-*` agent names. Upstream has the same defect in `writ-dispatch-discipline.sh`, so expect a conflict in those hooks once upstream fixes it.
- **Commit messages** are in French, `type(domaine): sujet`. A convention, not code.

## Steps of a sync

The 1.7.0 sync ran on branch `sync/upstream-1.7.0` (PR 8); the 1.7.2 sync is the merge `b0ca5d1`. Both followed these steps.

1. Branch off `main` as `sync/upstream-<version>`, then `git merge upstream/main`.
2. Resolve conflicts, keeping the surface above.
3. Re-align the pins that name a version or a count. `EXPECTED_VERSION` in `tests/test_version_consistency.py` must match `pyproject.toml`, `.claude-plugin/plugin.json` and the marketplace entry. `tests/test_phase51_doc_counts.py` counts the hooks in `hooks/hooks.json`.
4. Run the full suite with `make test`. It needs Docker, for the test Neo4j on 7688.
5. Add a `CHANGELOG.md` entry that names the upstream commit merged, and bump the version.
6. Open the PR and merge it. Then, on every machine: `claude plugin marketplace update writty`, `claude plugin update writty@writty`, restart Claude Code, restart the daemon ([Service lifecycle](service-lifecycle.md)).

## History

| Date | Upstream point | Fork side | Notes |
|---|---|---|---|
| 2026-09-14 | `e608659`, upstream's merge of 2026-08-14 | `b0ca5d1`, released as 1.7.2 | Upstream's approval-token binding and one session store per user. `CHANGELOG.md` names `bf339bc`, which `e608659` contains |
| 2026-08-11 | the 1.7.0 line, 94 commits (`cee1641`) | PR 8, `bf7f385` | `bible/` untracked the same day (PR 9) |
| 2026-08-01 | upstream's recreated history, no common ancestor | `main` rebuilt on it | Old main kept as tag `backup/pre-upstream-sync-2026-08-01`; fork hooks, corpus and tests restored on top |
