"""Shared nearest-rank percentile.

Formerly inlined in three places (writ.analysis.friction._percentile,
writ.session.metrics p50/p90, scripts/profile_hotpath p50/p95/p99); this is the
single source of that index formula.
"""

from __future__ import annotations


def percentile(values: list[float], pct: float) -> float:
    """Nearest-rank percentile: sorted(values)[min(int(n*pct/100), n-1)]; 0 on empty.

    pct is 0-100.
    """
    if not values:
        return 0
    sorted_values = sorted(values)
    idx = int(len(sorted_values) * pct / 100)
    idx = min(idx, len(sorted_values) - 1)
    return sorted_values[idx]
