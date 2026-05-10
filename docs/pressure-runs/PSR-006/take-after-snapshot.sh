#!/usr/bin/env bash
# PSR-006 post-run snapshot. Captures friction-log delta, hook
# state, daemon health. Idempotent: re-running overwrites the
# captured artifacts.
#
# Usage:
#   bash docs/pressure-runs/PSR-006/take-after-snapshot.sh

set -euo pipefail

WRIT_ROOT="~/.claude/skills/writ"
PSR_DIR="$WRIT_ROOT/docs/pressure-runs/PSR-006"
MASTER_LOG="$WRIT_ROOT/workflow-friction.log"
TEST_LOG="~/workspaces/MageContextABTest/workflow-friction.log"

# Test project (where the manual test ran). Load-bearing for grading.
TEST_BASELINE=297
TEST_AFTER=$(wc -l < "$TEST_LOG" 2>/dev/null || echo "$TEST_BASELINE")
TEST_DELTA=$((TEST_AFTER - TEST_BASELINE))
if [ "$TEST_DELTA" -gt 0 ]; then
    sed -n "$((TEST_BASELINE + 1)),${TEST_AFTER}p" "$TEST_LOG" > "$PSR_DIR/test-project-friction.jsonl"
else
    : > "$PSR_DIR/test-project-friction.jsonl"
fi

# Master log (orchestrator-side, mostly noise).
MASTER_BASELINE=7554
MASTER_AFTER=$(wc -l < "$MASTER_LOG")
MASTER_DELTA=$((MASTER_AFTER - MASTER_BASELINE))
if [ "$MASTER_DELTA" -gt 0 ]; then
    sed -n "$((MASTER_BASELINE + 1)),${MASTER_AFTER}p" "$MASTER_LOG" > "$PSR_DIR/master-friction.jsonl"
else
    : > "$PSR_DIR/master-friction.jsonl"
fi

# Backwards-compat alias for old ref to friction.jsonl.
cp "$PSR_DIR/test-project-friction.jsonl" "$PSR_DIR/friction.jsonl"

# Use test-project values for the rest of this script.
BASELINE=$TEST_BASELINE
AFTER=$TEST_AFTER
DELTA=$TEST_DELTA

# Daemon health re-check.
HEALTH=$(curl -sf -o /dev/null -w "%{http_code}" http://localhost:8765/health || echo "000")
DASHBOARD=$(curl -sf -o /dev/null -w "%{http_code}" http://localhost:8765/dashboard || echo "000")

# Event-type breakdown of the delta.
EVENT_BREAKDOWN=$(python3 -c "
import json, sys
from collections import Counter
counts = Counter()
try:
    for line in open('$PSR_DIR/friction.jsonl'):
        line = line.strip()
        if not line: continue
        try:
            counts[json.loads(line).get('event','?')] += 1
        except Exception:
            counts['_malformed'] += 1
    for ev, n in counts.most_common():
        print(f'  {ev}: {n}')
except FileNotFoundError:
    pass
")

cat > "$PSR_DIR/post-run-state.md" <<MD
# PSR-006 post-run state

Captured by take-after-snapshot.sh.

## Test project friction log delta (load-bearing)

Path: ~/workspaces/MageContextABTest/workflow-friction.log

- Baseline: $TEST_BASELINE lines (see baseline.md)
- Post-run: $TEST_AFTER lines
- Delta: $TEST_DELTA new events
- Captured to: test-project-friction.jsonl (also aliased as friction.jsonl)

## Master log delta (orchestrator-side, noise)

Path: $MASTER_LOG

- Baseline: $MASTER_BASELINE lines
- Post-run: $MASTER_AFTER lines
- Delta: $MASTER_DELTA new events
- Captured to: master-friction.jsonl

## Event-type breakdown (test-project delta)

$EVENT_BREAKDOWN

## Daemon state

- GET /health: $HEALTH
- GET /dashboard: $DASHBOARD

## Next step

Paste the test transcript into the orchestrator session for
grading. Analysis will land in analysis.md.
MD

echo "snapshot captured"
echo "  baseline: $BASELINE"
echo "  post-run: $AFTER"
echo "  delta:    $DELTA"
echo "  health:   $HEALTH"
echo "  dashboard:$DASHBOARD"
echo
echo "see $PSR_DIR/post-run-state.md"