"""Tests for writ/shared/percentile.py (Wave-3 Cycle G).

HERMETIC: pure functions over lists, no Neo4j, no I/O.

TestPercentile + TestAdoptersUsePercentile are RED until writ/shared/percentile.py
exists and the three call sites (friction.py, metrics.py, profile_hotpath.py) adopt it.

TestMetricsP50P90Equivalence + TestProfileEquivalence import `percentile` directly, so
they ERROR (collection-time ImportError) until the module exists; once it exists they
prove the shared helper reproduces the exact values the pre-existing inline
implementations produced (the behavior-preservation crux of this refactor).
"""

import pytest


class TestPercentile:
    """Direct unit tests of writ.shared.percentile.percentile."""

    def setup_method(self):
        try:
            from writ.shared.percentile import percentile
        except ImportError as exc:
            pytest.fail(f"writ.shared.percentile.percentile not importable yet: {exc}")
        self.percentile = percentile

    def test_empty_list_returns_zero(self):
        assert self.percentile([], 50) == 0

    def test_single_element_p50(self):
        assert self.percentile([42], 50) == 42

    def test_single_element_p90(self):
        assert self.percentile([42], 90) == 42

    def test_single_element_p95(self):
        assert self.percentile([42], 95) == 42

    def test_single_element_p99(self):
        assert self.percentile([42], 99) == 42

    def test_twenty_element_p50(self):
        values = list(range(10, 201, 10))  # [10, 20, ..., 200], n=20
        assert self.percentile(values, 50) == 110  # idx int(20*0.5)=10

    def test_twenty_element_p90(self):
        values = list(range(10, 201, 10))
        assert self.percentile(values, 90) == 190  # idx int(20*0.9)=18

    def test_twenty_element_p95(self):
        values = list(range(10, 201, 10))
        assert self.percentile(values, 95) == 200  # idx int(20*0.95)=19

    def test_twenty_element_p100(self):
        values = list(range(10, 201, 10))
        assert self.percentile(values, 100) == 200  # idx clamped to 19

    def test_sorts_unsorted_input(self):
        # [200, 10, 110] sorts to [10, 110, 200]; idx int(3*0.5)=1 -> 110
        assert self.percentile([200, 10, 110], 50) == 110

    def test_idx_never_exceeds_len_minus_one(self):
        values = list(range(10, 201, 10))
        # pct=100 exercises the clamp: int(20*100/100)=20, clamped to 19 -> max element
        assert self.percentile(values, 100) == max(values)


def _head_p50(st: list[int]) -> int:
    """Frozen HEAD-inline reproduction of metrics.py's p50 (st must be sorted)."""
    n = len(st)
    return st[n // 2]


def _head_p90(st: list[int]) -> int:
    """Frozen HEAD-inline reproduction of metrics.py's p90 (st must be sorted)."""
    n = len(st)
    return st[int(n * 0.9)] if n >= 10 else st[-1]


class TestMetricsP50P90Equivalence:
    """Differential test: percentile() must reproduce metrics.py's pinned p50/p90,
    including the n<10 branch where _head_p90 falls back to st[-1] but percentile's
    generic clamp (int(0.9n) capped to n-1) must land on the same value.
    """

    def setup_method(self):
        try:
            from writ.shared.percentile import percentile
        except ImportError as exc:
            pytest.fail(f"writ.shared.percentile.percentile not importable yet: {exc}")
        self.percentile = percentile

    @pytest.mark.parametrize("n", [1, 2, 5, 9, 10, 11, 20, 100])
    def test_p50_matches_head_inline(self, n):
        sorted_times = list(range(10, 10 * n + 1, 10))  # sorted ascending, len == n
        assert self.percentile(sorted_times, 50) == _head_p50(sorted_times)

    @pytest.mark.parametrize("n", [1, 2, 5, 9, 10, 11, 20, 100])
    def test_p90_matches_head_inline(self, n):
        sorted_times = list(range(10, 10 * n + 1, 10))  # sorted ascending, len == n
        assert self.percentile(sorted_times, 90) == _head_p90(sorted_times)


def _head_profile(lat: list[float], pct: float) -> float:
    """Frozen HEAD-inline reproduction of profile_hotpath.py's percentile
    (lat must already be sorted)."""
    return lat[int(len(lat) * pct / 100)]


class TestProfileEquivalence:
    """Differential test: percentile() must reproduce profile_hotpath.py's
    pinned p50/p95/p99 over an already-sorted, non-empty latency list."""

    def setup_method(self):
        try:
            from writ.shared.percentile import percentile
        except ImportError as exc:
            pytest.fail(f"writ.shared.percentile.percentile not importable yet: {exc}")
        self.percentile = percentile
        # sorted, non-empty float latency sample (~20 elements)
        self.latencies = sorted(
            [1.0, 2.5, 3.0, 4.2, 5.9, 6.1, 7.3, 8.8, 9.0, 10.4,
             11.1, 12.6, 13.3, 14.7, 15.2, 16.9, 17.5, 18.0, 19.8, 20.1]
        )

    @pytest.mark.parametrize("pct", [50, 95, 99])
    def test_matches_head_inline(self, pct):
        assert self.percentile(self.latencies, pct) == _head_profile(self.latencies, pct)


class TestAdoptersUsePercentile:
    """Source guard: confirms the three call sites import and use the shared
    helper instead of a local inline implementation. RED until Cycle G lands."""

    def _read(self, relative_path):
        import pathlib
        repo_root = pathlib.Path(__file__).resolve().parent.parent
        return (repo_root / relative_path).read_text()

    def test_percentile_module_defines_percentile(self):
        src = self._read("writ/shared/percentile.py")
        assert "def percentile(" in src

    def test_friction_imports_and_uses_shared_percentile(self):
        src = self._read("writ/analysis/friction.py")
        assert "from writ.shared.percentile import percentile" in src
        assert "percentile(" in src
        assert "def _percentile" not in src

    def test_metrics_imports_and_uses_shared_percentile(self):
        src = self._read("writ/session/metrics.py")
        assert "from writ.shared.percentile import percentile" in src
        assert "percentile(sorted_times, 50)" in src
        assert "percentile(sorted_times, 90)" in src
        assert "sorted_times[n // 2]" not in src
        assert "int(n * 0.9)" not in src

    def test_profile_hotpath_imports_and_uses_shared_percentile(self):
        src = self._read("scripts/profile_hotpath.py")
        assert "from writ.shared.percentile import percentile" in src
        assert "latencies[int(len(latencies) * 0.95)]" not in src
