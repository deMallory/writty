"""Guard for the Wave 3 hook marker-walk dedup.

Four hooks inlined an identical project-root marker-walk (`python3 -c` block: markers
[composer.json, package.json, Cargo.toml, go.mod, pyproject.toml, .git], start os.getcwd(),
walk to '/', print dir or empty) despite sourcing common.sh's detect_project_root. The dedup
replaces each inline walk with `$(detect_project_root "$(pwd)")`.

RED today: the four hooks still contain the inline `markers = ['composer.json',...]` walk and
do not call detect_project_root for PROJECT_ROOT.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
HOOKS = REPO / "hooks" / "scripts"
COMMON = REPO / "bin" / "lib" / "common.sh"
FOUR = ["friction-logger.sh", "auto-approve-gate.sh", "validate-exit-plan.sh", "writ-rag-inject.sh"]


def _run_detect(path: str) -> str:
    r = subprocess.run(
        ["bash", "-c", 'source "$1"; detect_project_root "$2"', "_", str(COMMON), path],
        capture_output=True, text=True, timeout=20,
    )
    return r.stdout.strip()


class TestHooksUseHelper:
    def test_four_hooks_call_detect_project_root(self) -> None:
        for h in FOUR:
            src = (HOOKS / h).read_text()
            assert "detect_project_root" in src, f"{h} must call detect_project_root"
            assert "markers = ['composer.json'" not in src, (
                f"{h} must not keep the inline marker-walk"
            )

    def test_hooks_pass_physical_pwd(self) -> None:
        # pwd -P (physical, symlink-resolved) matches the OLD inline os.getcwd(), so
        # PROJECT_ROOT stays byte-identical even when the cwd is reached via a symlink
        # (bare `pwd` is logical and would diverge). Behavior-preservation, not convenience.
        for h in FOUR:
            src = (HOOKS / h).read_text()
            assert 'detect_project_root "$(pwd -P)"' in src, (
                f"{h} must pass pwd -P (physical) for os.getcwd() parity"
            )

    def test_auto_approve_project_root_still_deferred(self) -> None:
        # POL-5b-3b: PROJECT_ROOT must be computed inside the approval conditional, never
        # unconditionally at column 0 (mirrors test_pol5b3b::test_project_root_not_unconditional).
        import re

        src = (HOOKS / "auto-approve-gate.sh").read_text()
        assert re.search(r"^PROJECT_ROOT=\$\(", src, re.M) is None, (
            "auto-approve must keep PROJECT_ROOT deferred (indented, inside the approval block)"
        )


class TestDetectProjectRootEquivalence:
    def test_finds_nearest_ancestor_with_marker(self, tmp_path) -> None:
        (tmp_path / "pyproject.toml").write_text("[project]\n")
        sub = tmp_path / "a" / "b"
        sub.mkdir(parents=True)
        assert _run_detect(str(sub)) == str(tmp_path)

    def test_empty_or_not_self_when_no_marker(self, tmp_path) -> None:
        # a bare dir with no marker: detect_project_root walks past it (to an ancestor with a
        # marker, or to '/' -> empty). Either way it must NOT claim the marker-less dir itself.
        bare = tmp_path / "no_markers"
        bare.mkdir()
        assert _run_detect(str(bare)) != str(bare)
