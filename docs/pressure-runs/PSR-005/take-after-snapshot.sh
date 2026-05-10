#!/usr/bin/env bash
# Run AFTER PSR-005 completes. Captures friction-log delta + post-run state.
#
# Usage:
#   bash ~/.claude/skills/writ/docs/pressure-runs/PSR-005/take-after-snapshot.sh

set -euo pipefail

WRIT_DIR="${HOME}/.claude/skills/writ"
PSR_DIR="${WRIT_DIR}/docs/pressure-runs/PSR-005"
LOG="${WRIT_DIR}/workflow-friction.log"
BASELINE=6987

if [ ! -f "$LOG" ]; then
    echo "ERROR: friction log not at $LOG"
    exit 1
fi

AFTER=$(wc -l < "$LOG" | tr -d ' ')
DELTA=$((AFTER - BASELINE))

if [ "$DELTA" -lt 0 ]; then
    # Log was rotated during the run. Concatenate .1 + current.
    ROTATED="${LOG}.1"
    if [ -f "$ROTATED" ]; then
        ROT_LINES=$(wc -l < "$ROTATED" | tr -d ' ')
        echo "NOTE: log rotated mid-run. .1 has ${ROT_LINES} lines, current has ${AFTER}."
        # Best-effort delta: tail of rotated + all of current
        if [ "$ROT_LINES" -gt "$BASELINE" ]; then
            sed -n "$((BASELINE+1)),${ROT_LINES}p" "$ROTATED" > "${PSR_DIR}/friction.jsonl"
            cat "$LOG" >> "${PSR_DIR}/friction.jsonl"
        else
            cp "$LOG" "${PSR_DIR}/friction.jsonl"
        fi
        DELTA=$(wc -l < "${PSR_DIR}/friction.jsonl" | tr -d ' ')
    else
        echo "ERROR: log shrunk but no .1 backup; cannot reconstruct delta."
        exit 2
    fi
else
    sed -n "$((BASELINE+1)),${AFTER}p" "$LOG" > "${PSR_DIR}/friction.jsonl"
fi

cat > "${PSR_DIR}/post-run-state.md" <<EOF
# PSR-005 post-run state

Captured by take-after-snapshot.sh.

## Friction log delta

- Baseline: ${BASELINE} lines (see baseline.md)
- Post-run: ${AFTER} lines
- Delta: ${DELTA} new events
- Captured to: friction.jsonl in this directory

## Phase 5 commit gate

Awaiting transcript paste + grade in analysis.md before commit.
EOF

# Quick event-type breakdown for the orchestrator's grading.
echo
echo "Snapshot saved to ${PSR_DIR}"
echo "Delta: ${DELTA} events"
echo
echo "Event-type counts in delta:"
python3 -c "
import json, sys, collections
counts = collections.Counter()
with open('${PSR_DIR}/friction.jsonl') as f:
    for line in f:
        line = line.strip()
        if not line:
            continue
        try:
            counts[json.loads(line).get('event','?')] += 1
        except json.JSONDecodeError:
            pass
for evt, n in counts.most_common():
    print(f'  {evt:35s} {n}')
"
