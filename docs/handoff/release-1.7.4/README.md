# After merging PR 26: get 1.7.4 onto this machine

Written 2026-09-29. PR 25 released 1.7.4 but merged before its last two commits; PR 26 carries
them (the `writ.__version__` fix and this checklist). Merging changes nothing on a machine
until its plugin is updated: hooks load from the plugin cache, one folder per version. Do the
steps in order.

Other sessions can keep running through all of it. A running session keeps the hooks it
loaded at start, and the update leaves the 1.7.3 folder on disk (1.7.2's folder was still
there after the last update).

## 1. Merge and update the plugin

- [ ] Merge PR 26: https://github.com/deMallory/writty/pull/26
- [ ] `claude plugin marketplace update writty`
- [ ] `claude plugin update writty@writty`
- [ ] `ls ~/.claude/plugins/cache/writty/writty/` lists `1.7.4` (today: 1.7.0, 1.7.2, 1.7.3)

The marketplace pulls from GitHub, not from this checkout, so no `git pull` is needed first.

## 2. Bootstrap and open a new session

- [ ] While any other session sits idle between prompts: `bash ~/.claude/plugins/cache/writty/writty/1.7.4/scripts/bootstrap-plugin.sh`. It reinstalls the Python package in the environment every session shares (`~/.cache/writ/.venv`), so a hook running mid-install could fail.
- [ ] `curl -s localhost:8765/health` shows `"status":"healthy"` and `"rule_count":336`
- [ ] Open a new session in this repo, in another tab. Nothing else needs a restart.

No daemon restart. On this machine the daemon runs from this repo's own `.venv`
(`writty/.venv/bin/writ serve --port 8765`), whose `writ` package is this checkout, not the
plugin cache. The plugin update does not change its code. On another machine, check what
serves port 8765 first ([Service lifecycle](../../../openwiki/operations/service-lifecycle.md)).

## 3. Live check: the reviewer order (the PR 22 fix)

Before 1.7.4, Work mode refused the code-quality reviewer forever.

- [ ] Set Work mode. With no mode set, the prompt hook prints the exact command with your session id.
- [ ] Ask Claude to dispatch `writ:writ-code-quality-reviewer` on the last commit. **Expect a refusal** naming `ENF-PROC-SDD-001`. This proves the gate is loaded; without it, the last step passes for the wrong reason.
- [ ] Ask Claude to dispatch `writ:writ-spec-reviewer` on the same commit. Wait until it stops.
- [ ] Ask again for `writ:writ-code-quality-reviewer`. **Pass: it runs.**

If the last step is refused, first suspect: the open thread on `task_id` in
`openwiki/operations/project-log.md`. The gate looks under the dispatch's `task_id` when one is
sent, but the spec review is recorded under the phase.

## 4. Clean up

- [ ] Ask Claude to switch to an updated `main` and delete `chore/release-1.7.4` and `fix/release-1.7.4-leftovers`, local and remote.

## Not part of this release, still on the list

- The workshop machine needs steps 1 and 2 before the workshop (around 2026-10-09).
- Task D: commit the workshop vault in raggidy, `Library/DevDocs/writty/`. Claude asks before pushing.
- `make test-graph-down` stops the test graph (port 7688) once you are done with tests.
- The `~/dotfiles` project-scope install is pinned at 1.7.0 (open thread in the project log).
