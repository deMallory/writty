---
technique_id: TEC-PROC-WORKTREE-001
node_type: Technique
domain: process
severity: medium
scope: task
trigger: "When starting feature work that should not interfere with the main workspace; when the user requests a worktree; when executing a plan that requires isolation from in-progress work."
statement: "Create isolated git worktrees with smart directory selection and mandatory gitignore-safety verification. Priority: existing worktrees dir → CLAUDE.md preference → ask user. Always verify the worktree directory is gitignored for project-local worktrees."
rationale: "Project-local worktrees that are not gitignored pollute the main branch's working tree and lead to accidental commits. A mandatory safety check prevents the single most common worktree footgun."
tags: [feature-branch, git, gitignore, isolation, process, worktree]
confidence: battle-tested
authority: human
last_validated: 2026-04-21
staleness_window: 365
evidence: peer-reviewed
source_attribution: "writ-native"
source_commit: null
edges:
  - { target: ENF-PROC-WORKTREE-001, type: TEACHES }
  - { target: PBK-PROC-SDD-001, type: PRECEDES }
  - { target: SKL-PROC-EXEC-001, type: PRECEDES }
category: CAT-PROC-001
action_triggers: ["worktree"]
trigger_keywords: ["worktree", "isolation", "gitignore", "git"]
---

# Technique: Create a safe worktree

## Step 0: detect existing isolation (first)

Are you ALREADY in a linked worktree? Compare `git rev-parse --git-dir` with `--git-common-dir`;
if they differ you are likely isolated -- unless `git rev-parse --show-superproject-working-tree`
returns a path (a submodule: treat as a normal repo). If already in a worktree, do NOT nest
another; skip to setup.

## Prefer native tools over `git worktree add`

If a native worktree tool exists (`EnterWorktree`, a `/worktree` command, a `--worktree` flag),
use it and skip to setup -- it keeps placement, branch, and cleanup in sync with the harness.
Raw `git worktree add` behind a native tool leaves phantom state; use it only as the fallback.

## Directory selection priority

1. If `.worktrees/` or `worktrees/` directory exists in the project root, use it.
2. Else if the project's `CLAUDE.md` specifies a worktree location preference, use it.
3. Else ask the user where to put the worktree. Do not assume.

## Safety verification (mandatory for project-local)

If the worktree directory lives inside the repo tree:
- Check that the directory path is listed in `.gitignore` or matches an ignored pattern.
- If not ignored: stop. Either add the path to `.gitignore` first (ask user), or pick a different directory.
- Project-local worktrees that are not gitignored pollute the main branch's working tree and lead to accidental commits.

## Setup after worktree creation

- Auto-detect and run project setup: `package.json` → `npm install`; `Cargo.toml` → `cargo build`; `pyproject.toml` or `requirements.txt` → `pip install`.
- Run the project's baseline test command. Report output. Do not proceed on red baseline — ask user.

## Red flags

- "Directory location doesn't matter, any place is fine." — violation of priority order.
- "Skip the gitignore check, I'm sure it's fine." — canonical pre-incident thought.
- "Skip baseline tests, we'll fix them later." — defeats the purpose of isolation.
