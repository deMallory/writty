"""Data-safety helpers for the destructive benchmarks.

The scale/traversal benchmarks call ``db.clear_all()`` against the LIVE Neo4j to build a
synthetic corpus. Two hazards follow, both fixed here:

1. **Permanent loss.** Graph-first nodes (``provenance`` in ``proposed`` /
   ``graduation_pending``) have NO markdown home -- ``clear_all()`` destroys them with no
   way to rebuild. ``assert_safe_to_wipe`` refuses to run while any exist.
2. **Incomplete restore.** The old teardowns recreated only ``Rule`` nodes, silently
   dropping the methodology graph (Skill, Playbook, Technique, ...). ``restore_full_corpus``
   re-imports the WHOLE ``bible/`` corpus so a benchmark run never leaves the graph empty
   or Rule-only.

Use both: guard before the first wipe, restore in the ``finally``.
"""
from __future__ import annotations

from pathlib import Path

from writ.graph.methodology_ingest import ingest_path

BIBLE_DIR = Path(__file__).resolve().parent.parent / "bible"

# Graph-first provenance states have no markdown home; clearing them is irreversible.
_GRAPH_FIRST = ("proposed", "graduation_pending")


async def assert_safe_to_wipe(db) -> None:
    """Raise if the live graph holds graph-first nodes that clear_all() would destroy
    permanently. Call ONCE before the first destructive clear_all()."""
    async with db._driver.session(database=db._database) as session:
        result = await session.run(
            "MATCH (n) WHERE n.provenance IN $states RETURN count(n) AS c",
            states=list(_GRAPH_FIRST),
        )
        count = (await result.single())["c"]
    if count:
        raise RuntimeError(
            f"Refusing to run a destructive benchmark: {count} graph-first node(s) "
            f"(provenance in {_GRAPH_FIRST}) have no markdown home, so clear_all() would "
            "destroy them permanently. Promote (writ promote-candidate) or remove them first."
        )


async def restore_full_corpus(db) -> None:
    """Wipe synthetic benchmark data and restore the FULL bible/ corpus (Rule +
    methodology), so a benchmark never leaves the live graph empty or Rule-only."""
    await db.clear_all()
    await ingest_path(BIBLE_DIR, db)
