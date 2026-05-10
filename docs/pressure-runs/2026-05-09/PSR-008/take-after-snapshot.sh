#!/usr/bin/env bash
# Capture PSR-008 friction-log delta + daemon health post-run.
#
# Validates the seven 2026-05-09 commits: Phase 6j unblock, always-on
# methodology extension, ExitPlanMode reset, hook stderr, etc.
#
# Reads two logs (master + test project), looks for the new event
# types this PSR cares about (query_source=methodology, always_on_inject).

set -euo pipefail

WRIT_ROOT="/home/lucio.saldivar/.claude/skills/writ"
PSR_DIR="$WRIT_ROOT/docs/pressure-runs/2026-05-09/PSR-008"
MASTER_LOG="$WRIT_ROOT/workflow-friction.log"
TEST_LOG="/home/lucio.saldivar/workspaces/MageContextABTest/workflow-friction.log"

TEST_BASELINE=475
TEST_AFTER=$(wc -l < "$TEST_LOG" 2>/dev/null || echo "$TEST_BASELINE")
TEST_DELTA=$((TEST_AFTER - TEST_BASELINE))
if [ "$TEST_DELTA" -gt 0 ]; then
    sed -n "$((TEST_BASELINE + 1)),${TEST_AFTER}p" "$TEST_LOG" > "$PSR_DIR/test-project-friction.jsonl"
else
    : > "$PSR_DIR/test-project-friction.jsonl"
fi

MASTER_BASELINE=15863
MASTER_AFTER=$(wc -l < "$MASTER_LOG")
MASTER_DELTA=$((MASTER_AFTER - MASTER_BASELINE))
if [ "$MASTER_DELTA" -gt 0 ]; then
    sed -n "$((MASTER_BASELINE + 1)),${MASTER_AFTER}p" "$MASTER_LOG" > "$PSR_DIR/master-friction.jsonl"
else
    : > "$PSR_DIR/master-friction.jsonl"
fi

cp "$PSR_DIR/test-project-friction.jsonl" "$PSR_DIR/friction.jsonl"

# Event-type breakdown across BOTH deltas (methodology + always_on
# events typically land in master log because the inject hook runs
# in the agent's main session).
cat "$PSR_DIR/test-project-friction.jsonl" "$PSR_DIR/master-friction.jsonl" \
    > "$PSR_DIR/_combined-delta.jsonl"

EVENT_BREAKDOWN=$(python3 -c "
import json, collections
counts = collections.Counter()
methodology = 0
always_on = 0
phase_advances = []
exit_plan_resets = 0
try:
    for line in open('$PSR_DIR/_combined-delta.jsonl'):
        line = line.strip()
        if not line: continue
        try:
            d = json.loads(line)
            ev = d.get('event','?')
            counts[ev] += 1
            if ev == 'rag_query' and d.get('query_source') == 'methodology':
                methodology += 1
            if ev == 'always_on_inject':
                always_on += 1
            if ev == 'phase_advance':
                phase_advances.append(f\"{d.get('from_phase')}->{d.get('to_phase')}\")
        except json.JSONDecodeError:
            counts['_parse_error'] += 1
except FileNotFoundError:
    pass
for ev, n in counts.most_common():
    print(f'  {ev}: {n}')
print()
print(f'  query_source=methodology: {methodology}')
print(f'  always_on_inject:         {always_on}')
print(f'  phase advances:           {phase_advances}')
" 2>/dev/null || echo "  (event breakdown unavailable)")

HEALTH=$(curl -sf -o /dev/null -w "%{http_code}" http://localhost:8765/health 2>/dev/null || echo "DOWN")
DASHBOARD=$(curl -sf -o /dev/null -w "%{http_code}" http://localhost:8765/dashboard 2>/dev/null || echo "DOWN")

ALWAYS_ON_POST=$(curl -s --max-time 3 "http://localhost:8765/always-on?mode=work" 2>/dev/null | python3 -c "
import json, sys
try:
    d = json.load(sys.stdin)
    rules = d.get('rules', [])
    skl = [r['rule_id'] for r in rules if r['rule_id'].startswith('SKL-')]
    pbk = [r['rule_id'] for r in rules if r['rule_id'].startswith('PBK-')]
    enf = [r['rule_id'] for r in rules if r['rule_id'].startswith('ENF-')]
    frb = [r['rule_id'] for r in rules if r['rule_id'].startswith('FRB-')]
    print(f'  count: {len(rules)}, total_tokens: {d.get(\"total_tokens\")}')
    print(f'  ENF: {enf}')
    print(f'  FRB: {frb}')
    print(f'  SKL: {skl}')
    print(f'  PBK: {pbk}')
except Exception as e:
    print(f'  (failed to parse: {e})')
" 2>/dev/null || echo "  (always-on unreachable)")

cat > "$PSR_DIR/post-run-state.md" <<MD
# PSR-008 post-run state

Captured by take-after-snapshot.sh.

## Friction-log deltas

| log | baseline | after | delta |
|---|---:|---:|---:|
| Test project | $TEST_BASELINE | $TEST_AFTER | $TEST_DELTA |
| Master | $MASTER_BASELINE | $MASTER_AFTER | $MASTER_DELTA |

## Event breakdown (combined delta)

\`\`\`
$EVENT_BREAKDOWN
\`\`\`

## Server health

- /health: $HEALTH
- /dashboard: $DASHBOARD

## /always-on?mode=work post-run

\`\`\`
$ALWAYS_ON_POST
\`\`\`
MD

rm -f "$PSR_DIR/_combined-delta.jsonl"

echo "Captured PSR-008 snapshot:"
echo "  test delta: $TEST_DELTA lines"
echo "  master delta: $MASTER_DELTA lines"
echo "  /health: $HEALTH"
echo "  See: $PSR_DIR/post-run-state.md"
