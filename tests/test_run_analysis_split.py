"""Structural guard for the Wave 2 run-analysis.sh -> sourced-analyzer-lib split.

The split moves the 8 analyzer functions verbatim into bin/lib/analyzers-lang.sh
(the 7 per-language analyzers) and bin/lib/analyzers-regex.sh (analyze_all_regex_scanners),
and run-analysis.sh sources them. It MUST be source-based (in-process): the analyzers
stay in the one already-forked process, so no extra python3 subprocess is added
(tests/test_auth_scan_suppression.py asserts a <=3 spawn ceiling).

RED today: the two libs do not exist and the analyzers are still defined inline in
run-analysis.sh.
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
RUN_ANALYSIS = REPO / "bin" / "run-analysis.sh"
LANG_LIB = REPO / "bin" / "lib" / "analyzers-lang.sh"
REGEX_LIB = REPO / "bin" / "lib" / "analyzers-regex.sh"

LANG_FUNCS = [
    "analyze_php", "analyze_xml", "analyze_js_ts", "analyze_python",
    "analyze_rust", "analyze_go", "analyze_graphql",
]
REGEX_FUNCS = ["analyze_all_regex_scanners"]


def _declared_functions(lib: Path) -> set[str]:
    """Source the lib in a fresh bash and list the functions it defines. Function
    definitions do not call common.sh helpers (only call-time does), so the lib can
    be sourced standalone to enumerate its declared functions."""
    r = subprocess.run(
        ["bash", "-c", f'source "{lib}" 2>/dev/null; declare -F'],
        capture_output=True, text=True,
    )
    return {line.split()[-1] for line in r.stdout.splitlines() if line.startswith("declare -f ")}


class TestAnalyzerLibsDefined:
    def test_lang_lib_defines_the_seven_language_analyzers(self) -> None:
        declared = _declared_functions(LANG_LIB)
        missing = [f for f in LANG_FUNCS if f not in declared]
        assert missing == [], f"analyzers-lang.sh must define {LANG_FUNCS}; missing {missing}"

    def test_regex_lib_defines_the_scanner(self) -> None:
        declared = _declared_functions(REGEX_LIB)
        assert set(REGEX_FUNCS) <= declared, (
            f"analyzers-regex.sh must define {REGEX_FUNCS}; declared {sorted(declared)}"
        )


class TestRunAnalysisWiring:
    def test_run_analysis_sources_both_libs(self) -> None:
        src = RUN_ANALYSIS.read_text()
        assert "analyzers-lang.sh" in src, "run-analysis.sh must source analyzers-lang.sh"
        assert "analyzers-regex.sh" in src, "run-analysis.sh must source analyzers-regex.sh"

    def test_analyzers_not_defined_inline_in_run_analysis(self) -> None:
        src = RUN_ANALYSIS.read_text()
        for fn in LANG_FUNCS + REGEX_FUNCS:
            assert f"{fn}()" not in src, (
                f"{fn} must move to a lib, not stay defined inline in run-analysis.sh"
            )


class TestLibsInheritSetE:
    def test_no_lib_declares_its_own_set_e(self) -> None:
        # The libs are sourced INTO run-analysis.sh's `set -euo pipefail` shell; they
        # must inherit it, not re-declare (which could change option state).
        for lib in (LANG_LIB, REGEX_LIB):
            for n, line in enumerate(lib.read_text().splitlines(), 1):
                stripped = line.strip()
                assert not stripped.startswith("set -e") and not stripped.startswith("set -euo"), (
                    f"{lib.name}:{n} must not declare its own set -e (inherits from caller)"
                )


class TestDispatchStillWorks:
    def test_smoke_emits_valid_json_and_sane_exit(self, tmp_path) -> None:
        # Wiring regression guard: the sourced dispatch still runs end-to-end and
        # prints a JSON array. A benign file yields an empty array; the point is that
        # the sourced analyzers load and the dispatch loop produces valid JSON.
        f = tmp_path / "sample.py"
        f.write_text("import os\n\n\ndef add(x, y):\n    return x + y\n")
        r = subprocess.run(
            ["bash", str(RUN_ANALYSIS), "--project-root", str(tmp_path), str(f)],
            capture_output=True, text=True,
        )
        assert r.returncode in (0, 1), f"unexpected exit {r.returncode}; stderr={r.stderr[:400]}"
        parsed = json.loads(r.stdout)
        assert isinstance(parsed, list), f"run-analysis.sh must emit a JSON array; got {r.stdout[:200]!r}"
