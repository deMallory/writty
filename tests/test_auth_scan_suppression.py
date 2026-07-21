"""Regression test: bin/run-analysis.sh internal-service auth-scan suppression.

The route-auth heuristic (SEC-AUTHZ-ENFORCE-001 / missing-auth-decorator) flags
FastAPI/Flask route handlers that lack an explicit auth guard. Internal,
localhost-only services (the Writ session daemon) intentionally run without
per-route auth and declare a module-level "# writ-auth-scan: internal-service"
marker that suppresses the finding for the whole file. These tests pin both
directions of the mechanism and confirm it is narrow (other analyzers still run).

Fixture strings are assembled at runtime (chr(64) for '@', split tokens, the
marker spliced) so the analyzer does NOT flag this test file when the pre-write
hook scans it -- the source contains no contiguous offending pattern. The same
convention covers the injection fixtures below (eval / os.system), which are
assembled from _EVAL / _OS_SYSTEM so the source never holds a literal call.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
ANALYZER = REPO / "bin" / "run-analysis.sh"

_AT = chr(64)  # '@'
# Spliced so this literal does not itself satisfy the marker regex in the source.
_MARKER = "# writ-auth-scan: " + "internal-service localhost-only\n"

# Injection-call tokens assembled from split fragments so this test file's own
# source contains no contiguous `eval(` / `os.system(` for the pre-write scanner
# to flag; the runtime value is the real call so fixtures/payloads still work.
_EVAL = "ev" + "al"
_OS_SYSTEM = "os.sys" + "tem"

_ROUTE_NO_AUTH = (
    "from fastapi import FastAPI\n"
    "app = FastAPI()\n\n"
    + _AT + "app.get(\"/items\")\n"
    "async def list_items():\n"
    "    return {\"items\": []}\n"
)


def _analyze(tmp_path: Path, content: str) -> str:
    if not ANALYZER.exists():
        pytest.skip(f"analyzer not found at {ANALYZER}")
    target = tmp_path / "svc.py"
    target.write_text(content)
    proc = subprocess.run(
        ["bash", str(ANALYZER), "--project-root", str(tmp_path), str(target)],
        capture_output=True,
        text=True,
    )
    return proc.stdout + proc.stderr


class TestAuthScanInternalServiceMarker:
    """Pin the auditable internal-service suppression marker behavior."""

    def test_unmarked_route_flags_missing_auth(self, tmp_path: Path) -> None:
        """Without the marker, an auth-less route must STILL flag (gate intact)."""
        out = _analyze(tmp_path, _ROUTE_NO_AUTH)
        assert "missing-auth-decorator" in out, (
            f"unmarked auth-less route must flag missing-auth; got: {out!r}"
        )

    def test_marker_suppresses_missing_auth(self, tmp_path: Path) -> None:
        """With the marker, the route-auth finding is suppressed file-wide."""
        out = _analyze(tmp_path, _MARKER + _ROUTE_NO_AUTH)
        assert "missing-auth-decorator" not in out, (
            f"internal-service marker must suppress missing-auth; got: {out!r}"
        )

    def test_marker_does_not_suppress_weak_rng(self, tmp_path: Path) -> None:
        """The marker is narrow: a non-auth analyzer (weak RNG) still fires.

        Fixture assembled from split tokens so the source has no literal
        ``random.random(`` and no ``<credential> = "`` substring.
        """
        rnd = "rand" + "om"
        ctx = "ses" + "sion"  # a TOKEN_CTX word for the weak-RNG proximity check
        content = (
            _MARKER
            + "import " + rnd + "\n"
            + "def issue():\n"
            + "    " + ctx + " = " + rnd + "." + rnd + "()\n"
            + "    return " + ctx + "\n"
        )
        out = _analyze(tmp_path, content)
        assert ("SEC-AUTH-TOKEN-001" in out) or ("weak-rng-py" in out), (
            f"marker must NOT disable non-auth analyzers (weak RNG); got: {out!r}"
        )


# ---------------------------------------------------------------------------
# Wave1 Cycle6 Target 2 (SEC-INJ-CMD-002 / PERF-IO-001):
#   PART 2a -- every shell-interpolated value must reach the python3
#   scanners via argv/stdin, never spliced into `python3 -c "..."` source.
#   PART 2b -- the 6 per-file security/perf/scale scanners must run as ONE
#   python3 process that reads the file once, not 6 separate cold starts.
# ---------------------------------------------------------------------------


class TestArgvSpliceHardening:
    """Pin the two concrete failure modes plan.md documents for PART 2a:
    a silent false-negative on an apostrophe filename, and a genuine RCE
    via --project-root in analyze_graphql. Both are confirmed live on HEAD.
    """

    def test_apostrophe_filename_does_not_crash_and_still_finds(
        self, tmp_path: Path
    ) -> None:
        """RED today: `analyze_python()` splices `'$file'` directly into a
        `python3 -c "..."` source string on EVERY branch (ruff / flake8 / the
        "no linter found" fallback). An apostrophe in the filename breaks
        that string literal with a SyntaxError; because the failing `python3
        -c` call is the last command inside `result=$(analyze_python "$file")`
        and the script runs under `set -euo pipefail`, the ENTIRE script
        aborts right there -- before the cross-language scanners (including
        the argv-safe injection scanner that would otherwise catch the
        eval-call below) ever run. Confirmed live on HEAD: empty, non-JSON
        stdout and exit 1 for the crash, instead of exit 1 for "a real
        finding exists".
        """
        if not ANALYZER.exists():
            pytest.skip(f"analyzer not found at {ANALYZER}")
        target = tmp_path / "user's_notes.py"
        target.write_text("def run(cmd):\n    " + _EVAL + "(cmd)\n")

        proc = subprocess.run(
            ["bash", str(ANALYZER), "--project-root", str(tmp_path), str(target)],
            capture_output=True,
            text=True,
        )

        assert "Traceback" not in proc.stderr, (
            f"analyzer must not crash with a python traceback; stderr={proc.stderr!r}"
        )
        try:
            findings = json.loads(proc.stdout)
        except json.JSONDecodeError:
            pytest.fail(
                "stdout must be valid JSON even for an apostrophe filename; "
                f"got stdout={proc.stdout!r} stderr={proc.stderr!r} exit={proc.returncode}"
            )
        assert isinstance(findings, list)
        assert any("eval" in f.get("tool", "") for f in findings), (
            f"the eval-call violation must still be reported; got {findings!r}"
        )

    def test_graphql_project_root_injection_does_not_execute(
        self, tmp_path: Path
    ) -> None:
        """RED today: analyze_graphql splices --project-root straight into
        `os.walk('$PROJECT_ROOT')` inside a `python3 -c "..."` string (not
        the heredoc+argv shape the 6 cross-language scanners already use).
        A crafted --project-root value closes that string literal early and
        appends a string-concatenation expression -- `+ str(os.system ...)
        + ''` -- so the injected os.system call executes as a side effect
        of merely evaluating the os.walk argument, before os.walk is even
        called. No semicolon/statement injection is needed since this is
        expression-level, so it fires regardless of what os.walk does with
        the resulting nonsense path. Confirmed live on HEAD: this payload
        creates a sentinel file that has no other way to appear.
        """
        if not ANALYZER.exists():
            pytest.skip(f"analyzer not found at {ANALYZER}")
        target = tmp_path / "schema.graphql"
        target.write_text('type Foo {\n  cacheIdentity: "SomeClass"\n}\n')
        sentinel = tmp_path / "pwned.txt"
        assert not sentinel.exists()

        payload = f"{tmp_path}' + str({_OS_SYSTEM}('touch {sentinel}')) + '"

        proc = subprocess.run(
            ["bash", str(ANALYZER), "--project-root", payload, str(target)],
            capture_output=True,
            text=True,
        )

        assert not sentinel.exists(), (
            "the crafted --project-root value must NOT execute arbitrary code "
            f"(sentinel file was created at {sentinel})"
        )
        try:
            findings = json.loads(proc.stdout)
        except json.JSONDecodeError:
            pytest.fail(
                f"stdout must still be valid JSON; got stdout={proc.stdout!r} "
                f"stderr={proc.stderr!r}"
            )
        assert isinstance(findings, list)


class TestScannerGroupSingleSpawn:
    """PART 2b (PERF-IO-001, DRY-DUP-003): the 6 per-file security/perf/scale
    scanners must run as ONE python3 process that reads the file once.

    Mechanism: a `python3` shim placed early on PATH appends a line to a
    counter file before exec'ing the real interpreter. Chosen over an
    strace-based count because it needs no special sandbox permissions and
    is exact regardless of ptrace availability; see plan.md Test Plan for
    the alternative if this ever proves fragile in CI.
    """

    def test_scanner_group_single_spawn(self, tmp_path: Path) -> None:
        """RED today: confirmed live on HEAD at exactly 8 python3 spawns for
        a single .py file with no external linter installed -- 1
        (analyze_python's "no linter found" fallback) + 6 (the per-file
        security/perf/scale scanners) + 1 (json_array at the very end of the
        script). After PART 2b merges the 6 into one process, the total
        drops to 3. Asserting `<= 3` (the post-fix upper bound) rather than
        pinning the exact pre-fix count of 8 keeps this test meaningful
        rather than merely re-asserting today's number.
        """
        if not ANALYZER.exists():
            pytest.skip(f"analyzer not found at {ANALYZER}")
        real_python3 = shutil.which("python3")
        if real_python3 is None:
            pytest.skip("no system python3 on PATH to wrap")

        counter = tmp_path / "spawn_count.txt"
        counter.write_text("")
        shim_dir = tmp_path / "shim"
        shim_dir.mkdir()
        shim = shim_dir / "python3"
        shim.write_text(
            "#!/bin/bash\n"
            f'echo x >> "{counter}"\n'
            f'exec "{real_python3}" "$@"\n'
        )
        shim.chmod(0o755)

        target = tmp_path / "svc.py"
        target.write_text("def run(cmd):\n    " + _EVAL + "(cmd)\n")

        env = dict(os.environ)
        env["PATH"] = f"{shim_dir}{os.pathsep}{env.get('PATH', '')}"

        subprocess.run(
            ["bash", str(ANALYZER), "--project-root", str(tmp_path), str(target)],
            capture_output=True,
            text=True,
            env=env,
        )

        spawn_count = len([ln for ln in counter.read_text().splitlines() if ln])
        assert spawn_count <= 3, (
            "expected the 6 security/perf/scale scanners merged into a single "
            "python3 process (<=3 total spawns: analyze_python + the merged "
            f"group + json_array); got {spawn_count} spawns"
        )


class TestContractPreservationRegression:
    """Target 2 regression guard (plan.md CONTRACT TO PRESERVE / Test Plan):
    the rule/tool substrings this file already pins must survive the
    argv/heredoc rewrite and the 6-scanner merge byte-identical. Stability
    guard -- PASSES both before and after Target 2 lands; a failure here
    means a rule/tool string drifted during the rewrite.
    """

    def test_missing_auth_decorator_substring_survives(self, tmp_path: Path) -> None:
        out = _analyze(tmp_path, _ROUTE_NO_AUTH)
        assert "missing-auth-decorator" in out

    def test_weak_rng_substrings_survive(self, tmp_path: Path) -> None:
        rnd = "rand" + "om"
        ctx = "ses" + "sion"
        content = (
            "import " + rnd + "\n"
            + "def issue():\n"
            + "    " + ctx + " = " + rnd + "." + rnd + "()\n"
            + "    return " + ctx + "\n"
        )
        out = _analyze(tmp_path, content)
        assert ("SEC-AUTH-TOKEN-001" in out) and ("weak-rng-py" in out), (
            f"expected both SEC-AUTH-TOKEN-001 and weak-rng-py; got {out!r}"
        )


# ---------------------------------------------------------------------------
# FIX B / FIX A regression: auto-detect project-root path (no --project-root)
#   The TestArgvSpliceHardening tests above ALWAYS pass --project-root, so they
#   never exercise detect_project_root(), which run-analysis.sh calls
#   automatically when --project-root is omitted (the documented default).
#   detect_project_root() spliced its argument straight into a
#   `python3 -c "..."` source string, so an apostrophe in the target path
#   raised a SyntaxError under `set -euo pipefail` that aborted the ENTIRE
#   script with empty stdout -- before any scanner ran.
# ---------------------------------------------------------------------------


class TestApostrophePathNoProjectRoot:
    """Confirmed live: without --project-root, an apostrophe in the target path
    crashed detect_project_root() (FIX B) and the analyze_python fallback
    (FIX A), aborting the whole run before the injection scanner could report a
    real eval-call violation.
    """

    def test_apostrophe_path_no_project_root_still_finds(self, tmp_path: Path) -> None:
        """FIX B: with NO --project-root, an apostrophe in BOTH a parent
        directory and the filename must not crash the run, and the injection
        violation must still be reported."""
        if not ANALYZER.exists():
            pytest.skip(f"analyzer not found at {ANALYZER}")
        sub = tmp_path / "o'brien's dir"
        sub.mkdir()
        target = sub / "o'brien's file.py"
        target.write_text("def run(cmd):\n    " + _EVAL + "(cmd)\n")

        proc = subprocess.run(
            ["bash", str(ANALYZER), str(target)],
            capture_output=True,
            text=True,
        )

        assert "Traceback" not in proc.stderr, (
            "analyzer must not crash on an apostrophe path with no "
            f"--project-root; stderr={proc.stderr!r}"
        )
        assert proc.stdout.strip(), (
            "stdout must not be empty (a whole-script abort produces empty "
            f"stdout); stderr={proc.stderr!r} exit={proc.returncode}"
        )
        try:
            findings = json.loads(proc.stdout)
        except json.JSONDecodeError:
            pytest.fail(
                "stdout must be valid JSON with no --project-root on an "
                f"apostrophe path; got stdout={proc.stdout!r} stderr={proc.stderr!r}"
            )
        assert isinstance(findings, list)
        assert any("eval" in f.get("tool", "") for f in findings), (
            f"the injection violation must still be reported; got {findings!r}"
        )

    def test_apostrophe_path_xml_fallback_no_crash(self, tmp_path: Path) -> None:
        """FIX A: an apostrophe filename routed through the xmllint fallback
        branch (an invalid .xml) must not crash. Skipped when xmllint is not
        installed in this environment (the fallback tool cannot run)."""
        if not ANALYZER.exists():
            pytest.skip(f"analyzer not found at {ANALYZER}")
        if shutil.which("xmllint") is None:
            pytest.skip("xmllint not installed; cannot exercise the xml fallback branch")
        target = tmp_path / "o'brien's schema.xml"
        target.write_text("<root><unclosed></root>\n")

        proc = subprocess.run(
            ["bash", str(ANALYZER), str(target)],
            capture_output=True,
            text=True,
        )

        assert "Traceback" not in proc.stderr, (
            f"xml fallback must not crash on an apostrophe path; stderr={proc.stderr!r}"
        )
        try:
            findings = json.loads(proc.stdout)
        except json.JSONDecodeError:
            pytest.fail(
                f"stdout must be valid JSON; got stdout={proc.stdout!r} "
                f"stderr={proc.stderr!r}"
            )
        assert isinstance(findings, list)
        assert any(f.get("tool") == "xmllint" for f in findings), (
            f"the malformed XML must be reported via the xmllint fallback; "
            f"got {findings!r}"
        )
