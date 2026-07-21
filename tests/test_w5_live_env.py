"""RED guard for Wave-5 Cycle 5.2 -- live-environment coupling + hardcoded-path
portability defects (test suite).

Cycle 5.2 removes two defect classes from the test suite:

- Group A: three test modules hardcode `SERVER = "http://localhost:8765"`,
  bypassing the suite's test-port isolation (`tests/conftest.py` pins
  `WRIT_PORT=8799`) and silently targeting the operator's live interactive
  daemon instead. The fix routes each through the canonical
  `tests._daemon._port()` helper (`from tests._daemon import _port` +
  `SERVER = f"http://localhost:{_port()}"`), mirroring the existing pattern
  in `tests/test_pol5a_statusline.py`.
- Group B: `tests/test_validate_rules.py` writes/passes hardcoded `/tmp/*.php`
  paths instead of the pytest `tmp_path` fixture, leaking uncleaned files
  across runs. `tests/test_pol5a_statusline.py` and
  `tests/test_pol5c_removal.py` read the OPERATOR's real
  `~/.claude/settings.json` unconditionally (crashing when absent) and derive
  their repo-root `SKILL_DIR` from `Path.home()` (machine-specific). The fix
  is a `skipif(not GLOBAL_SETTINGS.exists())` guard (NOT a synthetic
  monkeypatched file, which would make the live-install assertion vacuous)
  plus a `Path(__file__)`-relative `SKILL_DIR`.
- Group C: `tests/plugin/conftest.py`'s `REPO_ROOT` and
  `tests/test_methodology_ingest.py`'s `bible_dir` bake this machine's
  absolute home path in, defeating portability (and, worse, silently
  skipping the dual-location-dedup invariant off this machine). The fix
  resolves both via `Path(__file__).resolve()` hops to the checkout root.

INTENTIONAL EXCEPTION / over-correction guard: `tests/test_advance_phase_token_gate.py`
also hardcodes `localhost:8765`, but with a documented comment stating it is
a security-integration test of the DEPLOYED daemon and deliberately targets
:8765. It is NOT in the 5.2 Files list and must stay untouched; this guard
asserts it STILL contains the literal (GREEN now and after every other fix
lands).

This guard is FULLY HERMETIC: it is a pure source-text scan. It does NOT
import, execute, or collect fixtures from any target file, does NOT touch a
daemon or Neo4j, and does NOT read the operator's real
`~/.claude/settings.json` (it only source-scans the TEST files that
reference that path).

RED today (2026-07-16, pre-implementation):
- test_phase_advance_unified.py, test_phase6_promote_route_token.py,
  test_advance_populates_gates_approved.py each still hardcode
  `localhost:8765` and contain no `_port` reference -> both asserts in
  `_assert_uses_port_helper` fail.
- test_validate_rules.py still contains `/tmp/` literals and no `tmp_path`
  reference -> both asserts fail.
- test_pol5a_statusline.py and test_pol5c_removal.py contain no
  `GLOBAL_SETTINGS.exists()` skip guard, and their `SKILL_DIR` assignment
  lines use `Path.home()` (not `__file__`) -> all four asserts fail.
- tests/plugin/conftest.py's `REPO_ROOT` line uses `Path.home()` (not
  `__file__`) -> both asserts fail.
- test_methodology_ingest.py still contains a hardcoded
  `/home/<username>` path -> assert fails.

GREEN only once each corresponding fix in plan.md Cycle 5.2 lands.

The one exception is `test_advance_phase_token_gate_keeps_documented_8765`,
which is a survivor / over-correction guard: it passes today and must keep
passing after every other fix in this file lands, since that file is
deliberately excluded from the port-helper migration.
"""

from __future__ import annotations

import re
from pathlib import Path

TESTS_DIR = Path(__file__).resolve().parent


def _read(filename: str) -> str:
    """Read `filename`'s source text relative to this tests/ dir.

    Never imports or executes the file -- pure text read, so this guard
    cannot itself touch a daemon, Neo4j, or the operator's settings.json.
    """
    path = TESTS_DIR / filename
    assert path.exists(), f"expected {path} to exist"
    return path.read_text()


# ---------------------------------------------------------------------------
# Group A -- hardcoded interactive-daemon port 8765 routed through _port()
# ---------------------------------------------------------------------------


def _assert_uses_port_helper(filename: str) -> None:
    src = _read(filename)
    assert "localhost:8765" not in src, (
        f"{filename} must not hardcode the interactive-daemon literal "
        "'localhost:8765'; it must route through tests._daemon._port() so "
        "the test targets the isolated test-port daemon (WRIT_PORT=8799 per "
        "tests/conftest.py), not the operator's live :8765 singleton"
    )
    assert "_port" in src, (
        f"{filename} must import and use `_port` from tests._daemon "
        '(`from tests._daemon import _port` + '
        '`SERVER = f"http://localhost:{_port()}"`) to resolve SERVER'
    )


def test_phase_advance_unified_uses_port_helper() -> None:
    """tests/test_phase_advance_unified.py's SERVER must resolve via _port()."""
    _assert_uses_port_helper("test_phase_advance_unified.py")


def test_phase6_promote_route_token_uses_port_helper() -> None:
    """tests/test_phase6_promote_route_token.py's SERVER must resolve via _port()."""
    _assert_uses_port_helper("test_phase6_promote_route_token.py")


def test_advance_populates_gates_approved_uses_port_helper() -> None:
    """tests/test_advance_populates_gates_approved.py's SERVER must resolve via _port()."""
    _assert_uses_port_helper("test_advance_populates_gates_approved.py")


def test_advance_phase_token_gate_keeps_documented_8765() -> None:
    """Survivor / over-correction guard -- GREEN now AND after this cycle.

    tests/test_advance_phase_token_gate.py deliberately targets the DEPLOYED
    :8765 daemon (documented security-integration comment ~:27-30) and is NOT
    in the 5.2 Files list. This guard fails loud if a future sweep
    over-corrects it onto the _port() helper alongside the three real fixes.
    """
    src = _read("test_advance_phase_token_gate.py")
    assert "localhost:8765" in src, (
        "test_advance_phase_token_gate.py must still hardcode "
        "'localhost:8765' -- it is a documented security-integration test of "
        "the deployed daemon and is intentionally excluded from the 5.2 "
        "port-helper migration; this is an over-correction guard"
    )


# ---------------------------------------------------------------------------
# Group B -- real-environment reads (tmp_path isolation; skipif live-install)
# ---------------------------------------------------------------------------


def test_validate_rules_uses_tmp_path() -> None:
    """tests/test_validate_rules.py must adopt tmp_path, dropping /tmp/ literals."""
    src = _read("test_validate_rules.py")
    assert "/tmp/" not in src, (
        "test_validate_rules.py must no longer hardcode /tmp/*.php path "
        "literals; throwaway .php paths must come from the pytest tmp_path "
        "fixture so each test gets an isolated, auto-cleaned directory "
        "instead of leaking files into the shared /tmp"
    )
    assert "tmp_path" in src, (
        "test_validate_rules.py must adopt the pytest `tmp_path` fixture for "
        "its throwaway .php file paths/writes"
    )


_SKIPIF_GLOBAL_SETTINGS_RE = re.compile(r"GLOBAL_SETTINGS\.exists\(\)")


def _assert_skipif_guard_present(filename: str, src: str) -> None:
    assert _SKIPIF_GLOBAL_SETTINGS_RE.search(src) is not None, (
        f"{filename} must guard its GLOBAL_SETTINGS-reading tests with "
        "pytest.mark.skipif(not GLOBAL_SETTINGS.exists(), ...) so they skip "
        "(rather than crash via _load_settings's open()) when the "
        "operator's real settings.json is absent"
    )


def _assert_skill_dir_is_file_relative(filename: str, src: str) -> None:
    """Isolate the SKILL_DIR assignment LINE and assert on it only.

    GLOBAL_SETTINGS legitimately keeps Path.home() elsewhere in these files
    (it intentionally points at the operator's real settings file), so the
    "no Path.home()" requirement must be scoped to the SKILL_DIR line, not
    asserted against the whole file.
    """
    match = re.search(r"^\s*SKILL_DIR\s*=.*$", src, re.M)
    assert match is not None, (
        f"{filename} must define a `SKILL_DIR = ...` assignment line"
    )
    line = match.group(0)
    assert "__file__" in line, (
        f"{filename}'s SKILL_DIR assignment line must be derived from "
        f"Path(__file__) for portability across machines/checkouts; found: {line!r}"
    )
    assert "Path.home()" not in line, (
        f"{filename}'s SKILL_DIR assignment line must not use Path.home() "
        f"(a machine-specific repo-root hardcode); found: {line!r}"
    )


def test_pol5a_statusline_guards_and_relativizes() -> None:
    """test_pol5a_statusline.py: skipif guard on GLOBAL_SETTINGS.exists()
    plus a __file__-relative SKILL_DIR (GLOBAL_SETTINGS itself keeps
    Path.home() -- it is intentionally the operator's real file).
    """
    src = _read("test_pol5a_statusline.py")
    _assert_skipif_guard_present("test_pol5a_statusline.py", src)
    _assert_skill_dir_is_file_relative("test_pol5a_statusline.py", src)


def test_pol5c_removal_guards_and_relativizes() -> None:
    """test_pol5c_removal.py: skipif guard on GLOBAL_SETTINGS.exists()
    (repo-file PLUGIN_HOOKS assertions stay unconditional) plus a
    __file__-relative SKILL_DIR.
    """
    src = _read("test_pol5c_removal.py")
    _assert_skipif_guard_present("test_pol5c_removal.py", src)
    _assert_skill_dir_is_file_relative("test_pol5c_removal.py", src)


# ---------------------------------------------------------------------------
# Group C -- portability (hardcoded absolute paths to __file__-relative)
# ---------------------------------------------------------------------------


def test_plugin_conftest_repo_root_relative() -> None:
    """tests/plugin/conftest.py's REPO_ROOT must resolve via __file__, not
    Path.home(), so the fresh-install portability suite works on any machine.
    """
    src = _read("plugin/conftest.py")
    match = re.search(r"^\s*REPO_ROOT\s*=.*$", src, re.M)
    assert match is not None, (
        "tests/plugin/conftest.py must define a `REPO_ROOT = ...` assignment line"
    )
    line = match.group(0)
    assert "__file__" in line, (
        "tests/plugin/conftest.py's REPO_ROOT assignment line must be "
        f"derived from Path(__file__) for portability; found: {line!r}"
    )
    assert "Path.home()" not in line, (
        "tests/plugin/conftest.py's REPO_ROOT assignment line must not use "
        f"Path.home() (machine-specific); found: {line!r}"
    )


def test_methodology_ingest_bible_dir_relative() -> None:
    """tests/test_methodology_ingest.py must not bake any machine's
    username-specific absolute path into bible_dir; it must resolve via
    Path(__file__).resolve().parent.parent / "bible" so the
    dual-location-dedup invariant runs on any checkout instead of silently
    skipping off this machine.
    """
    src = _read("test_methodology_ingest.py")
    assert re.search(r"/home/[^/\s\"']+/", src) is None, (
        "test_methodology_ingest.py must not hardcode a username-baked "
        "absolute path; bible_dir must resolve via "
        'Path(__file__).resolve().parent.parent / "bible" so the '
        "dual-location-dedup invariant runs on any checkout"
    )
