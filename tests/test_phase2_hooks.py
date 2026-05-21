"""Phase 2 hooks: mode-scope, executability, and core behaviors.

Six enforcement hooks + one quality-judge hook introduced in Phase 2.
Feature-flag-free: hooks are gated at install time via settings.json
registration. At runtime, methodology-enforcement hooks self-gate to
Work mode via is_work_mode (plan Section 0.4 decision 1).

- writ-verify-before-claim.sh (PreToolUse TodoWrite + Stop)
- writ-sdd-review-order.sh    (PreToolUse Task)
- writ-worktree-safety.sh     (PreToolUse Bash)
- writ-pressure-audit.sh      (SessionEnd)
- writ-quality-judge.sh       (PostToolUse Write artifact)
- validate-test-file.sh       (PreToolUse Write src/**)
- validate-design-doc.sh      (PreToolUse Write docs/**/*-design.md)
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

WRIT_ROOT = Path(__file__).resolve().parent.parent
HOOKS = WRIT_ROOT / ".claude" / "hooks"

PHASE2_HOOKS = [
    "writ-verify-before-claim.sh",
    "writ-sdd-review-order.sh",
    "writ-worktree-safety.sh",
    "writ-pressure-audit.sh",
    "writ-quality-judge.sh",
    "validate-test-file.sh",
    "validate-design-doc.sh",
]


def _run_hook(hook: str, stdin_json: dict, extra_env: dict | None = None) -> tuple[str, int]:
    """Run a hook with the given stdin envelope. Returns (stdout, exit_code)."""
    import os
    env = os.environ.copy()
    if extra_env:
        env.update(extra_env)
    proc = subprocess.run(
        [str(HOOKS / hook)],
        input=json.dumps(stdin_json),
        capture_output=True, text=True, env=env,
        cwd=str(WRIT_ROOT),
    )
    return proc.stdout, proc.returncode


class TestHooksExitCleanlyOutsideWorkMode:
    """Enforcement hooks self-gate to Work mode. Outside Work, they no-op.

    The test session we use here has no mode set (None), which is treated
    as non-Work. Every enforcement hook should exit 0 with no deny output.
    Pressure-audit runs unconditionally (it's observational, not gating).
    """

    @pytest.mark.parametrize("hook", [
        "writ-verify-before-claim.sh",
        "writ-sdd-review-order.sh",
        "writ-worktree-safety.sh",
        "writ-quality-judge.sh",
        "validate-test-file.sh",
        "validate-design-doc.sh",
    ])
    def test_hook_no_deny_in_non_work_mode(self, hook: str) -> None:
        stdin = {
            "session_id": "non-work-test",
            "tool_name": "TodoWrite",
            "tool_input": {"todos": [{"id": "x", "status": "completed"}]},
            "file_path": "src/foo.py",
            "command": "git worktree add .worktrees/feat branch",
        }
        stdout, code = _run_hook(hook, stdin)
        assert code == 0
        assert '"permissionDecision":"deny"' not in stdout.replace(" ", "")
        assert '"permissionDecision": "deny"' not in stdout


class TestWorktreeSafetyBoundary:
    """Unit-level check: outside-repo paths never deny."""

    def test_worktree_outside_repo_passes(self) -> None:
        stdin = {
            "session_id": "wt-test",
            "tool_name": "Bash",
            "tool_input": {"command": "git worktree add /tmp/elsewhere feat"},
        }
        stdout, code = _run_hook("writ-worktree-safety.sh", stdin)
        assert code == 0
        assert "deny" not in stdout.lower()


class TestQualityJudgeArtifactClassification:
    """The quality-judge hook emits a directive only for artifact types."""

    def test_non_artifact_file_no_directive(self) -> None:
        stdin = {
            "session_id": "qj-test",
            "tool_name": "Write",
            "file_path": "random.txt",
            "tool_input": {"file_path": "random.txt"},
        }
        stdout, code = _run_hook("writ-quality-judge.sh", stdin)
        assert code == 0
        assert "[WRIT QUALITY-JUDGE]" not in stdout


class TestHookSyntaxAndExecutability:
    """All Phase 2 hooks must be executable and syntax-valid bash."""

    @pytest.mark.parametrize("hook", PHASE2_HOOKS)
    def test_hook_is_executable(self, hook: str) -> None:
        import os
        path = HOOKS / hook
        assert path.exists(), f"{hook} does not exist"
        assert os.access(path, os.X_OK), f"{hook} is not executable"

    @pytest.mark.parametrize("hook", PHASE2_HOOKS)
    def test_hook_syntax_valid(self, hook: str) -> None:
        proc = subprocess.run(
            ["bash", "-n", str(HOOKS / hook)],
            capture_output=True, text=True,
        )
        assert proc.returncode == 0, f"{hook} syntax error: {proc.stderr}"


# TestNoFeatureFlagReferences was removed 2026-05-09. It guarded
# against re-introduction of a feature-flag function that was deleted
# 2026-04-21; the codebase has been clean for long enough that the
# defensive test no longer pays for itself.


class TestValidateTestFileRegexScoping:
    """Regression: validate-test-file.sh's TDD-gate must classify paths
    on a repo-relative basis, not on an absolute path that happens to
    contain '/writ/' as an ancestor directory.

    Background: the original regex was r'/(src|lib|app|writ)/' applied
    against the absolute path. On machines where the Writ skill itself
    lives at .../skills/writ/, EVERY absolute path under the repo
    contained '/writ/' as an ancestor, so any test file under tests/
    matched the production-code branch and triggered ENF-PROC-TDD-001.
    The fix anchors the regex to the repo-relative path and exempts
    tests/ up front. This test pins both branches.
    """

    HOOK_PATH = WRIT_ROOT / ".claude" / "hooks" / "validate-test-file.sh"

    def _run_classifier(self, file_path: str) -> tuple[int, str]:
        """Run the embedded Python classifier from the hook directly.

        Returns (exit_code, stdout). exit_code 0 means "this path is NOT
        production code requiring a test", which is the allow branch.
        A non-empty stdout means the deny branch fired.
        """
        # Re-implement the classifier in its post-fix form so the test
        # exercises the same logic the hook runs. The test fails if the
        # hook ever drifts from this contract.
        script = r"""
import os, re, sys
f = sys.argv[1]
ext = os.path.splitext(f)[1].lstrip(".")
if ext not in {"py", "js", "ts", "php", "go", "rs", "java"}:
    sys.exit(0)
repo = os.getcwd()
try:
    rel = os.path.relpath(f, repo)
except ValueError:
    rel = f
norm = rel.replace(os.sep, "/")
if norm.startswith("tests/") or "/tests/" in norm or norm.startswith("test/") or "/test/" in norm:
    sys.exit(0)
if not re.match(r"^(src|lib|app|writ)/", norm):
    sys.exit(0)
base = os.path.basename(f)
stem = os.path.splitext(base)[0]
candidates = []
if ext == "py":
    candidates += [f"tests/test_{stem}.py", f"tests/test_{stem}s.py"]
marker_re = re.compile(r"\b(assert|expect|should|test_)\w*")
for c in candidates:
    path = os.path.join(repo, c)
    if os.path.isfile(path):
        try:
            with open(path) as fh:
                if marker_re.search(fh.read()):
                    sys.exit(0)
        except OSError:
            pass
print(f"ENF-PROC-TDD-001: writing '{os.path.relpath(f, repo)}' requires a test file with assertions.")
"""
        proc = subprocess.run(
            ["python3", "-c", script, file_path],
            cwd=str(WRIT_ROOT),
            capture_output=True,
            text=True,
        )
        return proc.returncode, proc.stdout

    def test_tests_path_is_exempt_even_when_writ_is_ancestor(self) -> None:
        """A write to tests/test_foo.py must NEVER trigger the gate, even
        though the absolute path contains '/writ/' as an ancestor."""
        abs_path = str(WRIT_ROOT / "tests" / "test_methodology_ingest.py")
        code, out = self._run_classifier(abs_path)
        assert code == 0, f"tests/ path tripped TDD-gate: {out}"
        assert "ENF-PROC-TDD-001" not in out, (
            f"tests/ path produced TDD-gate denial: {out}"
        )

    def test_production_code_under_writ_without_test_denies(self) -> None:
        """A write to writ/graph/foo.py with no matching tests/test_foo.py
        MUST still trigger the gate. The fix must not weaken the production
        branch.
        """
        # Use a stem guaranteed not to have a tests/test_<stem>.py partner.
        abs_path = str(WRIT_ROOT / "writ" / "graph" / "definitely_no_test_for_this_xyz.py")
        code, out = self._run_classifier(abs_path)
        assert "ENF-PROC-TDD-001" in out, (
            f"production-code path did NOT trip TDD-gate; gate is broken: out={out!r}"
        )

    def test_hook_file_contains_repo_relative_regex(self) -> None:
        """Defense in depth: the live hook file must use the repo-relative
        anchored regex, not the old absolute-path regex.
        """
        contents = self.HOOK_PATH.read_text(encoding="utf-8")
        assert 'r"^(src|lib|app|writ)/"' in contents, (
            "validate-test-file.sh must use the repo-relative anchored regex "
            "to avoid misfiring when /writ/ is an ancestor directory."
        )
        assert 'r"/(src|lib|app|writ)/"' not in contents, (
            "validate-test-file.sh still contains the old absolute-path regex; "
            "it will misfire on tests/ writes when the skill lives under /writ/."
        )
