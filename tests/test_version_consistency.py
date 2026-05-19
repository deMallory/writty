"""Cross-cutting: version string consistency across all four manifest files.

All of pyproject.toml, SKILL.md frontmatter, .claude-plugin/marketplace.json,
and .claude-plugin/plugin.json must declare version 1.3.0.
"""

from __future__ import annotations

import json
import re
import tomllib
from pathlib import Path

import pytest

SKILL_DIR = Path("/home/lucio.saldivar/.claude/skills/writ")
EXPECTED_VERSION = "1.3.0"


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


@pytest.fixture(scope="module")
def skill_md_text() -> str:
    return (SKILL_DIR / "SKILL.md").read_text()


class TestPyprojectVersion:
    """pyproject.toml declares version 1.3.0."""

    def test_pyproject_version_is_1_3_0(self, pyproject: dict) -> None:
        """pyproject.toml [project.version] must be '1.3.0'."""
        version = pyproject.get("project", {}).get("version")
        assert version == EXPECTED_VERSION, (
            f"pyproject.toml version must be '{EXPECTED_VERSION}'; got {version!r}"
        )


class TestSkillMdVersion:
    """SKILL.md frontmatter declares version 1.3.0."""

    def test_skill_md_frontmatter_version_is_1_3_0(
        self, skill_md_text: str
    ) -> None:
        """SKILL.md YAML frontmatter 'version:' field must be '1.3.0'."""
        # Match: version: "1.3.0" or version: 1.3.0
        match = re.search(
            r'^\s*version\s*:\s*["\']?(\d+\.\d+\.\d+)["\']?',
            skill_md_text,
            re.MULTILINE,
        )
        assert match is not None, (
            "SKILL.md must have a 'version:' field in its frontmatter"
        )
        found = match.group(1)
        assert found == EXPECTED_VERSION, (
            f"SKILL.md version must be '{EXPECTED_VERSION}'; got {found!r}"
        )


class TestMarketplaceJsonVersion:
    """marketplace.json declares version 1.3.0 in both locations."""

    def test_marketplace_metadata_version_is_1_3_0(
        self, marketplace: dict
    ) -> None:
        """marketplace.json metadata.version must be '1.3.0'."""
        version = marketplace.get("metadata", {}).get("version")
        assert version == EXPECTED_VERSION, (
            f"marketplace.json metadata.version must be '{EXPECTED_VERSION}'; "
            f"got {version!r}"
        )

    def test_marketplace_plugins_version_is_1_3_0(
        self, marketplace: dict
    ) -> None:
        """marketplace.json plugins[0].version must be '1.3.0'."""
        plugins = marketplace.get("plugins", [])
        assert len(plugins) > 0, "marketplace.json must have at least one plugin entry"
        version = plugins[0].get("version")
        assert version == EXPECTED_VERSION, (
            f"marketplace.json plugins[0].version must be '{EXPECTED_VERSION}'; "
            f"got {version!r}"
        )


class TestPluginJsonVersion:
    """plugin.json declares version 1.3.0."""

    def test_plugin_json_version_is_1_3_0(self, plugin_json: dict) -> None:
        """plugin.json 'version' field must be '1.3.0'."""
        version = plugin_json.get("version")
        assert version == EXPECTED_VERSION, (
            f"plugin.json version must be '{EXPECTED_VERSION}'; got {version!r}"
        )


class TestVersionConsistencyAcrossFiles:
    """All four manifest files agree on the same version string."""

    def test_all_four_manifests_agree(
        self,
        pyproject: dict,
        marketplace: dict,
        plugin_json: dict,
        skill_md_text: str,
    ) -> None:
        """pyproject, marketplace (both fields), plugin.json, SKILL.md all say 1.3.0."""
        versions = {
            "pyproject.toml": pyproject.get("project", {}).get("version"),
            "marketplace.json:metadata.version": marketplace.get("metadata", {}).get("version"),
            "marketplace.json:plugins[0].version": (
                marketplace.get("plugins", [{}])[0].get("version")
                if marketplace.get("plugins") else None
            ),
            "plugin.json:version": plugin_json.get("version"),
        }

        skill_match = re.search(
            r'^\s*version\s*:\s*["\']?(\d+\.\d+\.\d+)["\']?',
            skill_md_text, re.MULTILINE,
        )
        versions["SKILL.md:version"] = skill_match.group(1) if skill_match else None

        wrong = {k: v for k, v in versions.items() if v != EXPECTED_VERSION}
        assert not wrong, (
            f"The following manifests do not declare version '{EXPECTED_VERSION}': "
            + ", ".join(f"{k}={v!r}" for k, v in wrong.items())
        )
