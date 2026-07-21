"""Guard for Wave-3 Cycle H: adopt writ/shared/percentile.py in
scripts/instrument-corpus-stats.py (the final §7 DRY closeout).

HERMETIC: does not import scripts/instrument-corpus-stats.py (it pulls onnx/pipeline
at module scope); the source-guard tests below read its source TEXT instead.

TestSourceGuard is RED until Cycle H lands: it asserts the shared-helper import and
call site are present and the old inline p75 index expression is gone.

TestP75Differential imports writ.shared.percentile directly (already merged in Cycle
G) and is GREEN from the start; it proves percentile(x, 75) reproduces the exact
pre-existing inline formula `sorted(x)[int(len(x)*0.75)]` across a spread of list
shapes, so the swap in Cycle H is behavior-identical.
"""

from __future__ import annotations

import pathlib

import pytest

from writ.shared.percentile import percentile

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
SCRIPT_PATH = REPO_ROOT / "scripts" / "instrument-corpus-stats.py"

OLD_INLINE_P75 = "sorted(all_pairwise)[int(len(all_pairwise)*0.75)]"
NEW_IMPORT = "from writ.shared.percentile import percentile"
NEW_CALL_SITE = "percentile(all_pairwise, 75)"


def _sample_lists() -> list[list[float]]:
    """A spread of list shapes for the p75 differential: n=1..10 (incl. n=6,8,9),
    a large list, one with duplicate values, and one unsorted.
    """
    return [
        [1.0],  # n=1
        [1.0, 2.0],  # n=2
        [3.0, 1.0, 2.0],  # n=3
        [4.0, 1.0, 3.0, 2.0],  # n=4
        [5.0, 3.0, 1.0, 4.0, 2.0],  # n=5
        [1.0, 2.0, 3.0, 4.0, 5.0, 6.0],  # n=6
        [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0],  # n=7
        [8.0, 7.0, 6.0, 5.0, 4.0, 3.0, 2.0, 1.0],  # n=8, unsorted
        list(range(1, 10)),  # n=9
        list(range(10, 0, -1)),  # n=10, unsorted (descending)
        [float(i % 13) for i in range(100)],  # n=100
        [3.0, 3.0, 1.0, 3.0, 2.0, 2.0],  # duplicate values
        [9.0, 2.0, 5.0, 2.0, 9.0, 1.0, 5.0],  # unsorted with duplicates
    ]


def _old_inline_p75(values: list[float]) -> float:
    """Frozen reproduction of the pre-Cycle-H inline formula (non-empty only)."""
    return sorted(values)[int(len(values) * 0.75)]


class TestSourceGuard:
    """Confirms scripts/instrument-corpus-stats.py adopts the shared percentile
    helper at the p75 call site instead of its own inline index expression.
    RED until Cycle H lands."""

    def setup_method(self):
        assert SCRIPT_PATH.exists(), f"expected script at {SCRIPT_PATH}"
        self.src = SCRIPT_PATH.read_text()

    def test_imports_shared_percentile(self):
        assert NEW_IMPORT in self.src, (
            f"expected '{NEW_IMPORT}' in {SCRIPT_PATH}"
        )

    def test_call_site_uses_percentile_helper(self):
        assert NEW_CALL_SITE in self.src, (
            f"expected '{NEW_CALL_SITE}' in {SCRIPT_PATH}"
        )

    def test_old_inline_p75_removed(self):
        assert OLD_INLINE_P75 not in self.src, (
            f"old inline p75 expression '{OLD_INLINE_P75}' still present in {SCRIPT_PATH}"
        )


class TestP75Differential:
    """Proves percentile(x, 75) reproduces the exact old inline formula, so the
    Cycle H swap is behavior-identical. GREEN from the start (writ.shared.percentile
    already merged in Cycle G)."""

    @pytest.mark.parametrize("values", _sample_lists())
    def test_percentile_matches_old_inline_formula(self, values):
        assert percentile(values, 75) == _old_inline_p75(values)
