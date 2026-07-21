#!/bin/bash
# Standalone static analysis runner.
# Replaces shell-hook analysis and static-analysis agent bash commands.
# Returns structured JSON array of findings.
#
# Usage:
#   bin/run-analysis.sh <file> [file2 ...]
#   bin/run-analysis.sh --project-root /path/to/project <file> [file2 ...]
#
# Output: JSON array of { file, line, severity, rule, tool, message }
# Exit code: 0 = all clean, 1 = errors found, 2 = tool not available

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
source "$SCRIPT_DIR/lib/common.sh"
source "$SCRIPT_DIR/lib/analyzers-lang.sh"
source "$SCRIPT_DIR/lib/analyzers-regex.sh"

# ── Argument parsing ─────────────────────────────────────────────────────────
PROJECT_ROOT=""
FILES=()

while [[ $# -gt 0 ]]; do
  case "$1" in
    --project-root) PROJECT_ROOT="$2"; shift 2 ;;
    *) FILES+=("$1"); shift ;;
  esac
done

if [ ${#FILES[@]} -eq 0 ]; then
  echo '{"error": "No files specified. Usage: run-analysis.sh [--project-root DIR] file1 [file2 ...]"}'
  exit 2
fi

# Auto-detect project root from first file if not specified
if [ -z "$PROJECT_ROOT" ]; then
  PROJECT_ROOT=$(detect_project_root "${FILES[0]}")
fi


# ── Main loop ────────────────────────────────────────────────────────────────
ALL_FINDINGS=""
HAS_ERRORS=0

for file in "${FILES[@]}"; do
  if [ ! -f "$file" ]; then
    ALL_FINDINGS="${ALL_FINDINGS}$(python3 -c '
import json, sys
print(json.dumps({
    "file": sys.argv[1], "line": 0, "severity": "error",
    "rule": "ENF-POST-007", "tool": "filesystem",
    "message": "File does not exist"
}))' "$file" 2>/dev/null)"$'\n'
    HAS_ERRORS=1
    continue
  fi

  lang=$(detect_language "$file")
  case "$lang" in
    php)        result=$(analyze_php "$file") ;;
    xml)        result=$(analyze_xml "$file") ;;
    javascript|typescript) result=$(analyze_js_ts "$file") ;;
    python)     result=$(analyze_python "$file") ;;
    rust)       result=$(analyze_rust "$file") ;;
    go)         result=$(analyze_go "$file") ;;
    graphql)    result=$(analyze_graphql "$file") ;;
    *)          result="" ;;
  esac

  if [ -n "$result" ]; then
    ALL_FINDINGS="${ALL_FINDINGS}${result}"$'\n'
    # Check if any finding has severity=error
    if echo "$result" | grep -q '"severity": "error"'; then
      HAS_ERRORS=1
    fi
  fi

  # Cross-language regex scanners, merged into ONE python3 process that
  # reads the file once (PART 2b). perf-scan and scale-scan emit ONLY
  # "severity": "warning", so a single grep of the merged output for an
  # error severity flips HAS_ERRORS exactly when injection/auth/crypto/data
  # would -- never for perf/scale (verified: both are warning-only).
  scan_result=$(analyze_all_regex_scanners "$file" "$lang")
  if [ -n "$scan_result" ]; then
    ALL_FINDINGS="${ALL_FINDINGS}${scan_result}"$'\n'
    if echo "$scan_result" | grep -q '"severity": "error"'; then
      HAS_ERRORS=1
    fi
  fi
done

# Output as JSON array
echo "$ALL_FINDINGS" | json_array

exit $HAS_ERRORS
