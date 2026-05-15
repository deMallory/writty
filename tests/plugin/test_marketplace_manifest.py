"""Tests for .claude-plugin/marketplace.json (Phase A).

Verifies the marketplace manifest exists, parses as valid JSON, and conforms
to the claude plugin marketplace schema requirements. All tests skip cleanly
before Phase A lands.
"""

from __future__ import annotations

import json
import re
import tomllib
from pathlib import Path

import pytest

from tests.plugin.conftest import REPO_ROOT

MANIFEST_PATH = REPO_ROOT / ".claude-plugin" / "marketplace.json"


def _pyproject_version() -> str:
    """Single source of truth for the current writ version.

    See tests/plugin/test_plugin_manifest.py for the same helper +
    rationale. Reads pyproject.toml on every call so future version
    bumps only require touching pyproject.toml + the manifests; the
    tests catch drift without needing per-release edits.
    """
    data = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text())
    return data["project"]["version"]

RESERVED_NAMES = {
    "claude-code-marketplace",
    "claude-code-plugins",
    "claude-plugins-official",
    "anthropic-marketplace",
    "anthropic-plugins",
    "agent-skills",
    "knowledge-work-plugins",
    "life-sciences",
}


class TestMarketplaceManifestExists:
    def test_marketplace_json_exists_and_parses(self) -> None:
        """marketplace.json must exist at .claude-plugin/marketplace.json and be valid JSON."""
        if not MANIFEST_PATH.exists():
            pytest.skip("Phase A artifact not yet created")
        data = json.loads(MANIFEST_PATH.read_text())
        assert isinstance(data, dict)


class TestMarketplaceManifestStructure:
    @pytest.fixture()
    def manifest(self) -> dict:
        if not MANIFEST_PATH.exists():
            pytest.skip("Phase A artifact not yet created")
        return json.loads(MANIFEST_PATH.read_text())

    def test_marketplace_required_fields(self, manifest: dict) -> None:
        """Manifest must have name, owner (with name), and a plugins array."""
        assert "name" in manifest, "marketplace.json must have a 'name' field"
        assert "owner" in manifest, "marketplace.json must have an 'owner' field"
        assert isinstance(manifest["owner"], dict), "'owner' must be an object"
        assert "name" in manifest["owner"], "'owner' must have a 'name' field"
        assert "plugins" in manifest, "marketplace.json must have a 'plugins' array"
        assert isinstance(manifest["plugins"], list), "'plugins' must be an array"

    def test_marketplace_name_not_reserved(self, manifest: dict) -> None:
        """Marketplace name must not be one of the reserved names per Claude Code spec."""
        name = manifest.get("name", "")
        assert name not in RESERVED_NAMES, (
            f"Marketplace name '{name}' is reserved and cannot be used"
        )

    def test_marketplace_name_kebab_case(self, manifest: dict) -> None:
        """Marketplace name must match ^[a-z][a-z0-9-]*$ (kebab-case, lowercase)."""
        name = manifest.get("name", "")
        assert re.match(r"^[a-z][a-z0-9-]*$", name), (
            f"Marketplace name '{name}' must be kebab-case matching ^[a-z][a-z0-9-]*$"
        )

    def test_marketplace_owner_well_formed(self, manifest: dict) -> None:
        """owner.name must be non-empty string; if owner.email present, it must look like an email."""
        owner = manifest.get("owner", {})
        assert isinstance(owner.get("name"), str) and owner["name"].strip(), (
            "owner.name must be a non-empty string"
        )
        if "email" in owner:
            email = owner["email"]
            assert "@" in email and "." in email.split("@")[-1], (
                f"owner.email '{email}' does not look like a valid email address"
            )

    def test_marketplace_plugin_entry_writ(self, manifest: dict) -> None:
        """plugins array must have exactly one entry with name 'writ',
        source './', description, and version matching pyproject.toml's
        version field."""
        plugins = manifest.get("plugins", [])
        assert len(plugins) == 1, (
            f"marketplace.json must have exactly one plugin entry, found {len(plugins)}"
        )
        entry = plugins[0]
        assert entry.get("name") == "writ", "Plugin entry name must be 'writ'"
        assert entry.get("source") == "./", "Plugin entry source must be './'"
        assert "description" in entry, "Plugin entry must have a 'description' field"
        expected_version = _pyproject_version()
        assert entry.get("version") == expected_version, (
            f"Plugin entry version must match pyproject.toml "
            f"[project].version ({expected_version!r}); got "
            f"{entry.get('version')!r}. The manifests must move in "
            f"lockstep with pyproject.toml."
        )

    def test_marketplace_source_relative_path_ok(self, manifest: dict) -> None:
        """source must start with './' (relative path; required for git-hosted same-repo marketplaces)."""
        plugins = manifest.get("plugins", [])
        for entry in plugins:
            source = entry.get("source", "")
            assert source.startswith("./"), (
                f"Plugin source '{source}' must start with './' for same-repo marketplace"
            )
