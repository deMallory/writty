"""Phase 2 recall: compile captured Decision records into a budgeted payload.

Recall is NOT retrieval. Decision records are deliberately absent from
RETRIEVABLE_NODE_TYPES (schema.py), so they never enter the 5-stage RAG
pipeline. compile_recall reads them through the dedicated project-scoped query
(db.get_recent_decisions), expands each decision's governing_rule_ids to their
statements in ONE batched call (db.get_rule_statements, PERF-BATCH-001), and
fits the result under a token budget.

Eviction policy (adapted from Jolli's ContextCompiler -- the policy, not the
code): newest decisions first; per decision the PROTECTED fields are
decision_id, title, governing_rule_ids, and the expanded rule statements (the
rule-grounding is Writ's unique value and is never dropped); the EVICTABLE
fields, dropped in order, are rationale first, then each planned_files[].reason.
A decision that will not fit even after dropping all evictable fields is dropped
WHOLE (and, newest-first, so are all older decisions) rather than shipped
without its protected fields.

This module is a pure query: it returns a payload and performs no writes and no
side effects (command/query separation). It contains NO model call -- the
briefing is built mechanically by string formatting.
"""
from __future__ import annotations

from typing import Any

from writ.shared.tokens import estimate_tokens

# Briefing soft cap (~500 tokens). The briefing is the once-per-session line
# block injected into the agent; it stays small enough to be cheap on every
# session without crowding the rule injection.
_BRIEFING_BUDGET = 500
# How many decisions the compact briefing names.
_BRIEFING_DECISIONS = 5


def _decision_token_cost(decision: dict[str, Any], statements: dict[str, str]) -> int:
    """Token cost of a decision's CURRENT (possibly-evicted) fields + its rule
    statements. The protected fields (decision_id, title, governing_rule_ids)
    plus the statements are always counted; rationale and planned_files reasons
    are counted only while present."""
    cost = estimate_tokens(decision.get("title"), decision.get("decision_id"))
    cost += estimate_tokens(decision.get("rationale"), None)
    for rid in decision.get("governing_rule_ids") or []:
        cost += estimate_tokens(rid, statements.get(rid))
    for pf in decision.get("planned_files") or []:
        cost += estimate_tokens(pf.get("path"), pf.get("reason"))
    return cost


def _evict(decision: dict[str, Any]) -> bool:
    """Drop ONE evictable field from `decision` in policy order: rationale
    first, then each planned_files[].reason in list order. Returns True if a field was
    dropped, False when nothing evictable remains (the caller then drops the
    whole decision). Mutates a per-call copy supplied by compile_recall."""
    if decision.get("rationale"):
        decision["rationale"] = ""
        return True
    for pf in decision.get("planned_files") or []:
        if pf.get("reason"):
            pf["reason"] = ""
            return True
    return False


def _build_briefing(kept: list[dict[str, Any]]) -> str:
    """Mechanical (no-LLM) compact briefing: a header plus one line per recent
    decision naming its title and cited rule ids, capped at _BRIEFING_DECISIONS
    and ~_BRIEFING_BUDGET tokens."""
    if not kept:
        return ""
    lines = [
        "[Writ recall: recent decisions on this project "
        "(rule-grounded, read-back from decision memory)]"
    ]
    for d in kept[:_BRIEFING_DECISIONS]:
        rules = ", ".join(d.get("governing_rule_ids") or []) or "no rules cited"
        lines.append(f"- {d.get('title', '(untitled)')} [{rules}]")
        if estimate_tokens("\n".join(lines), None) > _BRIEFING_BUDGET:
            lines.pop()
            break
    return "\n".join(lines)


async def compile_recall(
    db, project: str, *, budget: int = 20000, full: bool = False
) -> dict[str, Any]:
    """Compile the project's recent Decisions into a budgeted recall payload.

    Returns {"briefing": str, "decisions": list[dict]} where each decision dict
    carries decision_id, title, rationale (possibly evicted to ""), planned_files
    (reasons possibly evicted), governing_rule_ids, rule_statements, phase, ts.
    A pure query: no writes, no side effects. `full` is accepted for caller
    symmetry (the CLI uses it to decide what to print) and does not change the
    compiled payload.
    """
    decisions = await db.get_recent_decisions(project, limit=20)

    # One batched rule-statement fetch over the UNION of all governing ids
    # (PERF-BATCH-001): never N+1 per decision per rule.
    all_ids: list[str] = []
    for d in decisions:
        for rid in d.get("governing_rule_ids") or []:
            if rid not in all_ids:
                all_ids.append(rid)
    statements = await db.get_rule_statements(all_ids)

    kept: list[dict[str, Any]] = []
    used = 0
    for src in decisions:  # already newest-first
        d = {
            "decision_id": src.get("decision_id"),
            "title": src.get("title"),
            "rationale": src.get("rationale") or "",
            "planned_files": [dict(pf) for pf in (src.get("planned_files") or [])],
            "governing_rule_ids": list(src.get("governing_rule_ids") or []),
            "phase": src.get("phase"),
            "ts": src.get("ts"),
        }
        # Drop evictable fields until the decision fits in the remaining budget.
        cost = _decision_token_cost(d, statements)
        while used + cost > budget and _evict(d):
            cost = _decision_token_cost(d, statements)
        if used + cost > budget:
            # Will not fit even with all evictable fields gone: drop it whole.
            # Newest-first means everything older is dropped too.
            break
        d["rule_statements"] = {
            rid: statements.get(rid, "")
            for rid in d["governing_rule_ids"]
        }
        kept.append(d)
        used += cost

    return {"briefing": _build_briefing(kept), "decisions": kept}
