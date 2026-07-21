"""Tests for documentation and version-field deliverables.

Verifies README.md exists and pyproject.toml carries a semver-shaped
version. Originally covered CHANGELOG.md and docs/plugin-validation.md
content; those files were removed when the project moved to private
distribution and the marketplace-facing artifacts were retired.
"""

from __future__ import annotations

import re
import tomllib

from tests.plugin.conftest import REPO_ROOT

README = REPO_ROOT / "README.md"
PYPROJECT = REPO_ROOT / "pyproject.toml"


def _pyproject_version() -> str:
    data = tomllib.loads(PYPROJECT.read_text())
    return data["project"]["version"]


class TestRepoDocs:
    def test_readme_exists(self) -> None:
        assert README.exists(), "README.md must exist"


class TestVersionBumps:
    """pyproject.toml must declare a non-empty semver-shaped version."""

    def test_pyproject_declares_semver_version(self) -> None:
        assert PYPROJECT.exists(), "pyproject.toml must exist"
        version = _pyproject_version()
        assert version, "pyproject.toml [project].version must be non-empty"
        assert re.match(r"^\d+\.\d+\.\d+", version), (
            f"pyproject.toml version {version!r} must be semver-shaped "
            f"(MAJOR.MINOR.PATCH)."
        )
