"""Replay writ-corpus.cypher into the TEST graph (7688), then export every node to OUT.

Run from the writty repo root with the repo venv. Refuses to touch anything but 7688:
the replay wipes its target first (writ/graph/dump.py, import_cypher_dump).
Usage: .venv/bin/python docs/handoff/verify-1.7.3/rebuild_bible.py OUT_DIR
"""
import asyncio
import os
import sys
from pathlib import Path

REPO = Path.cwd()
sys.path.insert(0, str(REPO))

os.environ["WRIT_NEO4J_URI"] = "bolt://localhost:7688"
from tests._graph import apply_isolation_env, targets_production  # noqa: E402

assert apply_isolation_env(os.environ), "isolation opted out"

from writ.config import get_neo4j_password, get_neo4j_uri, get_neo4j_user  # noqa: E402

uri = get_neo4j_uri()
assert uri == "bolt://localhost:7688", uri
assert not targets_production(uri), "resolver says this is production"

from writ.export import export_graph_to_markdown  # noqa: E402
from writ.graph.db import Neo4jConnection  # noqa: E402
from writ.graph.dump import import_cypher_dump  # noqa: E402


async def main(out: Path) -> None:
    assert not out.exists(), f"{out} exists, refusing to write into it"
    db = Neo4jConnection(uri, get_neo4j_user(), get_neo4j_password())
    try:
        replay = await import_cypher_dump(db, (REPO / "writ-corpus.cypher").read_text())
        print("replay:", replay)
        print("export:", await export_graph_to_markdown(db, out))
    finally:
        await db.close()


asyncio.run(main(Path(sys.argv[1])))
