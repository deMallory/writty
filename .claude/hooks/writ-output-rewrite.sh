#!/usr/bin/env bash
# PostToolUse(Bash) hook -- rewrites the tool result the model sees via
# hookSpecificOutput.updatedToolOutput (2.1.183 force-swap family):
# secret redaction plus oversize-output truncation. Zero token cost; the
# swap happens in the harness, not the prompt. Runs in every mode because
# redaction is a safety property, not a workflow one.
#
# Hook type: PostToolUse (matcher: Bash). Exit: always 0 (never blocks).

HOOK_DIR="$(cd "$(dirname "$0")" && pwd)"
WRIT_DIR="$(cd "$HOOK_DIR/../.." && pwd)"

python3 "$WRIT_DIR/bin/lib/output-rewrite.py" 2>/dev/null || true
exit 0
