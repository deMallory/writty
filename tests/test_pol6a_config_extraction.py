"""Tests for POL-6a: god-module split phase 1 -- writ/session/ package + facade (config layer).

POL-6 moves bin/lib/writ-session.py's implementation into a writ/session/* package while
the file itself becomes a thin facade that re-exports the surface and keeps main(). 6a proves
the package + facade + sys.path bootstrap + transparent re-export pattern on the lowest-risk
content: the budget/cost constant block. The constants must keep resolving for the 68 path
loaders (tests) and the server, which reads DEFAULT_SESSION_BUDGET off the loaded module.

Per TEST-TDD-001: skeletons approved before implementation.
"""

from __future__ import annotations

import importlib
import importlib.util
import json
import os
import subprocess
import sys

import pytest

SKILL_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
FACADE_PATH = os.path.join(SKILL_ROOT, "bin", "lib", "writ-session.py")
INIT_PATH = os.path.join(SKILL_ROOT, "writ", "session", "__init__.py")
CONFIG_PATH = os.path.join(SKILL_ROOT, "writ", "session", "config.py")
BUDGET_JSON_PATH = os.path.join(SKILL_ROOT, "writ", "shared", "budget.json")

# const-on-the-module -> key-in-budget.json
BUDGET_CONSTANTS = {
    "DEFAULT_SESSION_BUDGET": "default_budget",
    "APPROX_TOKENS_PER_RULE_FULL": "rule_cost_full",
    "APPROX_TOKENS_PER_RULE_STANDARD": "rule_cost_standard",
    "APPROX_TOKENS_PER_RULE_SUMMARY": "rule_cost_summary",
    "DEFAULT_ALWAYS_ON_CAP": "always_on_cap",
}


def _load_facade():
    """Load the facade the way the server and the 68 test loaders do."""
    spec = importlib.util.spec_from_file_location("writ_session_pol6a", FACADE_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _load_config_module():
    if SKILL_ROOT not in sys.path:
        sys.path.insert(0, SKILL_ROOT)
    return importlib.import_module("writ.session.config")


def _load_budget_json():
    with open(BUDGET_JSON_PATH) as f:
        return json.load(f)


class TestPackageFilesExist:
    """6a creates the new subpackage as plain files on disk."""

    def test_session_init_exists(self):
        assert os.path.isfile(INIT_PATH)

    def test_session_config_exists(self):
        assert os.path.isfile(CONFIG_PATH)


class TestConfigModuleImportable:
    """writ.session.config imports as a real package and exposes the 5 budget constants
    with values drawn from the canonical writ/shared/budget.json."""

    def test_imports_as_package(self):
        mod = _load_config_module()
        assert mod is not None

    @pytest.mark.parametrize("const_name", list(BUDGET_CONSTANTS))
    def test_exposes_constant(self, const_name):
        mod = _load_config_module()
        assert hasattr(mod, const_name)

    @pytest.mark.parametrize("const_name,json_key", list(BUDGET_CONSTANTS.items()))
    def test_constant_equals_budget_json(self, const_name, json_key):
        mod = _load_config_module()
        budget = _load_budget_json()
        assert getattr(mod, const_name) == budget[json_key]


class TestFacadeReExports:
    """The facade re-exports all 5 constants; values equal the config module's
    (proves transparent re-export -- inline functions and external mod.<name> access resolve)."""

    @pytest.mark.parametrize("const_name", list(BUDGET_CONSTANTS))
    def test_facade_has_constant(self, const_name):
        facade = _load_facade()
        assert hasattr(facade, const_name)

    @pytest.mark.parametrize("const_name", list(BUDGET_CONSTANTS))
    def test_facade_value_matches_config(self, const_name):
        config = _load_config_module()
        facade = _load_facade()
        assert getattr(facade, const_name) == getattr(config, const_name)


class TestFacadeCLIStillRuns:
    """The sys.path bootstrap must work when the file is loaded as a script by absolute
    path (the hook invocation), not only via spec_from_file_location."""

    def test_read_subcommand_exits_zero(self, tmp_path):
        env = dict(os.environ, WRIT_CACHE_DIR=str(tmp_path))
        result = subprocess.run(
            [sys.executable, FACADE_PATH, "read", "pol6a-cli-smoke"],
            capture_output=True,
            text=True,
            env=env,
        )
        assert result.returncode == 0, result.stderr


class TestSourceShape:
    """The budget block left the facade and lives in config.py."""

    def test_facade_no_longer_defines_budget_inline(self):
        with open(FACADE_PATH) as f:
            src = f.read()
        assert "DEFAULT_SESSION_BUDGET =" not in src

    def test_facade_imports_from_config(self):
        with open(FACADE_PATH) as f:
            src = f.read()
        assert "from writ.session.config import" in src

    def test_config_defines_budget_inline(self):
        with open(CONFIG_PATH) as f:
            src = f.read()
        assert "DEFAULT_SESSION_BUDGET =" in src
