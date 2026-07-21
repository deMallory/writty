"""POL-2: retrieval-benchmark test-harness dedup + encode-once (Wave 4).

INC-8..12 copy-pasted the bundle_completeness benchmark loop and the live_pipeline fixture into
five test files, each re-encoding the whole corpus. POL-2 centralizes the benchmark mechanics in
tests/fixtures/benchmark_harness.py and shares the expensive corpus/encode via session-scoped
conftest fixtures.

Structural dedup assertions (always run). The BEHAVIORAL guard -- that the move did not change
the computed numbers -- is the existing test_methodology_retrieval blocker tests + the five INC
test_bundle_completeness_holds, which run under the full suite.
"""
from __future__ import annotations

import re
from pathlib import Path

WRIT_ROOT = Path(__file__).resolve().parent.parent
TESTS = WRIT_ROOT / "tests"

# All five INC files had a local live_pipeline fixture (now the shared conftest one).
INC_BENCHMARK_FILES = [
    TESTS / "test_inc8_planning.py",
    TESTS / "test_inc9_receiving_review.py",
    TESTS / "test_inc10_worktree.py",
    TESTS / "test_inc11_methodology_check.py",
    TESTS / "test_inc12_verify_parallel.py",
]
# Only these four also had the inlined bundle_completeness loop (test_inc8 has no bundle test).
INC_BUNDLE_FILES = [
    TESTS / "test_inc9_receiving_review.py",
    TESTS / "test_inc10_worktree.py",
    TESTS / "test_inc11_methodology_check.py",
    TESTS / "test_inc12_verify_parallel.py",
]


class TestHarnessExists:
    def test_module_imports_with_expected_api(self) -> None:
        from tests.fixtures import benchmark_harness as bh

        for name in (
            "rrf_fuse",
            "bundle_for",
            "retrieve",
            "bundle_completeness",
            "benchmark_metrics",
        ):
            assert hasattr(bh, name), f"benchmark_harness missing {name}"
        assert isinstance(bh.BLOCKER_COMPLETENESS, float)
        assert bh.BLOCKER_COMPLETENESS >= 0.85, "blocker threshold must not be lowered"


class TestNoInlinedDuplication:
    """The five INC files must consume the shared harness, not redefine its mechanics."""

    @staticmethod
    def _src(p: Path) -> str:
        return p.read_text(encoding="utf-8")

    def test_inc_files_do_not_redefine_benchmark_fns(self) -> None:
        offenders: list[str] = []
        for f in INC_BENCHMARK_FILES:
            src = self._src(f)
            for fn in ("def bundle_for", "def rrf_fuse", "def retrieve"):
                if fn in src:
                    offenders.append(f"{f.name}: {fn}")
        assert not offenders, (
            "INC test files still inline benchmark functions (should import from "
            f"benchmark_harness):\n  " + "\n  ".join(offenders)
        )

    def test_inc_files_do_not_define_local_live_pipeline(self) -> None:
        offenders: list[str] = []
        for f in INC_BENCHMARK_FILES:
            if re.search(r"def\s+live_pipeline\b", self._src(f)):
                offenders.append(f.name)
        assert not offenders, (
            "INC test files still define a local live_pipeline fixture (should use the shared "
            f"conftest fixture):\n  " + "\n  ".join(offenders)
        )

    def test_inc_files_reference_the_shared_harness(self) -> None:
        # Each INC file with a bundle_completeness test should import the shared harness
        # (test_inc8 has no bundle test -- it only uses the shared live_pipeline fixture).
        missing = [
            f.name for f in INC_BUNDLE_FILES
            if "benchmark_harness" not in self._src(f)
        ]
        assert not missing, (
            "INC bundle-test files do not import the shared benchmark_harness: " + ", ".join(missing)
        )


class TestMethodologyRetrievalMigrated:
    def test_no_local_benchmark_fn_defs(self) -> None:
        src = (TESTS / "test_methodology_retrieval.py").read_text(encoding="utf-8")
        # The canonical functions now live in the harness; the retrieval test imports them.
        offenders = [fn for fn in ("def bundle_for", "def rrf_fuse") if fn in src]
        assert not offenders, (
            "test_methodology_retrieval still defines benchmark functions locally "
            f"(should import from benchmark_harness): {offenders}"
        )
        assert "benchmark_harness" in src, (
            "test_methodology_retrieval does not import the shared benchmark_harness"
        )
