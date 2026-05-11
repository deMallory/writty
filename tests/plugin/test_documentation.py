"""Tests for documentation and version-bump deliverables.

Verifies README, CHANGELOG, pyproject.toml, SKILL.md, and the new
docs/plugin-validation.md all reflect the v1.0.1 plugin distribution work.
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

    def test_readme_switching_section_exists(self, content: str) -> None:
        """README.md must contain the 'Switching from the standalone install to the plugin' section."""
        assert "Switching from the standalone install to the plugin" in content, (
            "README.md must have a 'Switching from the standalone install to the plugin' section"
        )


class TestChangelog:
    @pytest.fixture()
    def content(self) -> str:
        assert CHANGELOG.exists(), "CHANGELOG.md must exist"
        return CHANGELOG.read_text()

    def test_changelog_1_0_1_entry(self, content: str) -> None:
        """CHANGELOG.md must contain a ## [1.0.1] section heading."""
        assert "## [1.0.1]" in content, (
            "CHANGELOG.md must have a '## [1.0.1]' section"
        )

    def test_changelog_added_changed(self, content: str) -> None:
        """The 1.0.1 section must have Added and Changed subsections."""
        assert "## [1.0.1]" in content, (
            "CHANGELOG.md must have a '## [1.0.1]' section"
        )
        idx = content.index("## [1.0.1]")
        next_section = content.find("\n## [", idx + 1)
        section = content[idx:next_section] if next_section != -1 else content[idx:]
        lowered = section.lower()
        for subsection in ("added", "changed"):
            assert subsection in lowered, (
                f"CHANGELOG.md 1.0.1 section must contain a '{subsection}' subsection"
            )


class TestVersionBumps:
    def test_pyproject_version_1_0_1(self) -> None:
        """pyproject.toml must declare version = '1.0.1'."""
        assert PYPROJECT.exists(), "pyproject.toml must exist"
        content = PYPROJECT.read_text()
        assert 'version = "1.0.1"' in content, (
            "pyproject.toml must declare version = \"1.0.1\""
        )

    def test_skill_md_version_1_0_1(self) -> None:
        """SKILL.md frontmatter metadata.version must equal '1.0.1'."""
        assert SKILL_MD.exists(), "SKILL.md must exist"
        content = SKILL_MD.read_text()
        assert re.search(r'version[:\s]+["\']?1\.0\.1["\']?', content), (
            "SKILL.md frontmatter must have version: 1.0.1"
        )


class TestPluginValidationDoc:
    def test_plugin_validation_doc_exists(self) -> None:
        """docs/plugin-validation.md must exist and reference claude plugin validate."""
        if not PLUGIN_VALIDATION_DOC.exists():
            pytest.skip("docs/plugin-validation.md not yet created")
        assert PLUGIN_VALIDATION_DOC.exists(), "docs/plugin-validation.md must exist"
        content = PLUGIN_VALIDATION_DOC.read_text()
        assert "claude plugin validate" in content, (
            "docs/plugin-validation.md must reference 'claude plugin validate'"
        )
