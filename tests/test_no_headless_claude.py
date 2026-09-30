"""No Writ workflow may run headless Claude Code (`claude -p` / `claude --print`).

The efficacy A/B harness was the only headless user and has been removed end to end.
This file scans writ/, hooks/, bin/ and scripts/ so a headless invocation cannot return,
and pins the removal itself (module specs, fixtures, runbook, CLI command).

`claude plugin list --json` is a plugin-inventory query, not headless session work, and
is allowed by construction: it carries no `-p` / `--print` token.
"""
from __future__ import annotations

import importlib.util
import re
from pathlib import Path

from typer.testing import CliRunner

from writ.cli import app

REPO = Path(__file__).resolve().parent.parent
SCAN_ROOTS = ("writ", "hooks", "bin", "scripts")
HEADLESS_FLAGS = {"-p", "--print"}

# Python argv list whose program is "claude": ["claude", ... ]
_ARGV_LIST = re.compile(r"""\[\s*(?:"claude"|'claude')\s*,([^\]]*)\]""")
_ARGV_ELEMENT = re.compile(r"""["']([^"']*)["']""")
# Shell command word `claude`, then the rest of the simple command.
_SHELL_CLAUDE = re.compile(r"(?<![\w./-])claude(?![\w./-])([^;&|\n)]*)")


def find_headless_invocations(text: str) -> list[str]:
    """Return a description of every headless `claude` invocation found in text."""
    hits: list[str] = []
    for m in _ARGV_LIST.finditer(text):
        elements = set(_ARGV_ELEMENT.findall(m.group(1)))
        if elements & HEADLESS_FLAGS:
            hits.append(f"argv: {m.group(0)[:80]!r}")
    for m in _SHELL_CLAUDE.finditer(text):
        if set(m.group(1).split()) & HEADLESS_FLAGS:
            hits.append(f"shell: {m.group(0)[:80]!r}")
    return hits


def scanned_files() -> list[Path]:
    files: list[Path] = []
    for root in SCAN_ROOTS:
        base = REPO / root
        if not base.is_dir():
            continue
        for path in sorted(base.rglob("*")):
            if "__pycache__" in path.parts or not path.is_file():
                continue
            files.append(path)
    return files


def _read_text(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        return None


class TestSourceScan:
    def test_no_file_invokes_headless_claude(self):
        offenders: dict[str, list[str]] = {}
        for path in scanned_files():
            text = _read_text(path)
            if text is None:
                continue
            hits = find_headless_invocations(text)
            if hits:
                offenders[str(path.relative_to(REPO))] = hits
        assert offenders == {}, f"headless claude invocation found: {offenders}"

    def test_scanned_population_is_non_empty(self):
        assert len(scanned_files()) > 0

    def test_scanned_population_includes_known_claude_call_sites(self):
        rel = {str(p.relative_to(REPO)) for p in scanned_files()}
        assert "writ/session/doctor.py" in rel
        assert "bin/lib/writ_install.py" in rel

    def test_known_plugin_list_call_sites_are_not_flagged(self):
        for name in ("writ/session/doctor.py", "bin/lib/writ_install.py"):
            text = (REPO / name).read_text(encoding="utf-8")
            assert "claude" in text
            assert find_headless_invocations(text) == [], name


class TestScannerControls:
    def test_flags_python_argv_dash_p(self):
        assert find_headless_invocations('subprocess.run(["claude", "-p", prompt])')

    def test_flags_python_argv_flag_before_dash_p(self):
        assert find_headless_invocations('cmd = ["claude", "--output-format", "json", "-p"]')

    def test_flags_shell_dash_p(self):
        assert find_headless_invocations('claude -p "x"')

    def test_flags_shell_print(self):
        assert find_headless_invocations("claude --print --output-format json")

    def test_flags_command_substitution(self):
        assert find_headless_invocations("x=$(claude -p hi)")

    def test_allows_python_argv_plugin_list(self):
        assert find_headless_invocations('["claude", "plugin", "list", "--json"]') == []

    def test_allows_shell_plugin_list(self):
        assert find_headless_invocations("claude plugin list --json") == []

    def test_allows_unrelated_mkdir_dash_p_before_claude(self):
        assert find_headless_invocations("mkdir -p d && claude plugin list") == []


class TestHarnessRemoved:
    def test_efficacy_ab_module_is_gone(self):
        assert importlib.util.find_spec("writ.analysis.efficacy_ab") is None

    def test_variants_module_is_gone(self):
        assert importlib.util.find_spec("writ.analysis.variants") is None

    def test_efficacy_suite_fixtures_are_gone(self):
        assert not (REPO / "tests" / "efficacy_suite").exists()

    def test_efficacy_ab_runbook_is_gone(self):
        assert not (REPO / "docs" / "reference" / "efficacy-ab.md").exists()

    def test_efficacy_ab_is_not_a_registered_command(self):
        result = CliRunner().invoke(app, ["efficacy-ab", "x"])
        assert result.exit_code != 0
        assert "No such command" in result.output

    def test_token_audit_command_still_registered(self):
        result = CliRunner().invoke(app, ["token-audit", "--help"])
        assert result.exit_code == 0
