"""Cross-cutting: version string consistency across all three manifest files.

All of pyproject.toml, .claude-plugin/marketplace.json, and
.claude-plugin/plugin.json must declare version 1.5.0. SKILL.md no longer
participates (deleted in v1.5.0).
"""

from __future__ import annotations

import json
import re
import tomllib
from pathlib import Path

import pytest

SKILL_DIR = Path("/home/lucio.saldivar/.claude/skills/writ")
EXPECTED_VERSION = "1.5.0"


@pytest.fixture(scope="module")
def pyproject() -> dict:
    with (SKILL_DIR / "pyproject.toml").open("rb") as f:
        return tomllib.load(f)


@pytest.fixture(scope="module")
def marketplace() -> dict:
    with (SKILL_DIR / ".claude-plugin" / "marketplace.json").open() as f:
        return json.load(f)


@pytest.fixture(scope="module")
def plugin_json() -> dict:
    with (SKILL_DIR / ".claude-plugin" / "plugin.json").open() as f:
        return json.load(f)


class TestPyprojectVersion:
    """pyproject.toml declares version 1.5.0."""

    def test_pyproject_version_is_1_4_0(self, pyproject: dict) -> None:
        """pyproject.toml [project.version] must be '1.5.0'."""
        version = pyproject.get("project", {}).get("version")
        assert version == EXPECTED_VERSION, (
            f"pyproject.toml version must be '{EXPECTED_VERSION}'; got {version!r}"
        )


class TestMarketplaceJsonVersion:
    """marketplace.json declares version 1.5.0 in both locations."""

    def test_marketplace_metadata_version_is_1_4_0(
        self, marketplace: dict
    ) -> None:
        """marketplace.json metadata.version must be '1.5.0'."""
        version = marketplace.get("metadata", {}).get("version")
        assert version == EXPECTED_VERSION, (
            f"marketplace.json metadata.version must be '{EXPECTED_VERSION}'; "
            f"got {version!r}"
        )

    def test_marketplace_plugins_version_is_1_4_0(
        self, marketplace: dict
    ) -> None:
        """marketplace.json plugins[0].version must be '1.5.0'."""
        plugins = marketplace.get("plugins", [])
        assert len(plugins) > 0, "marketplace.json must have at least one plugin entry"
        version = plugins[0].get("version")
        assert version == EXPECTED_VERSION, (
            f"marketplace.json plugins[0].version must be '{EXPECTED_VERSION}'; "
            f"got {version!r}"
        )


class TestPluginJsonVersion:
    """plugin.json declares version 1.5.0."""

    def test_plugin_json_version_is_1_4_0(self, plugin_json: dict) -> None:
        """plugin.json 'version' field must be '1.5.0'."""
        version = plugin_json.get("version")
        assert version == EXPECTED_VERSION, (
            f"plugin.json version must be '{EXPECTED_VERSION}'; got {version!r}"
        )


class TestVersionConsistencyAcrossFiles:
    """All three manifest files agree on the same version string."""

    def test_all_three_manifests_agree(
        self,
        pyproject: dict,
        marketplace: dict,
        plugin_json: dict,
    ) -> None:
        """pyproject, marketplace (both fields), and plugin.json all say 1.5.0."""
        versions = {
            "pyproject.toml": pyproject.get("project", {}).get("version"),
            "marketplace.json:metadata.version": marketplace.get("metadata", {}).get("version"),
            "marketplace.json:plugins[0].version": (
                marketplace.get("plugins", [{}])[0].get("version")
                if marketplace.get("plugins") else None
            ),
            "plugin.json:version": plugin_json.get("version"),
        }

        wrong = {k: v for k, v in versions.items() if v != EXPECTED_VERSION}
        assert not wrong, (
            f"The following manifests do not declare version '{EXPECTED_VERSION}': "
            + ", ".join(f"{k}={v!r}" for k, v in wrong.items())
        )
