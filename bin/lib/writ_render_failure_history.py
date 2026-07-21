"""Escalation "Failure history" renderer for writ-rag-inject.sh.

Extracted VERBATIM from the hook's inline `python3 -c` block (was lines 648-679).
argv[1]=cache JSON, argv[2]=gate, argv[3]=diagnosis; prints the multi-line history.
stdlib-only; fail-open (malformed cache -> empty records)."""
import sys, json

cache_str = sys.argv[1]
gate = sys.argv[2]
diagnosis = sys.argv[3]

try:
    cache = json.loads(cache_str)
except Exception:
    cache = {}

records = cache.get('invalidation_history', {}).get(gate, [])
lines = []
for r in records:
    lines.append(f"  Cycle {r['cycle']}: {r['rule_id']} violated in {r['file']} ({r.get('evidence', 'no evidence')[:120]})")

if diagnosis == 'same-rule':
    lines.append('')
    lines.append('  Same rule triggered all cycles. Possible causes:')
    lines.append('    1. Plan repeatedly fails to address this rule')
    lines.append('    2. Rule violation pattern is over-broad for this context')
    lines.append('    3. Task requires an exception to this rule')
elif diagnosis == 'different-rules':
    lines.append('')
    lines.append('  Different rule each cycle. Plan is broadly missing rule coverage.')
else:
    lines.append('')
    lines.append('  Mixed pattern. Specific gaps in the plan.')

print('\n'.join(lines))
