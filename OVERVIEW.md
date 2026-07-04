# Overview of recent changes

This document explains the work on the `feat/update` branch (July 2026, post v1.5.0): four commits that move Writ's enforcement from prompt injection to in-flight rewriting of Claude Code's hook envelopes, plus a retrieval quality improvement and a concurrency fix.

## What changed, in one paragraph

Writ's hooks used to influence the agent the same way everything else does: by adding text to the context and hoping the model complies. The recent work replaces that with mechanical enforcement. Writ now maps what Claude Code actually sends into and out of each hook event (the "black box map"), then uses the rewrite surfaces that map exposes (`updatedInput`, `updatedToolOutput`, exit 2 on Stop) to swap data in flight. The model never sees the original payload and no prompt tokens are spent. Instead of asking the agent to behave, the harness changes the request.

## The black-box map

Claude Code's hook envelopes (the JSON each hook receives on stdin and the reply fields it honors) are only partially documented, and they drift between builds. The methodology:

1. Enable capture (`touch ~/.claude/writ-blackbox.on`), exercise every tool, and record the envelopes each hook event sends and accepts.
2. Pin the Claude Code build the map was captured on in `hooks/hookmap-version` (currently `2.1.199`).
3. A SessionStart canary in `hooks/scripts/session-start-bootstrap.sh` compares the pinned version against the running build and warns the session when they differ, with instructions to re-run the capture.

The current hooks were built against the 2.1.183 map and verified live on 2.1.199. The 2.1.199 capture also surfaced a new field: the Stop envelope now carries `last_assistant_message` for the main agent, which 2.1.183 did not.

## Rewrite surfaces now in use

### Agent hot-swap (`writ-agent-hotswap.sh`, PreToolUse on Task)

When Claude spawns a generic `Explore` or `Plan` subagent, the hook rewrites the spawn via `updatedInput` to `writ-explorer` or `writ-planner`, so Writ's specialized agents run without the user having to ask every time. The same hook stamps the model per the OpusPlan routing policy (opus for planning and review roles, sonnet for execution roles) whenever the caller did not set one explicitly. Zero token cost; the swap happens in the harness, not the prompt.

### Tool-output rewrite (`writ-output-rewrite.sh` + `bin/lib/output-rewrite.py`, PostToolUse on Bash)

Rewrites the Bash result the model sees via `updatedToolOutput`:

- **Secret redaction.** Conservative patterns for AWS access keys, GitHub tokens, Anthropic keys, Slack tokens, JWTs, private-key blocks, and keyed `secret=...` assignments. The original value never reaches the model.
- **Oversize truncation.** Stdout beyond 30,000 characters or 400 lines is reduced to the first 200 and last 100 lines with an elision marker.

Runs in every mode, because redaction is a safety property, not a workflow one.

### Blocking stop gates (Stop and SubagentStop, exit 2)

Stop-hook stderr previously reached the model only as advice. The gates now exit 2, which actually blocks the stop and continues the turn:

- **Pending-test failures** (`writ-run-pending-tests.sh`): a turn whose written files have failing tests cannot end.
- **Gate 5 quality judgments** (`writ-verify-before-claim.sh`): the turn cannot end while any artifact holds a quality score below 3 that is neither fixed nor overridden.
- **Completion-claim check** (`writ-verify-before-claim.sh` for the main agent, `writ-subagent-stop.sh` for `writ-implementer` and `writ-test-writer`): file paths named in the final message are cross-checked against disk via the shared `bin/lib/claim-check.py`. Claiming a file that does not exist blocks the stop.

Every gate is capped at one forced continuation per stop chain via `stop_hook_active`, so a persistent failure cannot loop.

The claim checker was refined after its first live trigger (`2ddbba1`): it tripped on a hypothetical ("the fix would be creating src/foo.py"). Paths now count only inside sentences containing a past-tense claim verb (created, wrote, implemented, and so on); removal verbs are deliberately excluded, since a deleted file is supposed to be missing. Tokens must contain a directory separator, so prose mentions of bare filenames never count.

### Failure telemetry (`writ-bash-failure.sh`, PostToolUseFailure on Bash)

Logs failed Bash commands (truncated command plus error reason) to the friction log. Telemetry only, never blocks. Per the capture, some tool failures never produce a PostToolUseFailure envelope at all, so this is a sample, not a census.

Supporting this, `bin/lib/parse-hook-stdin.py` now passes through `error`, `stop_hook_active`, `tool_response`, `last_assistant_message`, and `cwd` from the envelope.

## Retrieval: relevance floor

The July 2026 hook-token audit showed rank-tail retrieval candidates being injected with scores as low as 0.296. Reciprocal-rank normalization means those tail scores are dominated by the severity/confidence baseline rather than query relevance, and they were filling the context budget.

`apply_relevance_floor` in `writ/retrieval/ranking.py` now drops rules below a score floor, applied in `RetrievalPipeline.query` after the final sort and before authority preference and the context budget. Configured via `min_relevance_score` under `[ranking]` in `writ.toml` (default 0.30; 0.0 disables). The default was tuned on the 165-query ground-truth set against the live corpus: the minimum correct-rule score is 0.311, so 0.30 cuts zero ground-truth hits while removing 15.7% of co-injected tail rules. Tests: `tests/test_relevance_floor.py`.

## Reliability: session-cache write race

`_write_cache` in `bin/lib/writ-session.py` and three hook scripts all used a shared `<path>.tmp` name for atomic writes. Concurrent writers (server threads via `asyncio.to_thread`, hook CLI calls) raced on the rename and threw `FileNotFoundError` in production. Each writer now gets its own temp file via `tempfile.mkstemp` followed by `os.replace`. The regression test (`tests/test_session_cache_concurrency.py`) reproduces the old failure and passes on the fix.

## Related documents

- `CHANGELOG.md` for the released version history (v1.5.0 and earlier).
- `HANDBOOK.md` for the full architecture, including the hooks inventory.
- `README.md` for install, quick start, and the system description.
