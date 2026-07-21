"""Tests for writ/analysis/corpus_footprint.py (WRIT-TOKEN-BLUEPRINT.md lever B).

RED until writ/analysis/corpus_footprint.py + the CLI command exist.
Covers: per-component byte measurement + partition invariant, always-on bundle
cost + cap logic, code-block share, rank-cut candidate ordering + tag
presence + reach-field exclusion, scorecard shape + basis label, canary
(CorpusFootprintError on empty/unknown-domain corpus), and CLI exit codes.
"""
from __future__ import annotations

import importlib
import os
import sys
from pathlib import Path

import pytest

SKILL_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))


def _cf():
    if SKILL_ROOT not in sys.path:
        sys.path.insert(0, SKILL_ROOT)
    return importlib.import_module("writ.analysis.corpus_footprint")


# ---------------------------------------------------------------------------
# Shared rule-dict factory (TEST-FIXTURE-001 compliant)
# ---------------------------------------------------------------------------

def _rule(
    rule_id: str = "TEST-RULE-001",
    domain: str = "testing",
    trigger: str = "When writing a test function.",
    statement: str = "Every test has at least one assertion.",
    violation: str = "",
    pass_example: str = "",
    enforcement: str = "",
    rationale: str = "",
    edges: str = "",
    always_on: bool = False,
    mandatory: bool = False,
) -> dict:
    """Minimal rule dict matching parse_nodes_from_file output keys."""
    return {
        "rule_id": rule_id,
        "domain": domain,
        "node_type": "Rule",
        "trigger": trigger,
        "statement": statement,
        "violation": violation,
        "pass_example": pass_example,
        "enforcement": enforcement,
        "rationale": rationale,
        "edges": edges,
        "always_on": always_on,
        "mandatory": mandatory,
    }


# ---------------------------------------------------------------------------
# Real RULE-START block copied verbatim from bible/testing/rules.md (TEST-ASSERT-001).
# Used by tests that exercise the ingest loader path (load_corpus / scorecard / CLI).
# ---------------------------------------------------------------------------

_REAL_RULE_BLOCK = """\
<!-- RULE START: TEST-ASSERT-001 -->
## Rule TEST-ASSERT-001

**Domain**: testing
**Category**: CAT-CODE-TESTING-001
**Severity**: High
**Scope**: Component
**Mandatory**: false

### Trigger
When writing a test function.

### Statement
Every test has at least one assertion. Tests that exercise code without asserting an outcome are smoke tests at best and false-positive guarantees at worst.

### Violation
```python
def test_create_order():
    create_order(payload)  # no assert
```

### Pass
```python
def test_create_order():
    order = create_order(payload)
    assert order.id is not None
    assert order.status == 'pending'
```

### Enforcement
Linter rule (pytest-style assertion check; pylint custom rule).

### Rationale
An assertion-free test silently passes regardless of what the code does. The bug it claims to cover is invisible.

Related rules: TEST-ASSERT-002, TEST-EXIST-001, TEST-MOCK-001.

<!-- RULE END: TEST-ASSERT-001 -->
"""


@pytest.fixture
def tmp_bible(tmp_path: Path) -> Path:
    """A minimal bible dir containing one real RULE-START file (bible/<domain>/rules.md layout)."""
    domain_dir = tmp_path / "testing"
    domain_dir.mkdir()
    (domain_dir / "rules.md").write_text(_REAL_RULE_BLOCK, encoding="utf-8")
    return tmp_path


# ---------------------------------------------------------------------------
# TestMeasureRule
# ---------------------------------------------------------------------------

class TestMeasureRule:
    def test_component_bytes_match_utf8_len(self):
        cf = _cf()
        trigger = "When writing a test."
        statement = "Every test asserts something."
        violation = "def test(): pass"
        rule = _rule(trigger=trigger, statement=statement, violation=violation)
        result = cf.measure_rule(rule)
        assert result["components"]["trigger"]["bytes"] == len(trigger.encode("utf-8"))
        assert result["components"]["statement"]["bytes"] == len(statement.encode("utf-8"))
        assert result["components"]["violation"]["bytes"] == len(violation.encode("utf-8"))

    def test_tokens_floor_est_is_bytes_div_4(self):
        cf = _cf()
        trigger = "When writing a test function that has some text."
        rule = _rule(trigger=trigger)
        result = cf.measure_rule(rule)
        expected = len(trigger.encode("utf-8")) // 4
        assert result["components"]["trigger"]["tokens_floor_est"] == expected

    def test_core_plus_overhead_equals_total_bytes(self):
        """Partition invariant: every byte counted exactly once."""
        cf = _cf()
        rule = _rule(
            trigger="When writing a test.",
            statement="Every test has an assertion.",
            violation="def test(): pass",
            pass_example="def test(): assert result == 1",
            enforcement="Code review.",
            rationale="Tests without assertions prove nothing.",
            edges="RELATED_TO: TEST-ASSERT-002",
        )
        result = cf.measure_rule(rule)
        assert result["core_bytes"] + result["overhead_bytes"] == result["total_bytes"]

    def test_overhead_pct_in_zero_to_one(self):
        cf = _cf()
        rule = _rule(
            violation="A very long violation block with lots of prose explaining the issue.",
            pass_example="A good example here.",
        )
        result = cf.measure_rule(rule)
        assert 0.0 <= result["overhead_pct"] <= 1.0

    def test_empty_body_fields_produce_zero_overhead_no_crash(self):
        """A rule with all body fields empty: overhead == 0, no ZeroDivision."""
        cf = _cf()
        rule = _rule(
            trigger="Trigger text.",
            statement="Statement text.",
            violation="",
            pass_example="",
            enforcement="",
            rationale="",
            edges="",
        )
        result = cf.measure_rule(rule)
        assert result["overhead_bytes"] == 0
        assert result["overhead_pct"] == 0.0

    def test_fully_empty_rule_no_crash(self):
        """A rule with all fields empty (even trigger/statement): total_bytes == 0."""
        cf = _cf()
        rule = _rule(trigger="", statement="")
        result = cf.measure_rule(rule)
        assert result["total_bytes"] == 0
        assert result["overhead_pct"] == 0.0


# ---------------------------------------------------------------------------
# TestAlwaysOnBundle
# ---------------------------------------------------------------------------

class TestAlwaysOnBundle:
    def test_bundle_tokens_floor_est_equals_sum_over_flagged_rules(self):
        cf = _cf()
        if SKILL_ROOT not in sys.path:
            sys.path.insert(0, SKILL_ROOT)
        from writ.shared.tokens import estimate_tokens

        r_on = _rule(rule_id="A-001", always_on=True, trigger="Trigger A.", statement="Statement A.")
        r_mand = _rule(rule_id="B-001", mandatory=True, trigger="Trigger B.", statement="Statement B.")
        r_neither = _rule(rule_id="C-001", always_on=False, mandatory=False,
                          trigger="Trigger C.", statement="Statement C.")
        rules = [r_on, r_mand, r_neither]

        result = cf.always_on_bundle_cost(rules, cap=5000)

        expected_tokens = (
            estimate_tokens(r_on["trigger"], r_on["statement"])
            + estimate_tokens(r_mand["trigger"], r_mand["statement"])
        )
        assert result["tokens_floor_est"] == expected_tokens

    def test_rule_with_neither_flag_is_excluded_from_bundle(self):
        cf = _cf()
        r_normal = _rule(rule_id="N-001", always_on=False, mandatory=False,
                         trigger="Normal trigger.", statement="Normal statement.")
        result = cf.always_on_bundle_cost([r_normal], cap=5000)
        assert result["rule_count"] == 0
        assert result["tokens_floor_est"] == 0

    def test_over_cap_true_when_tokens_exceed_cap(self):
        cf = _cf()
        # Pass a tiny cap (1) to force over_cap.
        r = _rule(rule_id="X-001", always_on=True,
                  trigger="This trigger is longer than one token.",
                  statement="This statement is also longer than one token.")
        result = cf.always_on_bundle_cost([r], cap=1)
        assert result["over_cap"] is True

    def test_over_cap_false_when_tokens_within_cap(self):
        cf = _cf()
        # Empty trigger+statement -> 0 tokens, always within cap.
        r = _rule(rule_id="Y-001", always_on=True, trigger="", statement="")
        result = cf.always_on_bundle_cost([r], cap=5000)
        assert result["over_cap"] is False

    def test_basis_label_present(self):
        cf = _cf()
        result = cf.always_on_bundle_cost([], cap=5000)
        assert "basis" in result
        assert result["basis"]  # non-empty string


# ---------------------------------------------------------------------------
# TestCodeShare
# ---------------------------------------------------------------------------

class TestCodeShare:
    def test_fenced_block_in_pass_example_gives_nonzero_share(self):
        cf = _cf()
        rule = _rule(
            pass_example="```python\ndef test_create_order():\n    order = create_order(payload)\n    assert order.id is not None\n```",
        )
        result = cf.code_block_share([rule])
        assert 0.0 < result["code_share"] <= 1.0

    def test_no_fences_gives_zero_code_share(self):
        cf = _cf()
        rule = _rule(
            violation="No fences here, just prose explaining the violation.",
            pass_example="Also no fences, just prose describing the fix.",
        )
        result = cf.code_block_share([rule])
        assert result["code_share"] == 0.0

    def test_empty_list_gives_zero_no_zero_division(self):
        cf = _cf()
        result = cf.code_block_share([])
        assert result["code_share"] == 0.0

    def test_code_share_at_most_one(self):
        """code_share can never exceed 1.0 (code bytes <= body bytes)."""
        cf = _cf()
        big_block = "```python\n" + "x = 1\n" * 100 + "```"
        rule = _rule(pass_example=big_block)
        result = cf.code_block_share([rule])
        assert result["code_share"] <= 1.0


# ---------------------------------------------------------------------------
# TestRankCutCandidates
# ---------------------------------------------------------------------------

class TestRankCutCandidates:
    def _measured_from(self, rules):
        cf = _cf()
        return [cf.measure_rule(r) for r in rules]

    def test_ordered_by_score_descending(self):
        cf = _cf()
        # High overhead rule: lots of body, tiny core.
        r_high = _rule(
            rule_id="HIGH-001",
            trigger="T.",
            statement="S.",
            violation="A" * 500,
            rationale="B" * 500,
        )
        # Low overhead rule: mostly core.
        r_low = _rule(
            rule_id="LOW-001",
            trigger="When writing a very long trigger that dominates the token count.",
            statement="A very long statement that also contributes heavily to the core byte count.",
            violation="",
            rationale="",
        )
        measured = self._measured_from([r_low, r_high])
        result = cf.rank_cut_candidates(measured, top=10)
        # HIGH-001 must appear before LOW-001 (higher overhead score).
        ids = [c["rule_id"] for c in result]
        assert ids.index("HIGH-001") < ids.index("LOW-001")

    def test_deterministic_tie_breaking_by_rule_id(self):
        cf = _cf()
        # Two rules with identical content (same score) -- sorted by rule_id alphabetically.
        r_a = _rule(rule_id="ZZZ-001", violation="X" * 100, rationale="Y" * 100)
        r_b = _rule(rule_id="AAA-001", violation="X" * 100, rationale="Y" * 100)
        measured = self._measured_from([r_a, r_b])
        result1 = cf.rank_cut_candidates(measured, top=10)
        result2 = cf.rank_cut_candidates(list(reversed(measured)), top=10)
        assert [c["rule_id"] for c in result1] == [c["rule_id"] for c in result2]
        # Among ties, alphabetically first rule_id should come first.
        ids = [c["rule_id"] for c in result1]
        assert ids.index("AAA-001") < ids.index("ZZZ-001")

    def test_every_candidate_has_tag_key(self):
        cf = _cf()
        rules = [_rule(rule_id=f"R-{i:03}", violation="X" * 50) for i in range(5)]
        measured = self._measured_from(rules)
        result = cf.rank_cut_candidates(measured, top=5)
        for candidate in result:
            assert "tag" in candidate
            assert candidate["tag"]  # non-empty

    def test_top_n_respected(self):
        cf = _cf()
        rules = [_rule(rule_id=f"R-{i:03}", violation="X" * 50) for i in range(10)]
        measured = self._measured_from(rules)
        result = cf.rank_cut_candidates(measured, top=3)
        assert len(result) <= 3

    def test_largest_component_is_never_a_reach_field(self):
        """CRITICAL: trigger, statement, applicability_scope must never appear as largest_component."""
        cf = _cf()
        # Construct rules where trigger+statement dominate bytes.
        rules = [
            _rule(
                rule_id=f"REACH-{i:03}",
                trigger="When this trigger is very long and contains many words to dominate byte count.",
                statement="This statement is also very long and contains many descriptive words.",
                violation="short",
                pass_example="",
                enforcement="",
                rationale="",
                edges="",
            )
            for i in range(5)
        ]
        measured = self._measured_from(rules)
        result = cf.rank_cut_candidates(measured, top=10)
        reach_fields = {"trigger", "statement", "applicability_scope"}
        for candidate in result:
            assert candidate["largest_component"] not in reach_fields, (
                f"Reach field '{candidate['largest_component']}' must never be a cut candidate "
                f"(rule {candidate['rule_id']})"
            )

    def test_largest_component_is_one_of_body_fields(self):
        cf = _cf()
        body_fields = {"violation", "pass_example", "enforcement", "rationale", "edges"}
        rule = _rule(violation="A very long violation block " * 20)
        measured = self._measured_from([rule])
        result = cf.rank_cut_candidates(measured, top=5)
        for candidate in result:
            assert candidate["largest_component"] in body_fields


# ---------------------------------------------------------------------------
# TestScorecardShape
# ---------------------------------------------------------------------------

class TestScorecardShape:
    def test_required_keys_present(self, tmp_bible: Path):
        cf = _cf()
        card = cf.scorecard(str(tmp_bible))
        for key in (
            "rule_count",
            "total_tokens_floor_est",
            "always_on_bundle",
            "code_block_share",
            "per_domain",
            "cut_candidates",
            "basis",
            "measure_only",
        ):
            assert key in card, f"Missing key: {key!r}"

    def test_basis_contains_bytes_over_4(self, tmp_bible: Path):
        cf = _cf()
        card = cf.scorecard(str(tmp_bible))
        assert "bytes/4" in card["basis"]

    def test_measure_only_warns_about_ab(self, tmp_bible: Path):
        cf = _cf()
        card = cf.scorecard(str(tmp_bible))
        measure_only = card["measure_only"].lower()
        assert "a/b" in measure_only or "efficacy" in measure_only

    def test_rule_count_positive(self, tmp_bible: Path):
        cf = _cf()
        card = cf.scorecard(str(tmp_bible))
        assert card["rule_count"] >= 1

    def test_total_tokens_floor_est_positive(self, tmp_bible: Path):
        cf = _cf()
        card = cf.scorecard(str(tmp_bible))
        assert card["total_tokens_floor_est"] > 0

    def test_per_domain_keyed_by_domain(self, tmp_bible: Path):
        cf = _cf()
        card = cf.scorecard(str(tmp_bible))
        assert isinstance(card["per_domain"], dict)
        for domain_key, agg in card["per_domain"].items():
            assert "rule_count" in agg
            assert "tokens_floor_est" in agg
            assert "mean_overhead_pct" in agg

    def test_cut_candidates_is_list(self, tmp_bible: Path):
        cf = _cf()
        card = cf.scorecard(str(tmp_bible))
        assert isinstance(card["cut_candidates"], list)

    def test_always_on_bundle_has_basis(self, tmp_bible: Path):
        cf = _cf()
        card = cf.scorecard(str(tmp_bible))
        assert "basis" in card["always_on_bundle"]


# ---------------------------------------------------------------------------
# TestCanary
# ---------------------------------------------------------------------------

class TestCanary:
    def test_empty_dir_raises_corpus_footprint_error(self, tmp_path: Path):
        cf = _cf()
        with pytest.raises(cf.CorpusFootprintError) as exc_info:
            cf.scorecard(str(tmp_path))
        assert str(exc_info.value)  # non-empty message

    def test_nonexistent_domain_raises_corpus_footprint_error(self, tmp_bible: Path):
        cf = _cf()
        with pytest.raises(cf.CorpusFootprintError) as exc_info:
            cf.scorecard(str(tmp_bible), domain="nonexistent")
        assert "nonexistent" in str(exc_info.value)

    def test_load_corpus_empty_dir_raises(self, tmp_path: Path):
        cf = _cf()
        with pytest.raises(cf.CorpusFootprintError):
            cf.load_corpus(str(tmp_path))

    def test_load_corpus_returns_only_rule_nodes(self, tmp_bible: Path):
        cf = _cf()
        rules = cf.load_corpus(str(tmp_bible))
        for r in rules:
            assert r.get("node_type") == "Rule"


# ---------------------------------------------------------------------------
# TestCli
# ---------------------------------------------------------------------------

class TestCli:
    def test_exit_0_and_measure_only_banner_present(self, tmp_bible: Path):
        from typer.testing import CliRunner
        if SKILL_ROOT not in sys.path:
            sys.path.insert(0, SKILL_ROOT)
        from writ.cli import app

        result = CliRunner().invoke(app, ["corpus-footprint", str(tmp_bible)])
        assert result.exit_code == 0, (
            f"Expected exit 0, got {result.exit_code}. Output:\n{result.output}"
        )
        # render_text must include a propose/A/B/WASTE marker.
        assert any(
            marker in result.output
            for marker in ("propose", "A/B", "WASTE", "measure-only", "PROPOSE")
        ), f"Measure-only banner not found in output:\n{result.output}"

    def test_exit_2_on_empty_bible_dir(self, tmp_path: Path):
        from typer.testing import CliRunner
        if SKILL_ROOT not in sys.path:
            sys.path.insert(0, SKILL_ROOT)
        from writ.cli import app

        result = CliRunner().invoke(app, ["corpus-footprint", str(tmp_path)])
        assert result.exit_code == 2, (
            f"Expected exit 2 on canary failure, got {result.exit_code}."
        )
        # Check that the canary message appears in either stderr or mixed output.
        try:
            err = result.stderr or ""
        except (ValueError, Exception):
            err = ""
        assert "CORPUS CANARY FAILED" in (result.output + err), (
            f"Expected 'CORPUS CANARY FAILED' in output. Got:\n{result.output + err}"
        )
