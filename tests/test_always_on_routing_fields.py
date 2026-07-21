"""Always-on applicability routing fields on Rule (WRIT-BLUEPRINT 3.5).

Rules gain applicability_scope + trigger_keywords (mirroring methodology nodes) so the
always-on bundle can inject each rule at the moment its WHEN matches instead of all-every-turn.
These assert the data plumbing: the RULE-START parser reads the fields, the schema validates
them, the exporter renders them, and the cycle round-trips. A rule without the fields stays
valid with empty lists (fail-open).
"""

from __future__ import annotations

from pathlib import Path

from writ.export import rule_to_markdown
from writ.graph.ingest import parse_rules_from_file, validate_parsed_rule


def _rule_dict(**over) -> dict:
    base = {
        "rule_id": "SEC-INJ-SQL-001",
        "domain": "security",
        "severity": "critical",
        "scope": "component",
        "trigger": "When writing SQL strings that include any variable.",
        "statement": "Parameterized queries only.",
        "violation": "cursor.execute(f\"... {x}\")",
        "pass_example": "cursor.execute(q, params)",
        "enforcement": "regex scan flags f-strings near execute.",
        "rationale": "SQL injection is the most common high-severity web vuln.",
        "mandatory": True,
        "applicability_scope": ["write"],
        "trigger_keywords": ["sql", "query", "execute"],
    }
    base.update(over)
    return base


def _roundtrip(tmp_path: Path, rule: dict) -> dict:
    """Render a rule to markdown, write it, parse it back; return the parsed dict."""
    md = rule_to_markdown(rule)
    f = tmp_path / "rules.md"
    f.write_text(md, encoding="utf-8")
    parsed = parse_rules_from_file(f)
    assert len(parsed) == 1, f"expected one rule, got {len(parsed)}"
    return parsed[0]


class TestRoutingFieldsRoundTrip:
    def test_parser_reads_routing_fields(self, tmp_path):
        parsed = _roundtrip(tmp_path, _rule_dict())
        assert parsed["applicability_scope"] == ["write"]
        assert parsed["trigger_keywords"] == ["sql", "query", "execute"]

    def test_schema_validates_routing_fields(self, tmp_path):
        parsed = _roundtrip(tmp_path, _rule_dict())
        rule = validate_parsed_rule(parsed)
        assert rule.applicability_scope == ["write"]
        assert rule.trigger_keywords == ["sql", "query", "execute"]

    def test_multi_scope_and_keywords_roundtrip(self, tmp_path):
        r = _rule_dict(
            rule_id="ENF-PROC-WORKTREE-001",
            applicability_scope=["bash", "write"],
            trigger_keywords=["git worktree add", "worktree"],
        )
        parsed = _roundtrip(tmp_path, r)
        assert parsed["applicability_scope"] == ["bash", "write"]
        # phrases with spaces survive (comma-split, not whitespace-split)
        assert parsed["trigger_keywords"] == ["git worktree add", "worktree"]

    def test_exporter_emits_fields_only_when_present(self, tmp_path):
        with_fields = rule_to_markdown(_rule_dict())
        assert "**Applicability_Scope**: write" in with_fields
        assert "**Trigger_Keywords**: sql, query, execute" in with_fields
        bare = rule_to_markdown(_rule_dict(applicability_scope=[], trigger_keywords=[]))
        assert "Applicability_Scope" not in bare
        assert "Trigger_Keywords" not in bare

    def test_absent_fields_default_empty_and_valid(self, tmp_path):
        """A rule with no routing fields stays valid with empty lists (fail-open)."""
        parsed = _roundtrip(tmp_path, _rule_dict(applicability_scope=[], trigger_keywords=[]))
        assert parsed.get("applicability_scope", []) == []
        assert parsed.get("trigger_keywords", []) == []
        rule = validate_parsed_rule(parsed)
        assert rule.applicability_scope == []
        assert rule.trigger_keywords == []
