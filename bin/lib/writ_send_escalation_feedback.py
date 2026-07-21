"""C10 negative-feedback POSTer for writ-rag-inject.sh.

Extracted VERBATIM from the hook's inline `python3 -c` block (was lines 696-723).
argv[1]=cache JSON, argv[2]=gate; POSTs one negative signal per distinct rule id.
The localhost:8765 URL is a pre-existing hook quirk, preserved verbatim. stdlib-only."""
import sys, json

cache_str = sys.argv[1]
gate = sys.argv[2]

try:
    cache = json.loads(cache_str)
except Exception:
    sys.exit(0)

records = cache.get('invalidation_history', {}).get(gate, [])
rule_ids = set(r['rule_id'] for r in records)

import urllib.request, urllib.error
for rid in rule_ids:
    payload = json.dumps({'rule_id': rid, 'signal': 'negative'}).encode()
    req = urllib.request.Request(
        'http://localhost:8765/feedback',
        data=payload,
        headers={'Content-Type': 'application/json'},
        method='POST',
    )
    try:
        urllib.request.urlopen(req, timeout=0.3)
    except (urllib.error.URLError, OSError):
        break
