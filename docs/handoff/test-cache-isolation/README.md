# Handoff: stop the test suite writing into the real session store

Written 2026-10-03, at the end of the session that investigated the 1 Oct wipe of
`~/.cache/writ`. Updated the same day with the outcome of the fix. Claims were checked on
that date. "Not verified" marks the rest.

Resume prompt: `read docs/handoff/test-cache-isolation/README.md, do the follow-up`.

## Resume point

| What | State | Next |
|---|---|---|
| Branch `fix/test-cache-isolation` | Both leaks fixed, from `main` `7ec75ce` | Push and open the PR, owner's call |
| Leak 1, the cache folder | Fixed in `tests/_log_isolation.py` | Nothing |
| Leak 2, the daemon socket | Fixed in the same plugin, tests only | "Follow-up" below |
| The 1 Oct wipe | Cause unknown, investigation closed by the owner | Nothing, see "Open leads" |
| Real session folder | 524 of 4,657 files are test leftovers | Step 5, owner's call |

## Leak 1: the cache folder

`tests/conftest.py:52` on `main` sets the session cache folder with `setdefault`:

```python
_os.environ.setdefault("WRIT_CACHE_DIR", _tempfile.mkdtemp(prefix="writ-test-cache-"))
```

`setdefault` keeps a value that is already set. Under Claude Code, the dotfiles settings pin
`WRIT_CACHE_DIR` to `~/.cache/writ/session`. So every suite run from a Claude session uses the
real session store: in-process tests, subprocess tests that copy `os.environ`, and the test
daemon (`tests/_daemon.py::start_test_daemon` passes `expected_cache_dir()`, which reads the
same variable). The comment above the line says "Force"; the code does not force.

Evidence, 2026-10-03:

1. A sandboxed run with `WRIT_CACHE_DIR` set to a scratch folder wrote
   `writ-events-non-work-test.buf`, `writ-events-qj-test.buf` and `writ-events-wt-test.buf`
   into that folder.
2. The real `~/.cache/writ/session` held 516 files with `test` in the name, for example
   `writ-events-phase3b-test.buf` and `writ-events-test-6pre-094ee715.buf`.

`WRIT_LOG_ROOT` had the same bug and was already fixed. `tests/_log_isolation.py` assigns it,
and `pyproject.toml` loads that module through `addopts = "... -p tests._log_isolation"`, so
it also covers `--noconftest` runs. Nothing in CI, the Makefile or the scripts sets
`WRIT_CACHE_DIR` or `WRIT_SOCKET` for tests, so an assignment breaks no caller.

## Leak 2: the daemon socket

Found by the first full run with leak 1 fixed. That run still left 27 files in the real
folder: 18 `writ-session-test-pol5a-*` from `tests/test_pol5a_statusline.py` and 9
`test-dispatch-*` from `tests/test_pre_write_dispatch_parsing.py`.

Their hooks call `bin/lib/writ_daemon_client.py::post_json`. With `WRIT_SOCKET` unset, it uses
`DEFAULT_SOCKET`, which is `~/.cache/writ/run/writ.sock`: the operator's live daemon.
`_request` tries that socket before TCP whenever the file is a socket. The live daemon serves
the call and writes the session into its own cache folder, the real one. The suite's
`WRIT_PORT=8799` and `WRIT_SESSION_BASE` do not stop it. The bash client does:
`bin/lib/common.sh` skips the default socket when `WRIT_PORT` or `WRIT_HOST` is set. Claude
Code does not export `WRIT_SOCKET`.

## The fix

Done on `fix/test-cache-isolation`, six files.

1. **Red tests**, `tests/test_cache_isolation_plugin.py`. Two child pytest runs (plain and
   `--noconftest`) start with `WRIT_CACHE_DIR` set to a sentinel folder and must leave it
   empty. A third binds a real socket at `~/.cache/writ/run/writ.sock` under a throwaway
   `HOME` and counts the hook client's connections. Before the fix they failed on two equal
   paths, then on `assert 1 == 0`.
2. **Assign in `tests/_log_isolation.py`**: `WRIT_CACHE_DIR` and `WRIT_SOCKET`, next to
   `WRIT_LOG_ROOT`. The socket path sits in a fresh `mkdtemp` folder that no operator daemon
   holds, so the client falls back to TCP on the test port. A daemon a test starts with the
   inherited env binds that path.
3. **Remove the `setdefault` line in `tests/conftest.py`.** Addopts plugins load before
   conftest, so it was a no-op after step 2. Rejected: changing only that line to an
   assignment, which leaves `--noconftest` runs writing into the real store.
4. **Verify.** Full suite with the Claude Code pin in force, alone on the machine: 12713
   passed, 872 skipped, 1 failed, 3 errors, 19 minutes. The failure was
   `tests/test_state_root.py::TestBashAgreesWithPython::test_same_answer_when_home_is_unset`,
   which checks the default socket path and now inherited the plugin's `WRIT_SOCKET`; it
   clears that variable too, and the module passes. The 3 errors were teardown leak guards
   tripped by files and processes this change does not create: a daemon on port 65149
   started from the main checkout's `.venv`, and gate-token sentinel files whose origin was
   not traced. The three modules pass alone. Leftovers:
   `find ~/.cache/writ/session -newer <marker> -name '*test*'` printed nothing.
5. **Cleanup (owner's call, not part of the PR).** Delete the test leftovers in
   `~/.cache/writ/session`. Look at the list first: `ls ~/.cache/writ/session | grep test`.

## Follow-up: guard the Python hook client

`bin/lib/writ_daemon_client.py` should skip `DEFAULT_SOCKET` when `WRIT_PORT` or `WRIT_HOST`
is set and `WRIT_SOCKET` is not, as `bin/lib/common.sh` does. The PR fixed the tests only and
left that shared hook module alone. Any other caller that names a TCP endpoint still reaches
the live daemon through the socket. Not verified: whether such a caller exists outside tests.

## No 30-day delete exists

Checked 2026-10-03 in the repo, every installed plugin copy (Claude and Grok) and the launchd
agents. These are the only age-based deletes; none removes the cache folder itself.

| What | Age | Where |
|---|---|---|
| Old compressed log archives | 365 days (audit, friction, errors), 90 (metrics), 14 (debug) | `writ/session/log_rotation.py::RETENTION_DAYS` |
| Scratch files in `/tmp` | 7 days | `writ/session/log_rotation.py::SCRATCH_MAX_AGE_DAYS` |
| `FeedbackBatch` records in Neo4j (graph data, not files) | 30 days | `writ/graph/db/rule_store.py::FEEDBACK_BATCH_TTL_DAYS` |
| Abandoned event buffers | read into the logs, never deleted | `bin/lib/writ-flush-events.py::_sweep_abandoned` |

The 30-day matches in `writ/dashboard.py` only choose which events the dashboard shows.

## Open leads on the 1 Oct wipe

Not part of this fix. Recorded so nobody repeats the work.

1. **Window.** 2026-10-01, 10:02:23 to 10:03:12 CEST. Only `~/.cache/writ` was removed; it
   came back at 10:03:13. The only activity was a background full-suite run (pid 52249) in
   the `dashboard-pair-ledger` worktree, near `test_phase0_migration_is_not_destructive`.
2. **Ruled out.** Grok commands (read-only, turn ended 10:02:24), Claude transcripts,
   home-manager, a reboot, every recursive delete in the repo, the 1.7.5 plugin and the Grok
   plugin hooks.
3. **Did not reproduce.** The 20 test files from the window, at `8043a12`, sandboxed: 100
   passed, 4 failed (`test_phase18c`, missing venv in the clone), 52 skipped (51 need the
   untracked `bible/`, 1 needs a daemon). The sandbox root survived.
4. **Untested.** The full suite in a sandbox (about 21 minutes), and the import-cypher
   corpus-restore loop seen on 7688 at 08:03:38 to 08:05Z, which the 10:09 run did not hit.
5. **Lost data.** Logs from 13 to 29 Sep. They may be on the Time Machine disk, which failed
   to mount on 2026-10-03.

Related: the Grok hooks default the session folder to `$HOME/.cache/writ/session` because
`WRIT_CACHE_DIR` is unset in Grok. Harmless today, worth knowing.
