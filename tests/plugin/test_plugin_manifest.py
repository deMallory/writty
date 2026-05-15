"""Tests for .claude-plugin/plugin.json (Phase A + Phase B).

Phase A tests verify header-level conformance: required metadata fields, no
deprecated keys, correct version and URLs. Phase B tests (marked with
pytest.skip("Phase B")) verify component-path fields that are added in Phase B.
"""

from __future__ import annotations

import json
import tomllib
from pathlib import Path

import pytest

from tests.plugin.conftest import REPO_ROOT

MANIFEST_PATH = REPO_ROOT / ".claude-plugin" / "plugin.json"


def _pyproject_version() -> str:
    """Single source of truth for the current writ version.

    Reads pyproject.toml on every call. Asserting plugin.json version
    against this rather than a hardcoded string means version bumps
    only require touching pyproject.toml + plugin.json + the other two
    manifests; this test catches drift between them without needing
    its own per-release edit.
    """
    data = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text())
    return data["project"]["version"]


DEPRECATED_FIELDS = {"permissions", "defaultEnabled"}
DEPRECATED_LIFECYCLE_KEYS = {"Init", "Shutdown"}

ALLOWED_SPDX_IDS = {"MIT", "Apache-2.0", "BSD-3-Clause", "ISC", "MPL-2.0"}


class TestPluginManifestExists:
    def test_plugin_json_exists_and_parses(self) -> None:
        """plugin.json must exist at .claude-plugin/plugin.json and be valid JSON."""
        if not MANIFEST_PATH.exists():
            pytest.skip("Phase A artifact not yet created")
        data = json.loads(MANIFEST_PATH.read_text())
        assert isinstance(data, dict)


class TestPluginManifestSchema:
    @pytest.fixture()
    def manifest(self) -> dict:
        if not MANIFEST_PATH.exists():
            pytest.skip("Phase A artifact not yet created")
        return json.loads(MANIFEST_PATH.read_text())

    def test_plugin_json_has_no_deprecated_fields(self, manifest: dict) -> None:
        """plugin.json must NOT contain permissions, defaultEnabled, lifecycle.Init, or lifecycle.Shutdown."""
        for field in DEPRECATED_FIELDS:
            assert field not in manifest, (
                f"plugin.json must not contain deprecated field '{field}'"
            )
        lifecycle = manifest.get("lifecycle", {})
        if isinstance(lifecycle, dict):
            for key in DEPRECATED_LIFECYCLE_KEYS:
                assert key not in lifecycle, (
                    f"plugin.json lifecycle must not contain deprecated key '{key}'"
                )

    def test_plugin_json_required_name(self, manifest: dict) -> None:
        """name field must equal 'writ'."""
        assert manifest.get("name") == "writ", (
            f"plugin.json name must be 'writ', got '{manifest.get('name')}'"
        )

    def test_plugin_json_metadata_fields(self, manifest: dict) -> None:
        """plugin.json must have version matching pyproject.toml's version
        field, plus description, author.name, homepage, repository,
        license, keywords."""
        expected_version = _pyproject_version()
        assert manifest.get("version") == expected_version, (
            f"plugin.json version must match pyproject.toml [project].version "
            f"({expected_version!r}); got {manifest.get('version')!r}. The "
            f"manifests must move in lockstep with pyproject.toml."
        )
        assert "description" in manifest and manifest["description"], (
            "plugin.json must have a non-empty description"
        )
        author = manifest.get("author", {})
        assert isinstance(author, dict) and author.get("name"), (
            "plugin.json must have author.name"
        )
        assert "homepage" in manifest and manifest["homepage"], (
            "plugin.json must have a homepage URL"
        )
        assert "repository" in manifest and manifest["repository"], (
            "plugin.json must have a repository URL"
        )
        assert "license" in manifest, "plugin.json must have a license field"
        keywords = manifest.get("keywords")
        assert isinstance(keywords, list) and len(keywords) > 0, (
            "plugin.json must have a non-empty keywords list"
        )

    def test_plugin_json_homepage_repository_match_remote(self, manifest: dict) -> None:
        """Both homepage and repository must reference infinri/Writ on github."""
        homepage = manifest.get("homepage", "")
        repository = manifest.get("repository", "")
        assert "infinri/Writ" in homepage or "infinri/writ" in homepage.lower(), (
            f"homepage '{homepage}' must reference infinri/Writ on github"
        )
        assert "infinri/Writ" in repository or "infinri/writ" in repository.lower(), (
            f"repository '{repository}' must reference infinri/Writ on github"
        )

    def test_plugin_json_license_spdx(self, manifest: dict) -> None:
        """license must be a known SPDX identifier from the allowed-list."""
        license_id = manifest.get("license", "")
        assert license_id in ALLOWED_SPDX_IDS, (
            f"plugin.json license '{license_id}' must be one of {ALLOWED_SPDX_IDS}"
        )


class TestPluginManifestPhaseB:
    """Component-path fields added in Phase B. Tests skip until Phase B lands."""

    @pytest.fixture()
    def manifest(self) -> dict:
        if not MANIFEST_PATH.exists():
            pytest.skip("Phase A artifact not yet created")
        return json.loads(MANIFEST_PATH.read_text())

    def test_plugin_json_skills_field(self, manifest: dict) -> None:
        """skills must be ['./'] or contain './' so SKILL.md is auto-discovered."""
        if "skills" not in manifest:
            pytest.skip("Phase B: skills field not yet added to plugin.json")
        skills = manifest["skills"]
        assert "./" in skills, (
            f"plugin.json skills must contain './', got {skills}"
        )

    def test_plugin_json_commands_field(self, manifest: dict) -> None:
        """commands must reference ./.claude/commands for slash-command discovery."""
        if "commands" not in manifest:
            pytest.skip("Phase B: commands field not yet added to plugin.json")
        commands = manifest["commands"]
        assert ".claude/commands" in commands, (
            f"plugin.json commands must reference .claude/commands, got '{commands}'"
        )

    def test_plugin_json_agents_field(self, manifest: dict) -> None:
        """agents must reference ./.claude/agents for sub-agent discovery."""
        if "agents" not in manifest:
            pytest.skip("Phase B: agents field not yet added to plugin.json")
        agents = manifest["agents"]
        assert ".claude/agents" in agents, (
            f"plugin.json agents must reference .claude/agents, got '{agents}'"
        )

    def test_plugin_json_hooks_field(self, manifest: dict) -> None:
        """hooks must reference ./hooks/hooks.json for hook auto-discovery."""
        if "hooks" not in manifest:
            pytest.skip("Phase B: hooks field not yet added to plugin.json")
        hooks = manifest["hooks"]
        assert "hooks/hooks.json" in hooks, (
            f"plugin.json hooks must reference hooks/hooks.json, got '{hooks}'"
        )
