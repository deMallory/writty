"""Invalidated-gate "backward context" renderer for writ-rag-inject.sh.

Extracted VERBATIM from the hook's inline `python3 -c` block (was lines 740-771).
argv[1]=cache JSON, argv[2]=gate dir; prints the INVALIDATED block or nothing.
stdlib-only; fail-open."""
import sys, json, os

cache_str = sys.argv[1]
gate_dir = sys.argv[2]

try:
    cache = json.loads(cache_str)
except Exception:
    sys.exit(0)

history = cache.get('invalidation_history', {})
for gate_name, records in history.items():
    if not records:
        continue
    gate_file = os.path.join(gate_dir, f'{gate_name}.approved')
    if not os.path.exists(gate_file):
        # Gate was invalidated and not yet re-approved
        latest = records[-1]
        cycle = len(records)
        max_cycles = 3
        plan_hash = latest.get('prior_plan_hash', 'unknown')
        lines = []
        lines.append(f'[Writ: {gate_name} INVALIDATED -- cycle {cycle} of {max_cycles}]')
        lines.append('Previous plan failed validation:')
        for r in records:
            lines.append(f'  - {r["rule_id"]} violated in {r["file"]} ({r.get("evidence", "")[:120]})')
        lines.append(f'Revise the plan to address these gaps.')
        lines.append(f'Previous plan hash: {plan_hash} (do not resubmit unchanged)')
        print('\n'.join(lines))
        break  # Only inject for the first invalidated gate
