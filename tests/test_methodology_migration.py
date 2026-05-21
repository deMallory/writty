"""v1.4.0 acceptance tests: static-context absorption into hybrid RAG.

Covers the new acceptance surface introduced in v1.4.0:
- SKILL.md deletion
- plugin.json skills key removal
- four new Methodology nodes and their frontmatter
- templates/CLAUDE.md slimming
- writ-rag-inject.sh breadcrumb repoint
- rules/ stubs pointing at Methodology nodes
- docs cross-reference updates
- CHANGELOG 1.4.0 entry structure

Tests are expected to FAIL until implementation is complete.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path("/home/lucio.saldivar/.claude/skills/writ")
METHODOLOGY_DIR = REPO_ROOT / "bible" / "methodology"

# Required SKL frontmatter keys (from SKL-PROC-BRAIN-001.md schema)
SKL_REQUIRED_KEYS = {
    "skill_id",
    "node_type",
    "domain",
    "severity",
    "trigger",
    "statement",
    "confidence",
    "authority",
    "last_validated",
}

# Required PBK frontmatter keys (from PBK-PROC-PLAN-001.md schema)
PBK_REQUIRED_KEYS = {
    "playbook_id",
    "node_type",
    "domain",
    "severity",
    "trigger",
    "statement",
    "confidence",
    "authority",
    "last_validated",
    "phase_ids",
    "preconditions",
    "dispatched_roles",
}


def _parse_frontmatter(path: Path) -> dict:
    """Extract and parse YAML frontmatter from a Markdown file.

    Matches the '--- ... ---' block at the start of the file and passes
    the contents to yaml.safe_load. Returns an empty dict if no block
    is found or parsing fails.
    """
    text = path.read_text()
    match = re.match(r"^---\n(.*?)\n---", text, re.DOTALL)
    if not match:
        return {}
    return yaml.safe_load(match.group(1)) or {}


# ---------------------------------------------------------------------------
# SKILL.md deletion
# ---------------------------------------------------------------------------


class TestSkillMdDeleted:
    def test_skill_md_is_deleted(self) -> None:
        """SKILL.md must not exist at the repository root after v1.4.0 migration."""
        assert (REPO_ROOT / "SKILL.md").exists() is False, (
            "SKILL.md must be deleted from the repo root in v1.4.0; "
            "its content has moved to HANDBOOK.md and Methodology nodes"
        )


# ---------------------------------------------------------------------------
# plugin.json skills key removal
# ---------------------------------------------------------------------------


class TestPluginJsonSkillsKey:
    def test_plugin_json_has_no_skills_key(self) -> None:
        """plugin.json must not contain a top-level 'skills' key.

        Writ no longer ships as an Agent Skill plugin; SKILL.md is deleted
        and the skills auto-discovery path is removed.
        """
        import json
        manifest_path = REPO_ROOT / ".claude-plugin" / "plugin.json"
        assert manifest_path.exists(), ".claude-plugin/plugin.json must exist"
        manifest = json.loads(manifest_path.read_text())
        assert "skills" not in manifest, (
            "plugin.json must not have a 'skills' key; "
            "Writ no longer ships as a Skill plugin (v1.4.0)"
        )


# ---------------------------------------------------------------------------
# Methodology node existence
# ---------------------------------------------------------------------------


class TestMethodologyNodeExists:
    def test_methodology_node_skl_proc_mode_001_exists(self) -> None:
        """bible/methodology/SKL-PROC-MODE-001.md must exist."""
        node = METHODOLOGY_DIR / "SKL-PROC-MODE-001.md"
        assert node.exists(), (
            f"{node} must exist; it teaches the mode-set workflow "
            "migrated from templates/CLAUDE.md in v1.4.0"
        )

    def test_methodology_node_pbk_proc_work_workflow_001_exists(self) -> None:
        """bible/methodology/PBK-PROC-WORK-WORKFLOW-001.md must exist."""
        node = METHODOLOGY_DIR / "PBK-PROC-WORK-WORKFLOW-001.md"
        assert node.exists(), (
            f"{node} must exist; it describes the Work-mode gate pipeline "
            "migrated from templates/CLAUDE.md in v1.4.0"
        )

    def test_methodology_node_pbk_proc_orchestrator_001_exists(self) -> None:
        """bible/methodology/PBK-PROC-ORCHESTRATOR-001.md must exist."""
        node = METHODOLOGY_DIR / "PBK-PROC-ORCHESTRATOR-001.md"
        assert node.exists(), (
            f"{node} must exist; it replaces rules/writ-orchestrator.md "
            "as the canonical orchestrator playbook in v1.4.0"
        )

    def test_methodology_node_skl_proc_writ_failure_001_exists(self) -> None:
        """bible/methodology/SKL-PROC-WRIT-FAILURE-001.md must exist."""
        node = METHODOLOGY_DIR / "SKL-PROC-WRIT-FAILURE-001.md"
        assert node.exists(), (
            f"{node} must exist; it replaces rules/writ-workflow.md "
            "as the canonical failure-mode skill in v1.4.0"
        )


# ---------------------------------------------------------------------------
# Methodology node frontmatter
# ---------------------------------------------------------------------------


class TestMethodologyNodeFrontmatter:
    def test_methodology_node_skl_proc_mode_001_has_required_frontmatter(
        self,
    ) -> None:
        """SKL-PROC-MODE-001.md frontmatter must contain all required SKL keys."""
        node = METHODOLOGY_DIR / "SKL-PROC-MODE-001.md"
        assert node.exists(), f"{node} must exist before frontmatter can be checked"
        fm = _parse_frontmatter(node)
        missing = SKL_REQUIRED_KEYS - set(fm.keys())
        assert not missing, (
            f"SKL-PROC-MODE-001.md frontmatter is missing keys: {sorted(missing)}. "
            f"Required SKL keys: {sorted(SKL_REQUIRED_KEYS)}"
        )

    def test_methodology_node_pbk_proc_work_workflow_001_has_required_frontmatter(
        self,
    ) -> None:
        """PBK-PROC-WORK-WORKFLOW-001.md frontmatter must contain all required PBK keys."""
        node = METHODOLOGY_DIR / "PBK-PROC-WORK-WORKFLOW-001.md"
        assert node.exists(), f"{node} must exist before frontmatter can be checked"
        fm = _parse_frontmatter(node)
        missing = PBK_REQUIRED_KEYS - set(fm.keys())
        assert not missing, (
            f"PBK-PROC-WORK-WORKFLOW-001.md frontmatter is missing keys: {sorted(missing)}. "
            f"Required PBK keys: {sorted(PBK_REQUIRED_KEYS)}"
        )

    def test_methodology_node_pbk_proc_orchestrator_001_has_required_frontmatter(
        self,
    ) -> None:
        """PBK-PROC-ORCHESTRATOR-001.md frontmatter must contain all required PBK keys."""
        node = METHODOLOGY_DIR / "PBK-PROC-ORCHESTRATOR-001.md"
        assert node.exists(), f"{node} must exist before frontmatter can be checked"
        fm = _parse_frontmatter(node)
        missing = PBK_REQUIRED_KEYS - set(fm.keys())
        assert not missing, (
            f"PBK-PROC-ORCHESTRATOR-001.md frontmatter is missing keys: {sorted(missing)}. "
            f"Required PBK keys: {sorted(PBK_REQUIRED_KEYS)}"
        )

    def test_methodology_node_skl_proc_writ_failure_001_has_required_frontmatter(
        self,
    ) -> None:
        """SKL-PROC-WRIT-FAILURE-001.md frontmatter must contain all required SKL keys."""
        node = METHODOLOGY_DIR / "SKL-PROC-WRIT-FAILURE-001.md"
        assert node.exists(), f"{node} must exist before frontmatter can be checked"
        fm = _parse_frontmatter(node)
        missing = SKL_REQUIRED_KEYS - set(fm.keys())
        assert not missing, (
            f"SKL-PROC-WRIT-FAILURE-001.md frontmatter is missing keys: {sorted(missing)}. "
            f"Required SKL keys: {sorted(SKL_REQUIRED_KEYS)}"
        )


# ---------------------------------------------------------------------------
# Methodology node semantic content
# ---------------------------------------------------------------------------


class TestMethodologyNodeContent:
    def test_methodology_node_pbk_proc_work_workflow_001_declares_preconditions(
        self,
    ) -> None:
        """PBK-PROC-WORK-WORKFLOW-001.md preconditions must include SKL-PROC-MODE-001.

        The Work-mode playbook depends on the mode-set skill being understood
        first; the precondition encodes that dependency for graph traversal.
        """
        node = METHODOLOGY_DIR / "PBK-PROC-WORK-WORKFLOW-001.md"
        assert node.exists(), f"{node} must exist"
        fm = _parse_frontmatter(node)
        preconditions = fm.get("preconditions", [])
        assert "SKL-PROC-MODE-001" in preconditions, (
            f"PBK-PROC-WORK-WORKFLOW-001.md preconditions must include "
            f"'SKL-PROC-MODE-001'; got {preconditions!r}"
        )

    def test_methodology_node_pbk_proc_orchestrator_001_lists_workers(
        self,
    ) -> None:
        """PBK-PROC-ORCHESTRATOR-001.md dispatched_roles must list all four workers.

        The orchestrator playbook must enumerate every worker role so the
        graph can express the dispatch sequence as edges.
        """
        node = METHODOLOGY_DIR / "PBK-PROC-ORCHESTRATOR-001.md"
        assert node.exists(), f"{node} must exist"
        fm = _parse_frontmatter(node)
        dispatched_roles = fm.get("dispatched_roles", [])
        expected_roles = {
            "writ-explorer",
            "writ-planner",
            "writ-test-writer",
            "writ-implementer",
        }
        missing = expected_roles - set(dispatched_roles)
        assert not missing, (
            f"PBK-PROC-ORCHESTRATOR-001.md dispatched_roles must include "
            f"{sorted(expected_roles)}; missing: {sorted(missing)}; "
            f"got {dispatched_roles!r}"
        )


# ---------------------------------------------------------------------------
# templates/CLAUDE.md slimming
# ---------------------------------------------------------------------------


class TestClaudeMdTemplate:
    @pytest.fixture()
    def template(self) -> str:
        path = REPO_ROOT / "templates" / "CLAUDE.md"
        assert path.exists(), "templates/CLAUDE.md must exist"
        return path.read_text()

    def test_claude_md_template_drops_memory_tiers_section(
        self, template: str
    ) -> None:
        """templates/CLAUDE.md must not contain the '## Memory tiers' section.

        The memory-tiers table is now surfaced via RAG injection, not static
        context. Its presence in the template wastes ~200 tokens per session.
        """
        assert "## Memory tiers" not in template, (
            "templates/CLAUDE.md must not contain '## Memory tiers'; "
            "this section was removed in v1.4.0 (now surfaced via RAG)"
        )

    def test_claude_md_template_drops_mandatory_workflow_section(
        self, template: str
    ) -> None:
        """templates/CLAUDE.md must not contain '## Mandatory workflow before any task'.

        The mandatory-workflow tutorial is now a Methodology node
        (PBK-PROC-WORK-WORKFLOW-001) surfaced via RAG injection.
        """
        assert "## Mandatory workflow before any task" not in template, (
            "templates/CLAUDE.md must not contain '## Mandatory workflow before any task'; "
            "this section was removed in v1.4.0 (now in PBK-PROC-WORK-WORKFLOW-001)"
        )

    def test_claude_md_template_retains_global_preferences_section(
        self, template: str
    ) -> None:
        """templates/CLAUDE.md must retain the '## Global preferences' section.

        User preferences (no emojis, no em-dashes, short responses, etc.) are
        persistent and must not be moved to RAG -- they apply unconditionally.
        """
        assert "## Global preferences" in template, (
            "templates/CLAUDE.md must retain the '## Global preferences' section; "
            "user preferences are not workflow rules and must not be RAG-only"
        )

    def test_claude_md_template_has_bootstrap_fallback(
        self, template: str
    ) -> None:
        """templates/CLAUDE.md must contain a server-down bootstrap-fallback paragraph.

        When the Writ server is unavailable, Claude needs minimal orientation.
        The fallback paragraph must reference the server-unavailable scenario.
        """
        fallback_phrases = [
            "server is unavailable",
            "server unavailable",
            "unreachable",
            "server is down",
        ]
        found = any(phrase in template.lower() for phrase in fallback_phrases)
        assert found, (
            "templates/CLAUDE.md must contain a bootstrap-fallback paragraph for "
            "when the Writ server is unreachable; expected one of: "
            + str(fallback_phrases)
        )

    def test_claude_md_template_is_meaningfully_smaller(
        self, template: str
    ) -> None:
        """templates/CLAUDE.md must have fewer than 30 lines.

        The prior template was 82 lines. The v1.4.0 target is ~25 lines
        (user preferences + one bootstrap paragraph).
        """
        line_count = len(template.splitlines())
        assert line_count < 30, (
            f"templates/CLAUDE.md has {line_count} lines; must be under 30. "
            "The tutorial sections have been moved to Methodology nodes."
        )


# ---------------------------------------------------------------------------
# writ-rag-inject.sh breadcrumb repoint
# ---------------------------------------------------------------------------


class TestRagInjectHook:
    @pytest.fixture()
    def hook_text(self) -> str:
        path = REPO_ROOT / ".claude" / "hooks" / "writ-rag-inject.sh"
        assert path.exists(), ".claude/hooks/writ-rag-inject.sh must exist"
        return path.read_text()

    def test_rag_inject_hook_no_longer_references_skill_md(
        self, hook_text: str
    ) -> None:
        """writ-rag-inject.sh must not reference SKILL.md anywhere.

        The three breadcrumb lines at former lines 220, 585, 641 that
        said 'see SKILL.md' must be updated to reference HANDBOOK.md.
        """
        assert "SKILL.md" not in hook_text, (
            "writ-rag-inject.sh must not reference 'SKILL.md'; "
            "all breadcrumbs were repointed to HANDBOOK.md in v1.4.0"
        )

    def test_rag_inject_hook_references_handbook_md(
        self, hook_text: str
    ) -> None:
        """writ-rag-inject.sh must reference HANDBOOK.md at least twice.

        Each former SKILL.md breadcrumb (three total, at lines 220, 585, 641)
        must now point at HANDBOOK.md.
        """
        count = hook_text.count("HANDBOOK.md")
        assert count >= 2, (
            f"writ-rag-inject.sh must reference 'HANDBOOK.md' at least 2 times "
            f"(one per updated breadcrumb); found {count} occurrence(s)"
        )


# ---------------------------------------------------------------------------
# rules/ stubs pointing at Methodology nodes
# ---------------------------------------------------------------------------


class TestRulesStubs:
    def test_rules_writ_workflow_md_is_stub_pointing_at_methodology_node(
        self,
    ) -> None:
        """rules/writ-workflow.md must contain 'SKL-PROC-WRIT-FAILURE-001'.

        The file is kept as a thin pointer so the platform's automatic
        ~/.claude/rules/*.md global-load slot still surfaces something
        rather than 404'ing.
        """
        stub = REPO_ROOT / "rules" / "writ-workflow.md"
        assert stub.exists(), "rules/writ-workflow.md must exist as a stub"
        content = stub.read_text()
        assert "SKL-PROC-WRIT-FAILURE-001" in content, (
            "rules/writ-workflow.md must point at 'SKL-PROC-WRIT-FAILURE-001'; "
            "the content was migrated to that Methodology node in v1.4.0"
        )

    def test_rules_writ_orchestrator_md_is_stub_pointing_at_methodology_node(
        self,
    ) -> None:
        """rules/writ-orchestrator.md must contain PBK-PROC-ORCHESTRATOR-001,
        --orchestrator, and at least one of suppress/injection/token.

        Preserves the existing test_orchestrator_hardening.py assertions while
        confirming the stub points at the new Methodology node.
        """
        stub = REPO_ROOT / "rules" / "writ-orchestrator.md"
        assert stub.exists(), "rules/writ-orchestrator.md must exist as a stub"
        content = stub.read_text()
        assert "PBK-PROC-ORCHESTRATOR-001" in content, (
            "rules/writ-orchestrator.md must reference 'PBK-PROC-ORCHESTRATOR-001'"
        )
        assert "--orchestrator" in content, (
            "rules/writ-orchestrator.md must retain '--orchestrator' "
            "(required by test_orchestrator_hardening.py)"
        )
        token_words = {"suppress", "injection", "token"}
        found_token = any(word in content for word in token_words)
        assert found_token, (
            "rules/writ-orchestrator.md must contain at least one of "
            f"{sorted(token_words)} (required by test_orchestrator_hardening.py)"
        )


# ---------------------------------------------------------------------------
# docs cross-reference updates
# ---------------------------------------------------------------------------


class TestDocsUpdates:
    def test_docs_plugin_validation_no_longer_lists_skill_md(self) -> None:
        """docs/plugin-validation.md must not reference 'SKILL.md'.

        Line 16 previously listed 'Skill frontmatter in SKILL.md' as a
        validator-checked artifact; this was removed in v1.4.0.
        """
        doc = REPO_ROOT / "docs" / "plugin-validation.md"
        if not doc.exists():
            pytest.skip("docs/plugin-validation.md does not exist")
        content = doc.read_text()
        assert "SKILL.md" not in content, (
            "docs/plugin-validation.md must not reference 'SKILL.md'; "
            "the SKILL.md validator-check bullet was removed in v1.4.0"
        )

    def test_docs_extraction_01_repoints_at_handbook_md(self) -> None:
        """docs/extraction/01-architecture-and-data-flow.md table rows 249-251
        must reference HANDBOOK.md or Methodology node IDs instead of SKILL.md.

        Three rows in the source-of-truth table previously pointed at SKILL.md
        and rules/*.md. In v1.4.0 they point at HANDBOOK.md and the new nodes.
        """
        doc = REPO_ROOT / "docs" / "extraction" / "01-architecture-and-data-flow.md"
        if not doc.exists():
            pytest.skip("docs/extraction/01-architecture-and-data-flow.md does not exist")
        content = doc.read_text()
        lines = content.splitlines()

        # Find the "Hooks inventory + roles" table row.
        hooks_row = next(
            (ln for ln in lines if "Hooks inventory + roles" in ln), None
        )
        assert hooks_row is not None, (
            "Table row 'Hooks inventory + roles' not found in "
            "docs/extraction/01-architecture-and-data-flow.md"
        )
        valid_refs = {"HANDBOOK.md", "SKL-PROC-MODE-001", "SKL-PROC-WRIT-FAILURE-001",
                      "PBK-PROC-ORCHESTRATOR-001"}
        row_has_valid_ref = any(ref in hooks_row for ref in valid_refs)
        assert row_has_valid_ref, (
            f"'Hooks inventory + roles' row must reference one of {valid_refs}; "
            f"got: {hooks_row!r}"
        )
        assert "SKILL.md" not in hooks_row, (
            f"'Hooks inventory + roles' row must not reference 'SKILL.md'; "
            f"got: {hooks_row!r}"
        )

        # Find the "Mode system" table row.
        mode_row = next(
            (ln for ln in lines if "Mode system" in ln and "gate" in ln.lower()), None
        )
        assert mode_row is not None, (
            "Table row for 'Mode system, gate criteria, phase model' not found in "
            "docs/extraction/01-architecture-and-data-flow.md"
        )
        mode_has_valid_ref = any(ref in mode_row for ref in valid_refs)
        assert mode_has_valid_ref, (
            f"'Mode system' row must reference one of {valid_refs}; "
            f"got: {mode_row!r}"
        )
        assert "SKILL.md" not in mode_row, (
            f"'Mode system' row must not reference 'SKILL.md'; got: {mode_row!r}"
        )


# ---------------------------------------------------------------------------
# CHANGELOG 1.4.0 entry
# ---------------------------------------------------------------------------


class TestChangelogAbsorptionInV150:
    """The absorption work (SKILL.md removal, Methodology nodes, slimmed
    CLAUDE.md, hook breadcrumb repointing) ships as part of the combined
    [1.5.0] release entry. These assertions verify the [1.5.0] section
    documents the absorption work and uses the established subsection format."""

    @pytest.fixture()
    def content(self) -> str:
        path = REPO_ROOT / "CHANGELOG.md"
        assert path.exists(), "CHANGELOG.md must exist"
        return path.read_text()

    def test_changelog_150_entry_covers_absorption(self, content: str) -> None:
        """The [1.5.0] section must reference the SKILL.md removal and each of
        the four absorption-introduced Methodology nodes by ID."""
        assert "## [1.5.0]" in content, (
            "CHANGELOG.md must have a '## [1.5.0]' section"
        )
        idx_start = content.index("## [1.5.0]")
        idx_next = content.find("\n## [", idx_start + 1)
        section = content[idx_start:idx_next] if idx_next != -1 else content[idx_start:]

        assert "SKILL.md" in section, (
            "CHANGELOG.md [1.5.0] section must reference SKILL.md "
            "(the absorption work removes it)"
        )
        for node_id in (
            "SKL-PROC-MODE-001",
            "PBK-PROC-WORK-WORKFLOW-001",
            "PBK-PROC-ORCHESTRATOR-001",
            "SKL-PROC-WRIT-FAILURE-001",
        ):
            assert node_id in section, (
                f"CHANGELOG.md [1.5.0] section must reference {node_id} "
                f"(absorption work adds this Methodology node)"
            )

    def test_changelog_150_entry_has_required_subsections(
        self, content: str
    ) -> None:
        """The [1.5.0] CHANGELOG section must contain ### Removed, ### Added,
        and ### Changed subsections."""
        assert "## [1.5.0]" in content, "CHANGELOG.md must have a '## [1.5.0]' section"
        idx_start = content.index("## [1.5.0]")
        idx_next = content.find("\n## [", idx_start + 1)
        section = content[idx_start:idx_next] if idx_next != -1 else content[idx_start:]

        for subsection in ("### Removed", "### Added", "### Changed"):
            assert subsection in section, (
                f"CHANGELOG.md [1.5.0] section must contain '{subsection}'"
            )

    def test_changelog_preserves_130_entry(self, content: str) -> None:
        """CHANGELOG.md must still contain the 1.3.0 section (historical entry,
        must not be modified or removed)."""
        assert "## [1.3.0]" in content, (
            "CHANGELOG.md must retain the '## [1.3.0]' section; "
            "historical entries must not be removed"
        )
