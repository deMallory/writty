"""Unit tests for bin/lib/test_paths.py.

Covers config loading (defaults + project override), the four CLI subcommands
(match-src, match-test, resolve-test, runner-for), and edge cases.

The helper is invoked two ways:
  - subprocess: tests the actual CLI surface used by the bash hooks
  - importlib: tests the loader / matcher functions directly for tighter feedback

The helper file uses an underscore (test_paths.py) so it is importable; the
plan referred to it as `test-paths.py` for CLI familiarity but Python module
naming requires the underscore form. CLI argv0 prefix is irrelevant.
"""
from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import uuid
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
HELPER_PATH = REPO / "bin" / "lib" / "test_paths.py"
DEFAULTS_PATH = REPO / "bin" / "lib" / "test-paths-defaults.json"


# ── Module loading ──────────────────────────────────────────────────────────


def _load_helper():
    """Import the helper as a fresh module each call (cwd-sensitive loader)."""
    spec = importlib.util.spec_from_file_location(
        f"_test_paths_{uuid.uuid4().hex[:6]}", HELPER_PATH
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _run_cli(*args, cwd: Path | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(HELPER_PATH), *args],
        capture_output=True, text=True, cwd=str(cwd) if cwd else None,
    )


# ── Fixtures ────────────────────────────────────────────────────────────────


@pytest.fixture
def isolated_cwd(tmp_path):
    """A temp directory with no .claude/writ.json (uses defaults)."""
    yield tmp_path


@pytest.fixture
def cwd_with_project_config(tmp_path):
    """Caller writes a .claude/writ.json then yields tmp_path."""
    (tmp_path / ".claude").mkdir()
    yield tmp_path


# ── Defaults loading ────────────────────────────────────────────────────────


def test_defaults_file_exists_and_is_valid_json():
    assert DEFAULTS_PATH.is_file(), f"missing bundled defaults at {DEFAULTS_PATH}"
    data = json.loads(DEFAULTS_PATH.read_text())
    assert "patterns" in data
    assert isinstance(data["patterns"], list)
    assert len(data["patterns"]) > 0


def test_defaults_include_python_generic_pattern():
    data = json.loads(DEFAULTS_PATH.read_text())
    names = [p["name"] for p in data["patterns"]]
    assert "python-generic" in names


def test_defaults_include_magento_pattern():
    data = json.loads(DEFAULTS_PATH.read_text())
    names = [p["name"] for p in data["patterns"]]
    assert "magento" in names


def test_defaults_include_all_six_baseline_patterns():
    data = json.loads(DEFAULTS_PATH.read_text())
    names = {p["name"] for p in data["patterns"]}
    assert {"python-generic", "js-ts-generic", "go-generic",
            "rust-generic", "php-generic", "magento"} <= names


def test_loader_returns_defaults_when_no_project_config(isolated_cwd):
    mod = _load_helper()
    config = mod.load_config(isolated_cwd)
    names = [p["name"] for p in config["patterns"]]
    assert "python-generic" in names
    assert "magento" in names


def test_loader_merges_project_config_with_defaults(cwd_with_project_config):
    (cwd_with_project_config / ".claude" / "writ.json").write_text(json.dumps({
        "patterns": [{
            "name": "custom-laravel",
            "src_match": ["*/app/Models/*.php"],
            "test_match": ["*/tests/Unit/Models/*Test.php"],
            "src_to_test_regex": r"^(.*)/app/Models/(.+)\.php$",
            "src_to_test_replace": "{1}/tests/Unit/Models/{2}Test.php",
            "runner_command": "vendor/bin/phpunit",
        }],
    }))
    mod = _load_helper()
    config = mod.load_config(cwd_with_project_config)
    names = [p["name"] for p in config["patterns"]]
    assert "custom-laravel" in names
    assert "magento" in names  # defaults still present
    assert names.index("custom-laravel") < names.index("magento"), \
        "project patterns must come first for first-match precedence"


def test_loader_replaces_defaults_when_extends_defaults_false(cwd_with_project_config):
    (cwd_with_project_config / ".claude" / "writ.json").write_text(json.dumps({
        "extends_defaults": False,
        "patterns": [{
            "name": "only-this",
            "src_match": ["*/src/*.py"],
            "test_match": ["*/tests/*.py"],
            "src_to_test_regex": r"^(.*)/src/(.+)\.py$",
            "src_to_test_replace": "{1}/tests/test_{2}.py",
            "runner_command": "pytest",
        }],
    }))
    mod = _load_helper()
    config = mod.load_config(cwd_with_project_config)
    names = [p["name"] for p in config["patterns"]]
    assert names == ["only-this"]
    assert "magento" not in names


def test_loader_handles_malformed_project_json(cwd_with_project_config):
    (cwd_with_project_config / ".claude" / "writ.json").write_text("{ not valid json")
    mod = _load_helper()
    config = mod.load_config(cwd_with_project_config)
    names = {p["name"] for p in config["patterns"]}
    assert "python-generic" in names  # fell back to defaults
    assert mod.last_load_error is not None  # error captured for telemetry


# ── match-src ──────────────────────────────────────────────────────────────


def test_match_src_python_file_returns_python_generic(isolated_cwd):
    result = _run_cli("match-src", str(isolated_cwd / "src" / "foo.py"), cwd=isolated_cwd)
    assert result.returncode == 0
    assert result.stdout.strip() == "python-generic"


def test_match_src_magento_model_returns_magento(isolated_cwd):
    p = isolated_cwd / "app" / "code" / "Foo" / "Bar" / "Model" / "Baz.php"
    result = _run_cli("match-src", str(p), cwd=isolated_cwd)
    assert result.returncode == 0
    assert result.stdout.strip() == "magento"


def test_match_src_non_matching_returns_empty(isolated_cwd):
    p = isolated_cwd / "docs" / "readme.md"
    result = _run_cli("match-src", str(p), cwd=isolated_cwd)
    assert result.returncode == 0
    assert result.stdout.strip() == ""


def test_match_src_magento_etc_xml_does_not_match(isolated_cwd):
    p = isolated_cwd / "app" / "code" / "Foo" / "Bar" / "etc" / "config.xml"
    result = _run_cli("match-src", str(p), cwd=isolated_cwd)
    assert result.returncode == 0
    assert result.stdout.strip() == ""


def test_match_src_go_file_returns_go_generic(isolated_cwd):
    p = isolated_cwd / "pkg" / "thing.go"
    result = _run_cli("match-src", str(p), cwd=isolated_cwd)
    assert result.returncode == 0
    # go-generic matches any *.go EXCEPT *_test.go
    assert result.stdout.strip() == "go-generic"


def test_match_src_go_test_file_does_not_match_as_src(isolated_cwd):
    p = isolated_cwd / "pkg" / "thing_test.go"
    result = _run_cli("match-src", str(p), cwd=isolated_cwd)
    # _test.go is a test, not a src; match-src should return empty
    assert result.stdout.strip() == ""


# ── match-test ─────────────────────────────────────────────────────────────


def test_match_test_python_test_file(isolated_cwd):
    p = isolated_cwd / "tests" / "test_foo.py"
    result = _run_cli("match-test", str(p), cwd=isolated_cwd)
    assert result.stdout.strip() == "python-generic"


def test_match_test_magento_test_file(isolated_cwd):
    p = isolated_cwd / "app" / "code" / "Foo" / "Bar" / "Test" / "Unit" / "Model" / "BazTest.php"
    result = _run_cli("match-test", str(p), cwd=isolated_cwd)
    assert result.stdout.strip() == "magento"


def test_match_test_src_file_is_not_a_test(isolated_cwd):
    p = isolated_cwd / "src" / "foo.py"
    result = _run_cli("match-test", str(p), cwd=isolated_cwd)
    assert result.stdout.strip() == ""


def test_match_test_go_test_file_returns_go_generic(isolated_cwd):
    p = isolated_cwd / "pkg" / "thing_test.go"
    result = _run_cli("match-test", str(p), cwd=isolated_cwd)
    assert result.stdout.strip() == "go-generic"


# ── resolve-test ───────────────────────────────────────────────────────────


def test_resolve_test_python_generic(isolated_cwd):
    (isolated_cwd / "src").mkdir()
    (isolated_cwd / "tests").mkdir()
    src = isolated_cwd / "src" / "foo.py"
    src.write_text("def f(): pass\n")
    expected_test = isolated_cwd / "tests" / "test_foo.py"
    expected_test.write_text("def test_f(): pass\n")

    result = _run_cli("resolve-test", str(src), cwd=isolated_cwd)
    assert result.returncode == 0
    assert result.stdout.strip() == str(expected_test)


def test_resolve_test_magento_nested_path(isolated_cwd):
    src = isolated_cwd / "app" / "code" / "Foo" / "Bar" / "Model" / "ResourceModel" / "Baz.php"
    src.parent.mkdir(parents=True)
    src.write_text("<?php class Baz {}\n")
    test_path = isolated_cwd / "app" / "code" / "Foo" / "Bar" / "Test" / "Unit" / "Model" / "ResourceModel" / "BazTest.php"
    test_path.parent.mkdir(parents=True)
    test_path.write_text("<?php\n")

    result = _run_cli("resolve-test", str(src), cwd=isolated_cwd)
    assert result.returncode == 0
    assert result.stdout.strip() == str(test_path)


def test_resolve_test_returns_empty_when_test_file_missing(isolated_cwd):
    (isolated_cwd / "src").mkdir()
    src = isolated_cwd / "src" / "foo.py"
    src.write_text("def f(): pass\n")
    # No test file created.

    result = _run_cli("resolve-test", str(src), cwd=isolated_cwd)
    assert result.returncode == 0
    assert result.stdout.strip() == ""


def test_resolve_test_returns_empty_for_unmatched_path(isolated_cwd):
    p = isolated_cwd / "docs" / "readme.md"
    result = _run_cli("resolve-test", str(p), cwd=isolated_cwd)
    assert result.stdout.strip() == ""


def test_resolve_test_when_input_is_already_a_test_returns_input(isolated_cwd):
    """Passing a test path through resolve-test should echo it back (idempotent)."""
    (isolated_cwd / "tests").mkdir()
    test_file = isolated_cwd / "tests" / "test_foo.py"
    test_file.write_text("def test_x(): pass\n")
    result = _run_cli("resolve-test", str(test_file), cwd=isolated_cwd)
    assert result.stdout.strip() == str(test_file)


# ── runner-for ─────────────────────────────────────────────────────────────


def test_runner_for_python_test_returns_pytest(isolated_cwd):
    p = isolated_cwd / "tests" / "test_foo.py"
    result = _run_cli("runner-for", str(p), cwd=isolated_cwd)
    assert result.returncode == 0
    lines = result.stdout.split("\n")
    assert "pytest" in lines[0]
    # No config file expected for generic Python
    assert lines[1].strip() == ""


def test_runner_for_magento_with_config_file_present(isolated_cwd):
    cfg = isolated_cwd / "dev" / "tests" / "unit" / "phpunit.xml.dist"
    cfg.parent.mkdir(parents=True)
    cfg.write_text("<phpunit/>\n")
    test_file = isolated_cwd / "app" / "code" / "Foo" / "Bar" / "Test" / "Unit" / "BazTest.php"
    test_file.parent.mkdir(parents=True)
    test_file.write_text("<?php\n")

    result = _run_cli("runner-for", str(test_file), cwd=isolated_cwd)
    lines = result.stdout.split("\n")
    assert "phpunit" in lines[0]
    assert lines[1].strip().endswith("dev/tests/unit/phpunit.xml.dist")


def test_runner_for_magento_without_config_file_returns_empty_config(isolated_cwd):
    test_file = isolated_cwd / "app" / "code" / "Foo" / "Bar" / "Test" / "Unit" / "BazTest.php"
    test_file.parent.mkdir(parents=True)
    test_file.write_text("<?php\n")
    # No dev/tests/unit/phpunit.xml.dist created.

    result = _run_cli("runner-for", str(test_file), cwd=isolated_cwd)
    lines = result.stdout.split("\n")
    assert "phpunit" in lines[0]
    assert lines[1].strip() == ""


def test_runner_for_unmatched_path_returns_empty(isolated_cwd):
    p = isolated_cwd / "docs" / "readme.md"
    result = _run_cli("runner-for", str(p), cwd=isolated_cwd)
    assert result.stdout.strip() == ""


# ── First-match-wins ───────────────────────────────────────────────────────


def test_first_match_wins_with_project_pattern_overriding_default(cwd_with_project_config):
    """A project pattern named the same as a default should shadow it."""
    (cwd_with_project_config / ".claude" / "writ.json").write_text(json.dumps({
        "patterns": [{
            "name": "python-generic",
            "src_match": ["*/lib/*.py"],
            "test_match": ["*/spec/*_spec.py"],
            "src_to_test_regex": r"^(.*)/lib/(.+)\.py$",
            "src_to_test_replace": "{1}/spec/{2}_spec.py",
            "runner_command": "pytest --custom-flag",
        }],
    }))
    # A file under src/ should NOT match python-generic now (project's overrides it).
    # But it might still match the default php-generic? No -- python-generic's src_match
    # is now */lib/*.py per the project override. Files under src/ won't match it.
    result = _run_cli("match-src",
                      str(cwd_with_project_config / "src" / "foo.py"),
                      cwd=cwd_with_project_config)
    assert result.stdout.strip() == ""  # no longer matched

    result = _run_cli("match-src",
                      str(cwd_with_project_config / "lib" / "foo.py"),
                      cwd=cwd_with_project_config)
    assert result.stdout.strip() == "python-generic"
