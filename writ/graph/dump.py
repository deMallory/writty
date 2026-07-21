"""Portable Cypher-script graph dump: render the whole graph as a replay
script, and import that script back into a Neo4j instance.

This is a separate serialization from `writ/export.py`'s markdown round-trip
-- a single-file, human-readable, git-diffable script (the `.sql`-dump
equivalent for Neo4j), not the bible/ markdown tree.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from writ.graph.db import Neo4jConnection

_STAGING_PROPERTY = "_dump_eid"


def cypher_literal(value: object) -> str:
    """Render a Python scalar as a Cypher literal.

    Strings are single-quoted; backslash is escaped first so a value ending
    in a literal backslash cannot swallow the escape sequence that follows.
    """
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, str):
        escaped = (
            value.replace("\\", "\\\\")
            .replace("'", "\\'")
            .replace("\n", "\\n")
            .replace("\r", "\\r")
            .replace("\t", "\\t")
        )
        return f"'{escaped}'"
    if isinstance(value, list):
        return "[" + ", ".join(cypher_literal(v) for v in value) + "]"
    raise TypeError(f"cypher_literal: unsupported type {type(value).__name__}")


def _render_props(props: dict, extra: dict | None = None) -> str:
    merged = dict(props)
    if extra:
        merged.update(extra)
    parts = [f"{k}: {cypher_literal(v)}" for k, v in merged.items() if v is not None]
    return "{" + ", ".join(parts) + "}"


def render_cypher_dump(nodes: list[dict], edges: list[dict]) -> str:
    """Render a full-graph Cypher replay script from `get_all_nodes`/
    `get_all_relationships` output.

    Node order and edge order are sorted by eid so the same graph always
    renders to the same bytes.
    """
    lines: list[str] = []

    for node in sorted(nodes, key=lambda n: n["eid"]):
        label = ":".join(node["labels"])
        props_str = _render_props(node["props"], {_STAGING_PROPERTY: node["eid"]})
        lines.append(f"CREATE (:{label} {props_str});")

    for edge in sorted(edges, key=lambda e: (e["from_eid"], e["to_eid"])):
        props_str = _render_props(edge["props"])
        lines.append(
            f"MATCH (a {{{_STAGING_PROPERTY}: {cypher_literal(edge['from_eid'])}}}), "
            f"(b {{{_STAGING_PROPERTY}: {cypher_literal(edge['to_eid'])}}}) "
            f"CREATE (a)-[:{edge['rel_type']} {props_str}]->(b);"
        )

    lines.append(f"MATCH (n) WHERE n.{_STAGING_PROPERTY} IS NOT NULL REMOVE n.{_STAGING_PROPERTY};")
    return "\n".join(lines) + "\n"


async def import_cypher_dump(db: "Neo4jConnection", text: str) -> dict:
    """Replace the graph's contents with a rendered Cypher dump.

    Wipes `db` first: the dump's CREATE statements are not idempotent (unlike
    `writ import-markdown`'s MERGE-based writes), so replaying into an
    already-populated graph raises a uniqueness constraint violation on any
    node whose business key (e.g. rule_id) already exists. Every real call
    site (bootstrap, CI, the test suite's self-heal hook) wants "make the
    graph exactly match this dump," not "merge this dump into whatever is
    already there" -- so restore semantics belong here, not on every caller.

    Returns {"statements_run": N}.
    """
    await db.clear_all()
    statements = [line for line in text.splitlines() if line.strip()]
    for statement in statements:
        await db.execute(statement)
    return {"statements_run": len(statements)}
