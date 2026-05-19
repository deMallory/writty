#!/bin/bash
# Exit codes: 0=pass, 1=warning (advisory -- deliberate, not blocking)
#
# Universal validation hook -- routes by file extension.
# PostToolUse: fires after every Write/Edit/MultiEdit.
# Exit non-zero = Claude Code injects error into context. Must fix before continuing.
# Output: structured JSON per finding.
#
# Delegates to bin/run-analysis.sh for the actual analysis.
# This hook extracts the file path from tool input and calls the shared script.

SKILL_DIR="$(cd "$(dirname "$0")/../.." && pwd)"
source "$SKILL_DIR/bin/lib/common.sh"

# Parse the Claude Code hook stdin envelope (consumes stdin once)
PARSED=$(parse_hook_stdin)
FILE=$(parsed_field "$PARSED" "file_path")

if [ -z "$FILE" ]; then exit 0; fi

# Skip validation if the write itself failed (tool_result_is_error = true).
# No point validating old file content when the write didn't land.
if parsed_bool "$PARSED" "is_error"; then exit 0; fi

if [ ! -f "$FILE" ]; then exit 0; fi

# Check if the file type is one we analyze
lang=$(detect_language "$FILE")
if [ "$lang" = "unknown" ]; then exit 0; fi

PROJECT_ROOT=$(detect_project_root "$FILE")

# Run analysis via the shared script
OUTPUT=$("$SKILL_DIR/bin/run-analysis.sh" --project-root "$PROJECT_ROOT" "$FILE" 2>&1)
EXIT_CODE=$?

# Track file write for coverage analysis
SESSION_ID=$(detect_session_id "$PARSED")
ANALYSIS_RESULT="pass"
if [ $EXIT_CODE -ne 0 ]; then
    ANALYSIS_RESULT="fail"
fi
python3 "$SKILL_DIR/bin/lib/writ-session.py" update "$SESSION_ID" \
    --add-file "$FILE" \
    --add-file-result "$FILE" "$ANALYSIS_RESULT" 2>/dev/null || true

if [ $EXIT_CODE -ne 0 ]; then
  # Full linter output -> per-session log; terse summary -> stderr.
  # emit-summary.py reads the log, surfaces the first error, references the
  # log path. Claude reads the full log only if the first error is ambiguous.
  SAFE_NAME=$(echo "$FILE" | tr '/' '_')
  LOG_DIR="$SKILL_DIR/cache/$SESSION_ID"
  mkdir -p "$LOG_DIR"
  LOG_FILE="$LOG_DIR/${SAFE_NAME}.lint.json"
  echo "$OUTPUT" > "$LOG_FILE"
  python3 "$SKILL_DIR/bin/lib/emit-summary.py" \
    --format json \
    --log "$LOG_FILE" \
    --rule "ENF-POST-007" \
    --label "static-analysis errors in $FILE"
  exit 1
fi

exit 0
