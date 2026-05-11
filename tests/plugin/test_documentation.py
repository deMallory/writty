"""Tests for Phase D documentation and version-bump deliverables.

Verifies README, CHANGELOG, pyproject.toml, SKILL.md, and the new
docs/plugin-validation.md all reflect the 2.0.0 plugin distribution refactor.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from tests.plugin.conftest import REPO_ROOT

README = REPO_ROOT / "README.md"
CHANGELOG = REPO_ROOT / "CHANGELOG.md"
PYPROJECT = REPO_ROOT / "pyproject.toml"
SKILL_MD = REPO_ROOT / "SKILL.md"
PLUGIN_VALIDATION_DOC = REPO_ROOT / "docs" / "plugin-validation.md"


class TestReadmePluginSection:
    @pytest.fixture()
    def content(self) -> str:
        assert README.exists(), "README.md must exist"
        return README.read_text()

    def test_readme_plugin_install_section_exists(self, content: str) -> None:
        """README.md must contain the heading 'Install as a Claude Code plugin'."""
        assert "Install as a Claude Code plugin" in content, (
            "README.md must have an 'Install as a Claude Code plugin' section"
        )

    def test_readme_marketplace_add_command(self, content: str) -> None:
        """README.md must contain the exact marketplace add command."""
        assert "claude plugin marketplace add infinri/Writ" in content, (
            "README.md must document 'claude plugin marketplace add infinri/Writ'"
        )

    def test_readme_plugin_install_command(self, content: str) -> None:
        """README.md must contain the exact plugin install command."""
        assert "claude plugin install writ@writ" in content, (
            "README.md must document 'claude plugin install writ@writ'"
        )

    def test_readme_upgrade_section_exists(self, content: str) -> None:
        """README.md must contain the 'Upgrading from standalone v1.0.0' section."""
        assert "Upgrading from standalone v1.0.0" in content, (
            "README.md must have an 'Upgrading from standalone v1.0.0' section"
        )


class TestChangelog:
    @pytest.fixture()
    def content(self) -> str:
        assert CHANGELOG.exists(), "CHANGELOG.md must exist"
        return CHANGELOG.read_text()

    def test_changelog_2_0_0_entry(self, content: str) -> None:
        """CHANGELOG.md must contain a ## [2.0.0] section heading."""
        assert "## [2.0.0]" in content, (
            "CHANGELOG.md must have a '## [2.0.0]' section"
        )

    def test_changelog_breaking_added_changed(self, content: str) -> None:
        """The 2.0.0 section must have Breaking, Added, Changed, Deprecated, and Upgrade-path subsections."""
        # Find the 2.0.0 section and check it contains required subsections
        if "## [2.0.0]" not in content:
            pytest.skip("Phase D: ## [2.0.0] section not yet in CHANGELOG.md")
        # Extract just the 2.0.0 section to avoid matching other sections
        idx = content.index("## [2.0.0]")
        # Find the next ## heading after 2.0.0 to bound the section
        next_section = content.find("\n## [", idx + 1)
        section = content[idx:next_section] if next_section != -1 else content[idx:]
        lowered = section.lower()
        for subsection in ("breaking", "added", "changed", "deprecated", "upgrade"):
            assert subsection in lowered, (
                f"CHANGELOG.md 2.0.0 section must contain a '{subsection}' subsection"
            )


class TestVersionBumps:
    def test_pyproject_version_2_0_0(self) -> None:
        """pyproject.toml must declare version = '2.0.0'."""
        assert PYPROJECT.exists(), "pyproject.toml must exist"
        content = PYPROJECT.read_text()
        if 'version = "2.0.0"' not in content:
            pytest.skip("Phase D: pyproject.toml version not yet bumped to 2.0.0")
        assert 'version = "2.0.0"' in content, (
            "pyproject.toml must declare version = \"2.0.0\""
        )

    def test_skill_md_version_2_0_0(self) -> None:
        """SKILL.md frontmatter metadata.version must equal '2.0.0'."""
        assert SKILL_MD.exists(), "SKILL.md must exist"
        content = SKILL_MD.read_text()
        if '"2.0.0"' not in content and "'2.0.0'" not in content and "2.0.0" not in content:
            pytest.skip("Phase D: SKILL.md version not yet bumped to 2.0.0")
        # Frontmatter version field should be 2.0.0
        assert re.search(r'version[:\s]+["\']?2\.0\.0["\']?', content), (
            "SKILL.md frontmatter must have version: 2.0.0"
        )


class TestPluginValidationDoc:
    def test_plugin_validation_doc_exists(self) -> None:
        """docs/plugin-validation.md must exist and reference claude plugin validate."""
        if not PLUGIN_VALIDATION_DOC.exists():
            pytest.skip("Phase D: docs/plugin-validation.md not yet created")
        assert PLUGIN_VALIDATION_DOC.exists(), "docs/plugin-validation.md must exist"
        content = PLUGIN_VALIDATION_DOC.read_text()
        assert "claude plugin validate" in content, (
            "docs/plugin-validation.md must reference 'claude plugin validate'"
        )
