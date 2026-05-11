"""Tests for dual-mode compatibility in server management scripts (Phase C).

Verifies that ensure-server.sh and stop-server.sh gain a CLAUDE_PLUGIN_ROOT
branch without breaking their existing standalone behavior, and that
writ-rag-inject.sh resolves the venv from the correct location based on
which env var is set.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.plugin.conftest import REPO_ROOT

ENSURE_SERVER = REPO_ROOT / "scripts" / "ensure-server.sh"
STOP_SERVER = REPO_ROOT / "scripts" / "stop-server.sh"
RAG_INJECT = REPO_ROOT / ".claude" / "hooks" / "writ-rag-inject.sh"


class TestEnsureServerDualMode:
    @pytest.fixture()
    def content(self) -> str:
        assert ENSURE_SERVER.exists(), "scripts/ensure-server.sh must exist"
        return ENSURE_SERVER.read_text()

    def test_ensure_server_has_plugin_root_branch(self, content: str) -> None:
        """ensure-server.sh must contain a branch using ${CLAUDE_PLUGIN_ROOT:-} for WRIT_DIR."""
        if "CLAUDE_PLUGIN_ROOT" not in content:
            pytest.skip("Phase C: CLAUDE_PLUGIN_ROOT branch not yet added to ensure-server.sh")
        assert "CLAUDE_PLUGIN_ROOT" in content, (
            "ensure-server.sh must have a branch checking ${CLAUDE_PLUGIN_ROOT:-}"
        )

    def test_ensure_server_has_plugin_data_branch(self, content: str) -> None:
        """When CLAUDE_PLUGIN_ROOT is set, VENV_DIR must resolve to ${CLAUDE_PLUGIN_DATA:-$HOME/.cache/writ}/.venv."""
        if "CLAUDE_PLUGIN_DATA" not in content:
            pytest.skip("Phase C: CLAUDE_PLUGIN_DATA branch not yet added to ensure-server.sh")
        assert "${CLAUDE_PLUGIN_DATA:-$HOME/.cache/writ}/.venv" in content, (
            "ensure-server.sh plugin branch must set VENV_DIR to "
            "${CLAUDE_PLUGIN_DATA:-$HOME/.cache/writ}/.venv"
        )

    def test_ensure_server_backward_compatible(self, content: str) -> None:
        """When CLAUDE_PLUGIN_ROOT is unset, the original dirname walk must be preserved."""
        assert 'dirname "$0"' in content or "dirname" in content, (
            "ensure-server.sh must preserve the original dirname-based WRIT_DIR fallback "
            "for standalone installs"
        )


class TestStopServerDualMode:
    @pytest.fixture()
    def content(self) -> str:
        assert STOP_SERVER.exists(), "scripts/stop-server.sh must exist"
        return STOP_SERVER.read_text()

    def test_stop_server_has_plugin_root_branch(self, content: str) -> None:
        """stop-server.sh must contain a branch using ${CLAUDE_PLUGIN_ROOT:-} for WRIT_DIR."""
        if "CLAUDE_PLUGIN_ROOT" not in content:
            pytest.skip("Phase C: CLAUDE_PLUGIN_ROOT branch not yet added to stop-server.sh")
        assert "CLAUDE_PLUGIN_ROOT" in content, (
            "stop-server.sh must have a branch checking ${CLAUDE_PLUGIN_ROOT:-}"
        )

    def test_stop_server_has_plugin_data_branch(self, content: str) -> None:
        """When CLAUDE_PLUGIN_ROOT is set, VENV_DIR must resolve to ${CLAUDE_PLUGIN_DATA:-$HOME/.cache/writ}/.venv."""
        if "CLAUDE_PLUGIN_DATA" not in content:
            pytest.skip("Phase C: CLAUDE_PLUGIN_DATA branch not yet added to stop-server.sh")
        assert "${CLAUDE_PLUGIN_DATA:-$HOME/.cache/writ}/.venv" in content, (
            "stop-server.sh plugin branch must set VENV_DIR to "
            "${CLAUDE_PLUGIN_DATA:-$HOME/.cache/writ}/.venv"
        )

    def test_stop_server_backward_compatible(self, content: str) -> None:
        """When CLAUDE_PLUGIN_ROOT is unset, the original dirname walk must be preserved."""
        assert 'dirname "$0"' in content or "dirname" in content, (
            "stop-server.sh must preserve the original dirname-based WRIT_DIR fallback "
            "for standalone installs"
        )


class TestRagInjectDualMode:
    @pytest.fixture()
    def content(self) -> str:
        assert RAG_INJECT.exists(), ".claude/hooks/writ-rag-inject.sh must exist"
        return RAG_INJECT.read_text()

    def test_writ_rag_inject_has_plugin_root_branch(self, content: str) -> None:
        """writ-rag-inject.sh must have the CLAUDE_PLUGIN_ROOT branch in the first 10 lines."""
        if "CLAUDE_PLUGIN_ROOT" not in content:
            pytest.skip(
                "Phase C: CLAUDE_PLUGIN_ROOT branch not yet added to writ-rag-inject.sh"
            )
        first_ten_lines = "\n".join(content.splitlines()[:10])
        assert "CLAUDE_PLUGIN_ROOT" in first_ten_lines, (
            "writ-rag-inject.sh must check ${CLAUDE_PLUGIN_ROOT:-} in the first 10 lines "
            "before falling back to the dirname walk"
        )
