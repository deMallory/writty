"""Text-level pins for the fix-loop escalation, worker status contracts and
orchestrator dispatch policy.

Reads writ-corpus.cypher and agents/*.md as text. Never contacts Neo4j, so it
runs under --noconftest. One class per commit: TestFixLoopEscalation (A),
TestStatusContracts (B), TestDispatchPolicy (C).
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from writ.graph.dump import cypher_literal

REPO = Path(__file__).resolve().parent.parent
CORPUS = REPO / "writ-corpus.cypher"
AGENTS = REPO / "agents"

EM_DASH = "—"
SPACED_DOUBLE_HYPHEN = " -- "

ROLE_AGENT_FILES = {
    "ROL-EXPLORER-001": "writ-explorer.md",
    "ROL-IMPLEMENTER-001": "writ-implementer.md",
    "ROL-PLANNER-001": "writ-planner.md",
    "ROL-REVIEWER-001": "writ-reviewer.md",
    "ROL-TEST-WRITER-001": "writ-test-writer.md",
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _corpus_lines() -> list[str]:
    return CORPUS.read_text(encoding="utf-8").splitlines()


def find_create_line(label: str, id_key: str, node_id: str) -> str:
    """Return the single `CREATE (:<Label>` line whose id property is node_id."""
    needle = f"{id_key}: '{node_id}'"
    prefix = f"CREATE (:{label} "
    hits = [ln for ln in _corpus_lines() if ln.startswith(prefix) and needle in ln]
    assert len(hits) == 1, f"expected exactly one {label} line for {node_id}, got {len(hits)}"
    return hits[0]


_ESCAPES = {"\\": "\\", "'": "'", "n": "\n", "r": "\r", "t": "\t"}


def _decode(raw: str) -> str:
    out: list[str] = []
    i = 0
    while i < len(raw):
        ch = raw[i]
        if ch == "\\" and i + 1 < len(raw):
            nxt = raw[i + 1]
            out.append(_ESCAPES.get(nxt, "\\" + nxt))
            i += 2
        else:
            out.append(ch)
            i += 1
    return "".join(out)


def extract_prop(line: str, key: str) -> str:
    """Extract and decode a Cypher single-quoted property (inverse of cypher_literal)."""
    m = re.search(rf"(?:\{{|, ){re.escape(key)}: '((?:[^'\\]|\\.)*)'", line)
    assert m, f"property {key!r} not found"
    return _decode(m.group(1))


def extract_list_prop(line: str, key: str) -> list[str]:
    m = re.search(rf"(?:\{{|, ){re.escape(key)}: \[([^\]]*)\]", line)
    assert m, f"list property {key!r} not found"
    return re.findall(r"'((?:[^'\\]|\\.)*)'", m.group(1))


def agent_body(filename: str) -> str:
    """Text after the frontmatter and one blank line."""
    text = (AGENTS / filename).read_text(encoding="utf-8")
    assert text.startswith("---\n")
    end = text.index("\n---\n", 4)
    rest = text[end + len("\n---\n"):]
    assert rest.startswith("\n")
    return rest[1:]


def norm(s: str) -> str:
    return " ".join(s.split())


def section_from(text: str, heading: str) -> str:
    """Text from `heading` to the next same-level '## ' heading (or the end)."""
    start = text.index(heading)
    nxt = text.find("\n## ", start + len(heading))
    return text[start:] if nxt == -1 else text[start:nxt]


def assert_style_clean(text: str) -> None:
    assert EM_DASH not in text
    assert SPACED_DOUBLE_HYPHEN not in text


def fixloop_line() -> str:
    return find_create_line("Rule", "rule_id", "ENF-PROC-FIXLOOP-001")


def sdd_line() -> str:
    return find_create_line("Playbook", "playbook_id", "PBK-PROC-SDD-001")


def orch_line() -> str:
    return find_create_line("Playbook", "playbook_id", "PBK-PROC-ORCHESTRATOR-001")


def role_line(role_id: str) -> str:
    return find_create_line("SubagentRole", "role_id", role_id)


def role_template(role_id: str) -> str:
    return extract_prop(role_line(role_id), "prompt_template")


@pytest.fixture(scope="module")
def fixloop() -> dict[str, str]:
    ln = fixloop_line()
    return {k: extract_prop(ln, k) for k in ("statement", "body", "evidence", "pass_example", "rationale", "violation")}


@pytest.fixture(scope="module")
def sdd() -> dict[str, str]:
    ln = sdd_line()
    return {"statement": extract_prop(ln, "statement"), "body": extract_prop(ln, "body")}


@pytest.fixture(scope="module")
def orch() -> dict[str, str]:
    ln = orch_line()
    return {
        "statement": extract_prop(ln, "statement"),
        "body": extract_prop(ln, "body"),
        "rationale": extract_prop(ln, "rationale"),
    }


# ---------------------------------------------------------------------------
# Helper self-checks and byte-level parity
# ---------------------------------------------------------------------------


class TestHelpers:
    def test_decode_inverts_cypher_literal(self):
        sample = "a\\b 'q' \n line\r\t end\\"
        literal = cypher_literal(sample)
        assert literal.startswith("'") and literal.endswith("'")
        assert _decode(literal[1:-1]) == sample

    def test_extract_prop_finds_first_property_after_brace(self):
        line = "CREATE (:X {evidence: 'a\\'b', other: 'c'})"
        assert extract_prop(line, "evidence") == "a'b"
        assert extract_prop(line, "other") == "c"


class TestAgentCorpusParity:
    @pytest.mark.parametrize("role_id", sorted(ROLE_AGENT_FILES))
    def test_agent_body_is_substring_of_role_create_line(self, role_id):
        body = agent_body(ROLE_AGENT_FILES[role_id])
        assert f"prompt_template: {cypher_literal(body)}" in role_line(role_id)


# ---------------------------------------------------------------------------
# Commit A: fix-loop escalation by ownership and evidence
# ---------------------------------------------------------------------------


class TestFixLoopEscalation:
    def test_no_more_capable_model_or_capability_bump_anywhere(self):
        texts = [CORPUS.read_text(encoding="utf-8")]
        texts += [p.read_text(encoding="utf-8") for p in sorted(AGENTS.glob("*.md"))]
        for text in texts:
            low = text.lower()
            assert "more capable model" not in low
            assert "more capable\nmodel" not in low
            assert "capability bump" not in low

    def test_statement_says_fresh_implementer_same_model_full_evidence(self, fixloop):
        st = norm(fixloop["statement"])
        assert "rounds 4-5 dispatch a FRESH implementer on the same model" in st
        for item in ("brief or plan path", "failing test output", "every open finding", "prior fix reports"):
            assert item in st

    def test_body_rounds_4_5_bullet_new_wording(self, fixloop):
        body = norm(fixloop["body"])
        assert "**Rounds 4-5.** Escalate by ownership and evidence, not by model" in body
        assert "dispatch a FRESH `writ-implementer` on the same model" in body
        assert "the brief or plan path, the failing test output, every open review finding verbatim, and every prior fix report" in body
        assert "a prior implementer attempted this N times; you own it now" in body
        assert "fresh eyes on the whole record are the move" in body

    def test_fable_only_when_user_explicitly_asks_in_statement_and_body(self, fixloop):
        assert "Fable only when the user explicitly asks" in norm(fixloop["statement"])
        body = norm(fixloop["body"])
        assert "Override the model to Fable (`model: fable` on the dispatch) only when the user explicitly asks" in body

    def test_rationale_evidence_violation_pass_example_rewritten(self, fixloop):
        assert "a context and ownership problem, not a diligence problem and not a model-strength problem" in norm(fixloop["rationale"])
        assert "no per-dispatch effort" in norm(fixloop["evidence"])
        assert "writ-implementer already runs opus/high" in norm(fixloop["evidence"])
        assert "you own it now" in norm(fixloop["pass_example"])
        assert "raising the model without the user asking" in norm(fixloop["violation"])

    def test_five_round_cap_and_dispositions_unchanged(self, fixloop):
        body = norm(fixloop["body"])
        st = norm(fixloop["statement"])
        assert "five rounds per task" in st
        assert "Rounds 1-3" in body
        assert "Adjudicate ONLY at the cap" in body
        assert "contestable" in body
        assert "load-bearing" in body
        assert "## Not the 3-fix rule" in fixloop["body"]

    def test_ant_proc_debug_distinction_and_trigger_keywords_kept(self, fixloop):
        assert "ANT-PROC-DEBUG-001" in fixloop["body"]
        keywords = extract_list_prop(fixloop_line(), "trigger_keywords")
        for kw in ("fix loop", "re-review", "review findings", "escalate", "adjudicate"):
            assert kw in keywords

    def test_sdd_blocked_handling_new_wording(self, sdd):
        body = norm(sdd["body"])
        assert "reasoning dead end -> rule on the approach yourself (or ask the user) and re-dispatch a fresh implementer with the ruling and the evidence so far" in body
        assert "task too large -> split it" in body
        assert "plan is wrong -> return to planning" in body

    def test_sdd_no_unchanged_redispatch_sentence(self, sdd):
        body = norm(sdd["body"])
        assert "Never re-dispatch a task unchanged: change the context (the missing facts, a ruling, the prior evidence) or the task size" in body
        assert "Raise the model only when the user explicitly asks." in body
        assert "change the context, the model, or the task size" not in body

    def test_sdd_fix_loop_section_new_wording(self, sdd):
        sec = norm(section_from(sdd["body"], "## The fix loop"))
        assert "Per `ENF-PROC-FIXLOOP-001`" in sec
        assert "bounded at five rounds per task" in sec
        assert "rounds 4-5 dispatch a fresh implementer on the same model carrying the full evidence" in sec
        assert "a prior implementer attempted this N times; you own it now" in sec
        assert "Fable only when the user explicitly asks." in sec
        assert "stop re-dispatching" in sec

    def test_sdd_body_keeps_statuses_and_terms(self, sdd):
        body = sdd["body"]
        for token in ("DONE", "DONE_WITH_CONCERNS", "BLOCKED", "NEEDS_CONTEXT", "unchanged", "re-dispatch", "ENF-PROC-FIXLOOP-001"):
            assert token in body

    def test_implementer_template_new_escalation_parenthetical(self):
        tpl = role_template("ROL-IMPLEMENTER-001")
        assert "(more context, a ruling from the\ncontroller, or a smaller task)" in tpl
        assert "more context, a ruling from the controller, or a smaller task" in norm(tpl)

    def test_implementer_template_keeps_blocked_linebreak(self):
        assert "BLOCKED or\nNEEDS_CONTEXT" in role_template("ROL-IMPLEMENTER-001")

    def test_agent_implementer_body_matches_new_wording(self):
        body = agent_body("writ-implementer.md")
        assert "a ruling from the controller" in norm(body)
        assert "BLOCKED or\nNEEDS_CONTEXT" in body

    def test_rewritten_fixloop_text_is_style_clean(self, fixloop):
        assert_style_clean(fixloop["statement"])
        bullet = section_from(fixloop["body"], "**Rounds 4-5.**")
        rounds_only = bullet.split("\n\n")[0]
        assert_style_clean(rounds_only)
        assert_style_clean(fixloop["evidence"])
        assert_style_clean(fixloop["pass_example"])
        assert_style_clean(fixloop["violation"])

    def test_sdd_fix_loop_section_is_style_clean(self, sdd):
        assert_style_clean(section_from(sdd["body"], "## The fix loop"))


# ---------------------------------------------------------------------------
# Commit B: status contracts
# ---------------------------------------------------------------------------

_EXPLORER_STATUSES = ("COMPLETE", "INSUFFICIENT_CONTEXT", "REQUIRES_REASONING", "CONFLICTING_EVIDENCE")
_TEST_WRITER_STATUSES = ("COMPLETE", "INSUFFICIENT_CONTEXT", "REQUIRES_REQUIREMENT_DECISION", "CONFLICTING_EVIDENCE")

_REVIEWER_STATUS_LINE = '"status": "approved" | "changes_requested" | "insufficient_context" | "conflicting_evidence",'


class TestStatusContracts:
    def test_explorer_report_status_section(self):
        tpl = role_template("ROL-EXPLORER-001")
        assert "## Report status" in tpl
        sec = section_from(tpl, "## Report status")
        for st in _EXPLORER_STATUSES:
            assert f"- **{st}**:" in sec
        assert "REQUIRES_REQUIREMENT_DECISION" not in tpl
        assert "End every report with exactly one status so the controller never has to guess" in norm(sec)
        assert "The remedy is more facts, not a stronger model." in norm(sec)
        assert "Cite both sides; do not pick one." in norm(sec)

    def test_explorer_section_follows_only_observe(self):
        tpl = role_template("ROL-EXPLORER-001")
        assert tpl.index("Only observe and report.") < tpl.index("## Report status")

    def test_test_writer_report_status_section(self):
        tpl = role_template("ROL-TEST-WRITER-001")
        assert "## Report status" in tpl
        sec = section_from(tpl, "## Report status")
        for st in _TEST_WRITER_STATUSES:
            assert f"- **{st}**:" in sec
        assert "REQUIRES_REASONING" not in tpl
        n = norm(sec)
        assert "End every dispatch with exactly one status so the controller never has to guess" in n
        assert "Never invent behavior into a test" in n
        assert "write no test for that capability until the decision is made" in n
        assert "list the test files written and the capabilities each one covers" in n

    def test_test_writer_section_after_post_write_verification(self):
        tpl = role_template("ROL-TEST-WRITER-001")
        assert tpl.index("Post-write verification") < tpl.index("## Report status")

    def test_reviewer_status_line_exact(self):
        tpl = role_template("ROL-REVIEWER-001")
        assert _REVIEWER_STATUS_LINE in tpl
        assert '"status": "approved" | "changes_requested",' not in tpl

    def test_reviewer_shape_otherwise_unchanged(self):
        tpl = role_template("ROL-REVIEWER-001")
        assert '"spec_compliance"' in tpl
        for key in ('"critical"', '"important"', '"minor"'):
            assert key in tpl
        assert "Output JSON only" in tpl
        assert "If `status` is `approved`, `critical` and `important` must be empty" in norm(tpl)

    def test_reviewer_first_rule_says_changes_requested_on_spec_fail(self):
        n = norm(role_template("ROL-REVIEWER-001"))
        assert "If `spec_compliance` is `fail` because the diff misses the spec, set `status` to `changes_requested`" in n

    def test_reviewer_new_status_rules_instruct_fail_and_critical_entries(self):
        n = norm(role_template("ROL-REVIEWER-001"))
        assert "`insufficient_context`: you could not finish a pass because something it needs was not provided" in n
        assert "Set `spec_compliance` to `fail`, since compliance was not established, and put each missing fact in `critical` as its own entry" in n
        assert "The controller retrieves the facts and re-dispatches." in n
        assert "`conflicting_evidence`: the spec contradicts itself or the code it references, so compliance cannot be judged." in n
        assert "Set `spec_compliance` to `fail` and put each conflict in `critical`, citing both sides." in n
        assert "The controller rules or asks the user." in n

    def test_reviewer_severity_critical_gains_incomplete_review(self):
        assert "a review that could not be completed" in norm(role_template("ROL-REVIEWER-001"))

    def test_implementer_four_statuses_unchanged(self):
        tpl = role_template("ROL-IMPLEMENTER-001")
        for st in ("DONE", "DONE_WITH_CONCERNS", "BLOCKED", "NEEDS_CONTEXT"):
            assert st in tpl
        assert "COMPLETE" not in tpl
        assert "REQUIRES_REASONING" not in tpl

    def test_agents_carry_the_new_status_sections(self):
        assert "## Report status" in agent_body("writ-explorer.md")
        assert "## Report status" in agent_body("writ-test-writer.md")
        assert _REVIEWER_STATUS_LINE in agent_body("writ-reviewer.md")

    def test_new_status_text_is_style_clean(self):
        assert_style_clean(section_from(role_template("ROL-EXPLORER-001"), "## Report status"))
        assert_style_clean(section_from(role_template("ROL-TEST-WRITER-001"), "## Report status"))
        tpl = role_template("ROL-REVIEWER-001")
        new_lines = [
            ln for ln in tpl.splitlines()
            if "`insufficient_context`:" in ln or "`conflicting_evidence`:" in ln or _REVIEWER_STATUS_LINE in ln
        ]
        assert len(new_lines) >= 3
        for ln in new_lines:
            assert_style_clean(ln)


# ---------------------------------------------------------------------------
# Commit C: dispatch policy
# ---------------------------------------------------------------------------


def _all_roles() -> list[tuple[str, str]]:
    out = []
    for rid in ROLE_AGENT_FILES:
        ln = role_line(rid)
        out.append((rid, extract_prop(ln, "name")))
    return out


def _named(text: str, token: str) -> bool:
    return re.search(rf"(?<![\w-]){re.escape(token)}(?![\w-])", text, re.IGNORECASE) is not None


class TestDispatchPolicy:
    def _policy(self, orch) -> str:
        assert "## Dispatch policy" in orch["body"]
        return norm(section_from(orch["body"], "## Dispatch policy"))

    def test_policy_section_exists_after_existing_bullets(self, orch):
        body = orch["body"]
        assert "## Dispatch policy" in body
        assert body.index("## Dispatch policy") > 0

    def test_do_it_directly_when_small(self, orch):
        p = self._policy(orch)
        assert "**Do it directly when it is small.**" in p
        assert "Prefer deterministic tools (grep, rg, git, the test suite)" in p
        assert "Delegate only when a worker isolates heavy context, runs independent work in parallel, or the role's constraints matter" in p
        assert "(read-only, write scope, a fresh context)" in p

    def test_facts_before_strength(self, orch):
        p = self._policy(orch)
        assert "**Facts before strength.**" in p
        assert "retrieve the fact before raising model strength" in p
        assert "Never raise the model to compensate for missing context." in p

    def test_per_dispatch_model_override_rules(self, orch):
        p = self._policy(orch)
        assert "**Per-dispatch model override.**" in p
        assert "`model` override (haiku, sonnet, opus, fable); effort stays the role's pin" in p
        assert "Haiku only for a bounded lookup or extraction with a structured return" in p
        assert "never for deciding what matters" in p
        assert "Sonnet is the default for the explorer, test-writer and reviewer roles" in p
        assert "Opus for the planner and implementer roles, and for a conflicting or high-consequence judgment" in p
        assert "Fable only when the user explicitly asks." in p

    def test_routes_missing_context_to_retrieval_not_model(self, orch):
        p = self._policy(orch)
        assert "INSUFFICIENT_CONTEXT, NEEDS_CONTEXT, or a reviewer `insufficient_context`: retrieve the missing facts the worker named and re-dispatch; do not escalate the model." in p

    def test_routes_judgment_statuses_to_controller_or_user(self, orch):
        p = self._policy(orch)
        assert "REQUIRES_REASONING, REQUIRES_REQUIREMENT_DECISION, CONFLICTING_EVIDENCE, or a reviewer `conflicting_evidence`: the controller decides or asks the user." in p
        assert "A stronger model (opus) may be used for that one judgment; the worker is then re-dispatched with the ruling on its own model." in p

    def test_routes_complete_and_remaining_statuses(self, orch):
        p = self._policy(orch)
        assert "**Route on the returned status.**" in p
        assert "COMPLETE, DONE, or a reviewer `approved`: verify independently, then proceed." in p
        assert "DONE_WITH_CONCERNS and BLOCKED route per `PBK-PROC-SDD-001`; review rounds per `ENF-PROC-FIXLOOP-001`." in p

    def test_policy_never_names_reviewer_role_identifiers(self, orch):
        p = section_from(orch["body"], "## Dispatch policy")
        assert not _named(p, "writ-reviewer")
        assert not _named(p, "ROL-REVIEWER-001")
        assert "reviewer" in p

    @pytest.mark.parametrize("which", ["orch", "sdd"])
    def test_prose_parity_text_mirror(self, which, orch, sdd):
        if which == "orch":
            line, data, pid = orch_line(), orch, "PBK-PROC-ORCHESTRATOR-001"
        else:
            line, data, pid = sdd_line(), sdd, "PBK-PROC-SDD-001"
        dispatched = set(extract_list_prop(line, "dispatched_roles"))
        assert dispatched, pid
        text = f"{data['statement']}\n{data['body']}"
        for role_id, name in _all_roles():
            named = _named(text, role_id) or (bool(name) and _named(text, name))
            if role_id in dispatched:
                assert named, f"{pid} dispatches {role_id} but never names it"
            else:
                assert not named, f"{pid} names {role_id} without dispatching it"

    def test_orchestrator_statement_still_names_ranked_channel(self, orch):
        assert "ranked" in orch["statement"].lower()

    def test_orchestrator_statement_and_rationale_have_no_tilde(self, orch):
        assert "~" not in orch["statement"]
        assert "~" not in orch["rationale"]

    def test_orchestrator_body_never_names_claude_hooks_dir(self, orch):
        assert ".claude/hooks/" not in orch["body"]

    def test_sdd_routes_incomplete_reviewer_verdicts(self, sdd):
        n = norm(sdd["body"])
        assert "A reviewer verdict of `insufficient_context` or `conflicting_evidence` is not a pass" in n
        assert "route it per the status routing in `PBK-PROC-ORCHESTRATOR-001`" in n
        assert "(retrieve the missing facts, or rule on the conflict), then re-review." in n

    def test_sdd_routing_sentence_follows_step_4(self, sdd):
        body = sdd["body"]
        assert body.index("A reviewer verdict of `insufficient_context`") > body.index("## Per task")
        assert body.index("A reviewer verdict of `insufficient_context`") < body.index("## The fix loop")

    def test_dispatch_policy_section_is_style_clean(self, orch):
        assert_style_clean(section_from(orch["body"], "## Dispatch policy"))
