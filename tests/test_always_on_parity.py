"""Always-on filter parity (#N2): turning the filter ON must not strand any rule.

Every always-on/injection rule must be reachable via the prompt path (universal/
empty scope) OR the write path (write/bash scope, matched by its own
trigger_keywords). This harness caught ENF-COMMS-OUTPUT-001 being stranded
(empty scope + spurious trigger_keywords gated it out of the prompt path).

Requires a live graph; skips if Neo4j is unreachable.
"""
from __future__ import annotations

import pytest
import pytest_asyncio

from writ.config import get_neo4j_password, get_neo4j_uri, get_neo4j_user
from writ.graph.db import Neo4jConnection
from writ.retrieval.always_on_filter import select_always_on
from writ.server import INJECTION_RULE_WHERE

CLEAN_WRITES = [
    "def add(a, b):\n    return a + b",
    "console.log('rendering header component')",
    "# Updated the README with install steps",
    "<div className='card'><h2>Title</h2></div>",
    "SELECT name FROM products WHERE active = 1",
]


@pytest_asyncio.fixture()
async def injection_rules():
    db = Neo4jConnection(get_neo4j_uri(), get_neo4j_user(), get_neo4j_password())
    query = f"""
        MATCH (r:Rule) WHERE {INJECTION_RULE_WHERE}
        RETURN r.rule_id AS rule_id, r.applicability_scope AS applicability_scope,
               r.trigger_keywords AS trigger_keywords
    """
    try:
        async with db._driver.session(database=db._database) as s:
            rows = [r.data() async for r in await s.run(query)]
    except Exception:
        pytest.skip("Neo4j unreachable")
    finally:
        await db._driver.close()
    if not rows:
        pytest.skip("no injection rules in graph")
    return [{"rule_id": r["rule_id"],
             "applicability_scope": r.get("applicability_scope") or [],
             "trigger_keywords": r.get("trigger_keywords") or []} for r in rows]


def _reachable_ids(rules: list[dict]) -> set[str]:
    """Every rule the filter can deliver: prompt-active, plus write-scoped rules
    reached by a representative write containing their first keyword."""
    reachable = {r["rule_id"] for r in select_always_on(rules, "prompt", "")}
    for r in rules:
        if not any(sc in ("write", "bash") for sc in r["applicability_scope"]):
            continue
        kws = r["trigger_keywords"]
        ctx = kws[0] if kws else ""
        if r["rule_id"] in {x["rule_id"] for x in select_always_on(rules, "write", ctx)}:
            reachable.add(r["rule_id"])
    return reachable


@pytest.mark.asyncio
async def test_no_injection_rule_is_stranded(injection_rules):
    reachable = _reachable_ids(injection_rules)
    stranded = [r["rule_id"] for r in injection_rules if r["rule_id"] not in reachable]
    assert stranded == [], f"filter would strand these rules: {stranded}"


@pytest.mark.asyncio
async def test_output_quality_rule_stays_prompt_active(injection_rules):
    # Regression guard: ENF-COMMS-OUTPUT-001 is universal -- it must inject every
    # turn, not be keyword-gated off the prompt path.
    ids = [r["rule_id"] for r in injection_rules]
    if "ENF-COMMS-OUTPUT-001" not in ids:
        pytest.skip("ENF-COMMS-OUTPUT-001 not in this corpus")
    prompt_active = {r["rule_id"] for r in select_always_on(injection_rules, "prompt", "")}
    assert "ENF-COMMS-OUTPUT-001" in prompt_active


@pytest.mark.asyncio
async def test_clean_writes_do_not_overmatch(injection_rules):
    prompt_active = {r["rule_id"] for r in select_always_on(injection_rules, "prompt", "")}
    for w in CLEAN_WRITES:
        write_only = [x["rule_id"] for x in select_always_on(injection_rules, "write", w)
                      if x["rule_id"] not in prompt_active]
        assert write_only == [], f"clean write {w[:40]!r} over-matched: {write_only}"
