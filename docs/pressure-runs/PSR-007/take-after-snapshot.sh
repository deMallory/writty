#!/usr/bin/env bash
# Capture PSR-007 friction-log delta + daemon health post-run.
#
# Same shape as PSR-005b/006 helper. Reads two logs:
#   - test project (load-bearing for grading)
#   - master log (orchestrator-side noise)

set -euo pipefail

WRIT_ROOT="~/.claude/skills/writ"
PSR_DIR="$WRIT_ROOT/docs/pressure-runs/PSR-007"
MASTER_LOG="$WRIT_ROOT/workflow-friction.log"
TEST_LOG="~/workspaces/MageContextABTest/workflow-friction.log"

TEST_BASELINE=379
TEST_AFTER=$(wc -l < "$TEST_LOG" 2>/dev/null || echo "$TEST_BASELINE")
TEST_DELTA=$((TEST_AFTER - TEST_BASELINE))
if [ "$TEST_DELTA" -gt 0 ]; then
    sed -n "$((TEST_BASELINE + 1)),${TEST_AFTER}p" "$TEST_LOG" > "$PSR_DIR/test-project-friction.jsonl"
else
    : > "$PSR_DIR/test-project-friction.jsonl"
fi

MASTER_BASELINE=9718
MASTER_AFTER=$(wc -l < "$MASTER_LOG")
MASTER_DELTA=$((MASTER_AFTER - MASTER_BASELINE))
if [ "$MASTER_DELTA" -gt 0 ]; then
    sed -n "$((MASTER_BASELINE + 1)),${MASTER_AFTER}p" "$MASTER_LOG" > "$PSR_DIR/master-friction.jsonl"
else
    : > "$PSR_DIR/master-friction.jsonl"
fi

cp "$PSR_DIR/test-project-friction.jsonl" "$PSR_DIR/friction.jsonl"

# Event-type breakdown from the test-project delta
EVENT_BREAKDOWN=$(python3 -c "
import json, sys, collections
counts = collections.Counter()
try:
    for line in open('$PSR_DIR/test-project-friction.jsonl'):
        line = line.strip()
        if not line: continue
        try:
            d = json.loads(line)
            counts[d.get('event','?')] += 1
        except json.JSONDecodeError:
            counts['_parse_error'] += 1
except FileNotFoundError:
    pass
for ev, n in counts.most_common():
    print(f'  {ev}: {n}')
" 2>/dev/null || echo "  (event breakdown unavailable)")

HEALTH=$(curl -sf -o /dev/null -w "%{http_code}" http://localhost:8765/health 2>/dev/null || echo "DOWN")
DASHBOARD=$(curl -sf -o /dev/null -w "%{http_code}" http://localhost:8765/dashboard 2>/dev/null || echo "DOWN")

cat > "$PSR_DIR/post-run-state.md" <<MD
# PSR-007 post-run state

Captured by take-after-snapshot.sh.

## Test project friction log delta (load-bearing)

Path: $TEST_LOG

- Baseline: $TEST_BASELINE lines
- Post-run: $TEST_AFTER lines
- Delta: $TEST_DELTA new events
- Captured to: test-project-friction.jsonl (also aliased as friction.jsonl)

## Master log delta (orchestrator-side noise)

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

## Phase 6 final-verification status

Awaiting transcript paste + grading in analysis.md.
MD

echo "snapshot captured"
echo "  test-project baseline: $TEST_BASELINE"
echo "  test-project post-run: $TEST_AFTER"
echo "  test-project delta:    $TEST_DELTA"
echo "  master delta:          $MASTER_DELTA"
echo "  health:                $HEALTH"
echo "  dashboard:             $DASHBOARD"
echo
echo "see $PSR_DIR/post-run-state.md"
