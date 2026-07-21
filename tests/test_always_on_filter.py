"""Applicability-scoped selection for always-on rules (WRIT-BLUEPRINT 3.5).

select_always_on() returns the rules applicable at a given injection point. These assert:
universal rules inject only per-turn (prompt), context rules inject at their scope when a
keyword matches, stop rules inject at stop with no keyword, and a rule with no routing data
fails open to universal (never silently dropped).
"""

from __future__ import annotations

from writ.retrieval.always_on_filter import rule_applies_at, select_always_on


def R(rid, scope, kws=None):
    return {"rule_id": rid, "applicability_scope": scope, "trigger_keywords": kws or []}


UNIVERSAL = R("ENF-COMMS-OUTPUT-001", ["universal"])
SQL = R("SEC-INJ-SQL-001", ["write"], ["sql", "query", "parameterized"])
WORKTREE = R("ENF-PROC-WORKTREE-001", ["bash"], ["git worktree add", "worktree"])
STOP = R("ENF-TEST-001", ["stop"])
NOSCOPE = R("LEGACY-RULE-001", [], [])  # pre-migration -> fail-open universal


class TestRuleAppliesAt:
    def test_universal_injects_at_prompt_only(self):
        assert rule_applies_at(UNIVERSAL, "prompt")
        assert not rule_applies_at(UNIVERSAL, "write", "anything")
        assert not rule_applies_at(UNIVERSAL, "stop")

    def test_write_rule_requires_keyword_match(self):
        assert rule_applies_at(SQL, "write", "building a raw sql string by hand")
        assert not rule_applies_at(SQL, "write", "def add(a, b): return a + b")
        # right keyword, wrong injection point
        assert not rule_applies_at(SQL, "prompt", "write some sql")

    def test_bash_phrase_keyword(self):
        assert rule_applies_at(WORKTREE, "bash", "git worktree add ../wt feature")
        assert not rule_applies_at(WORKTREE, "bash", "git status")

    def test_stop_rule_no_keyword_always_at_stop(self):
        assert rule_applies_at(STOP, "stop")
        assert not rule_applies_at(STOP, "write", "tests")

    def test_empty_scope_fails_open_to_prompt(self):
        assert rule_applies_at(NOSCOPE, "prompt")
        assert not rule_applies_at(NOSCOPE, "write", "x")

    def test_keyword_is_whole_word(self):
        # "query" must not match inside "querystring" (whole-word matcher)
        assert not rule_applies_at(SQL, "write", "parse the querystring param")
        assert rule_applies_at(SQL, "write", "run the query now")


class TestSelectAlwaysOn:
    RULES = [UNIVERSAL, SQL, WORKTREE, STOP, NOSCOPE]

    def test_prompt_point_gets_universal_and_failopen(self):
        ids = [r["rule_id"] for r in select_always_on(self.RULES, "prompt", "hello")]
        assert ids == ["ENF-COMMS-OUTPUT-001", "LEGACY-RULE-001"]

    def test_write_point_only_matching_content_rule(self):
        ids = [r["rule_id"] for r in select_always_on(self.RULES, "write", "a raw sql query here")]
        assert ids == ["SEC-INJ-SQL-001"]

    def test_write_point_no_match_is_empty(self):
        assert select_always_on(self.RULES, "write", "plain prose, no code") == []

    def test_stop_point_only_stop_rules(self):
        ids = [r["rule_id"] for r in select_always_on(self.RULES, "stop")]
        assert ids == ["ENF-TEST-001"]

    def test_order_preserved(self):
        # add a second write rule; output keeps input order
        pii = R("SEC-DATA-PII-001", ["write"], ["log", "email"])
        ids = [r["rule_id"] for r in select_always_on([SQL, pii], "write", "log the email and run a query")]
        assert ids == ["SEC-INJ-SQL-001", "SEC-DATA-PII-001"]
