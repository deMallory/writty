#!/usr/bin/env bash
# INV-5: single-region audit orchestrator.
#
# Wires the audit lens end to end over EXISTING pieces -- it does not modify
# bin/run-analysis.sh, runs no network calls, and performs no destructive ops:
#   1. resolve the region's analyzable files (dirs expand to common code files)
#   2. freeze that file list as the INV-4 coverage denominator (--freeze-scope)
#   3. for each file: run bin/run-analysis.sh and record it examined (record-analysis)
#   4. print the INV-4 coverage map + the INV-5 presence synthesis gate
#
# Usage: bin/audit-region.sh [--session SID] <file-or-dir> [more...]
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SESSION_HELPER="$SCRIPT_DIR/lib/writ-session.py"
RUN_ANALYSIS="$SCRIPT_DIR/run-analysis.sh"

SID=""
TARGETS=()
while [[ $# -gt 0 ]]; do
  case "$1" in
    --session) SID="$2"; shift 2 ;;
    *) TARGETS+=("$1"); shift ;;
  esac
done

if [ -z "$SID" ] && [ -f /tmp/writ-current-session ]; then
  SID=$(tr -d '[:space:]' < /tmp/writ-current-session 2>/dev/null || true)
fi
if [ -z "$SID" ] || [ ${#TARGETS[@]} -eq 0 ]; then
  echo '{"error":"usage: audit-region.sh [--session SID] <file-or-dir> ..."}'
  exit 2
fi

# 1. Resolve the region's file list (expand directories to common code files).
FILES=()
for t in "${TARGETS[@]}"; do
  if [ -d "$t" ]; then
    while IFS= read -r f; do
      [ -n "$f" ] && FILES+=("$f")
    done < <(find "$t" -type f \( -name '*.py' -o -name '*.php' -o -name '*.js' \
              -o -name '*.ts' -o -name '*.go' -o -name '*.rs' \) 2>/dev/null)
  elif [ -f "$t" ]; then
    FILES+=("$t")
  fi
done
if [ ${#FILES[@]} -eq 0 ]; then
  echo '{"error":"no analyzable files in region"}'
  exit 2
fi

# 2. Freeze the region as the coverage denominator.
SCOPE_JSON=$(printf '%s\n' "${FILES[@]}" | python3 -c \
  "import sys, json; print(json.dumps({'files':[l.strip() for l in sys.stdin if l.strip()],'source':'audit-region'}))")
python3 "$SESSION_HELPER" update "$SID" --freeze-scope "$SCOPE_JSON" >/dev/null 2>&1 || true

# 3. Analyze each file and record it as examined (findings detail -> citation_log).
for f in "${FILES[@]}"; do
  "$RUN_ANALYSIS" "$f" 2>/dev/null \
    | python3 "$SESSION_HELPER" record-analysis "$SID" "$f" >/dev/null 2>&1 || true
done

# 4. Report coverage + the presence synthesis gate.
echo "=== coverage-map ==="
python3 "$SESSION_HELPER" coverage-map "$SID"
echo "=== synthesis-gate ==="
python3 "$SESSION_HELPER" synthesis-gate "$SID"