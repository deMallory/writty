"""Shared fixtures for the plugin distribution test suite.

All tests in tests/plugin/ rely on these fixtures for repo-root resolution
and manifest loading. Fixtures skip rather than fail when Phase A/B artifacts
are absent so the suite loads cleanly before those phases land.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest


REPO_ROOT = (Path.home() / ".claude/skills/writ")


def _expand_plugin_root(path: str, root: Path) -> Path:
    """Substitute ${CLAUDE_PLUGIN_ROOT} with repo root for test-time path resolution."""
    expanded = path.replace("${CLAUDE_PLUGIN_ROOT}", str(root))
    return Path(expanded)


@pytest.fixture()
def repo_root() -> Path:
    """Absolute path to the Writ repo root."""
    return REPO_ROOT


@pytest.fixture()
def marketplace_manifest(repo_root: Path) -> dict:
    """Load and parse .claude-plugin/marketplace.json; skip if absent (pre-Phase A)."""
    manifest_path = repo_root / ".claude-plugin" / "marketplace.json"
    if not manifest_path.exists():
        pytest.skip("Phase A artifact .claude-plugin/marketplace.json not yet created")
    return json.loads(manifest_path.read_text())


@pytest.fixture()
def plugin_manifest(repo_root: Path) -> dict:
    """Load and parse .claude-plugin/plugin.json; skip if absent."""
    manifest_path = repo_root / ".claude-plugin" / "plugin.json"
    if not manifest_path.exists():
        pytest.skip("Phase A artifact .claude-plugin/plugin.json not yet created")
    return json.loads(manifest_path.read_text())


@pytest.fixture()
def hooks_json(repo_root: Path) -> dict:
    """Load and parse hooks/hooks.json; skip if absent (pre-Phase B)."""
    hooks_path = repo_root / "hooks" / "hooks.json"
    if not hooks_path.exists():
        pytest.skip("Phase B artifact hooks/hooks.json not yet created")
    return json.loads(hooks_path.read_text())
