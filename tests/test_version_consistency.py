"""Cross-cutting: version string consistency across pyproject.toml and plugin.json.

Both must declare the same version. marketplace.json was removed when the
project moved to private distribution; SKILL.md was removed in v1.5.0.
"""

from __future__ import annotations

import json
import tomllib
from pathlib import Path

import pytest

SKILL_DIR = (Path.home() / ".claude/skills/writ")
EXPECTED_VERSION = "1.5.0"


@pytest.fixture(scope="module")
def pyproject() -> dict:
    with (SKILL_DIR / "pyproject.toml").open("rb") as f:
        return tomllib.load(f)


@pytest.fixture(scope="module")
def plugin_json() -> dict:
    with (SKILL_DIR / ".claude-plugin" / "plugin.json").open() as f:
        return json.load(f)


class TestPyprojectVersion:
    def test_pyproject_version_matches_expected(self, pyproject: dict) -> None:
        version = pyproject.get("project", {}).get("version")
        assert version == EXPECTED_VERSION, (
            f"pyproject.toml version must be '{EXPECTED_VERSION}'; got {version!r}"
        )


class TestPluginJsonVersion:
    def test_plugin_json_version_matches_expected(self, plugin_json: dict) -> None:
        version = plugin_json.get("version")
        assert version == EXPECTED_VERSION, (
            f"plugin.json version must be '{EXPECTED_VERSION}'; got {version!r}"
        )


class TestVersionConsistencyAcrossFiles:
    def test_both_manifests_agree(
        self,
        pyproject: dict,
        plugin_json: dict,
    ) -> None:
        versions = {
            "pyproject.toml": pyproject.get("project", {}).get("version"),
            "plugin.json:version": plugin_json.get("version"),
        }
        wrong = {k: v for k, v in versions.items() if v != EXPECTED_VERSION}
        assert not wrong, (
            f"The following manifests do not declare version '{EXPECTED_VERSION}': "
            + ", ".join(f"{k}={v!r}" for k, v in wrong.items())
        )
