"""POL-3: production single-source -- redundancy threshold + node-type registry (+ straggler).

C1: the cosine redundancy threshold was defined twice (writ/gate.py and writ/graph/schema.py);
gate.py now imports schema's. C6: the node-type -> id-field / -> model maps were triplicated
across ingest.py / db.py / (models in) schema.py; one canonical registry now lives in schema and
ingest/db derive from it. Straggler: test_inc7's local live_pipeline -> the shared conftest one.

Single-source assertions (always run). Behaviour is guarded by the full suite (ingest/db/
retrieval/gate all run against the consolidated registry + single threshold).

T0.1 update: ALL_NODE_TYPES expanded to 13 (added 'Abstraction' and 'Category') so
test_schema_owns_the_registry acts as the RED gate until schema.py registers both.
"""
from __future__ import annotations

from pathlib import Path

WRIT_ROOT = Path(__file__).resolve().parent.parent
GATE = WRIT_ROOT / "writ" / "gate.py"
INGEST = WRIT_ROOT / "writ" / "graph" / "ingest.py"
INC7 = WRIT_ROOT / "tests" / "test_inc7_tdd_design.py"

# The Neo4j layer is `writ/graph/db.py` OR (after the Wave 2 split) the
# `writ/graph/db/` package. Read whichever exists so this single-source guard is
# layout-agnostic; the id-field derivation lives in the package's _common.py.
_DB_FILE = WRIT_ROOT / "writ" / "graph" / "db.py"
_DB_DIR = WRIT_ROOT / "writ" / "graph" / "db"


def _db_source() -> str:
    if _DB_DIR.is_dir():
        return "\n".join(p.read_text(encoding="utf-8") for p in sorted(_DB_DIR.glob("*.py")))
    return _DB_FILE.read_text(encoding="utf-8")

ALL_NODE_TYPES = {
    "Rule", "Abstraction", "Category",
    "Skill", "Playbook", "Technique", "AntiPattern", "ForbiddenResponse",
    "Phase", "Rationalization", "PressureScenario", "WorkedExample", "SubagentRole",
}


class TestC1RedundancyThresholdSingleSource:
    def test_gate_threshold_is_schema_threshold(self) -> None:
        from writ.gate import REDUNDANCY_THRESHOLD
        from writ.graph.schema import REDUNDANCY_SIMILARITY_THRESHOLD

        assert REDUNDANCY_THRESHOLD == REDUNDANCY_SIMILARITY_THRESHOLD == 0.95

    def test_gate_does_not_redefine_the_literal(self) -> None:
        src = GATE.read_text(encoding="utf-8")
        assert "REDUNDANCY_THRESHOLD = 0.95" not in src, (
            "writ/gate.py still defines its own 0.95 redundancy threshold (should import schema's)"
        )


class TestC6NodeTypeRegistry:
    def test_schema_owns_the_registry(self) -> None:
        from writ.graph import schema

        assert set(schema.NODE_ID_FIELDS) == ALL_NODE_TYPES
        assert set(schema.NODE_TYPE_MODELS) == ALL_NODE_TYPES
        assert set(schema.METHODOLOGY_NODE_TYPES) == ALL_NODE_TYPES - {"Rule"}

    def test_ingest_uses_the_same_objects(self) -> None:
        from writ.graph import ingest, schema

        assert ingest.NODE_ID_FIELDS is schema.NODE_ID_FIELDS, "ingest copies instead of importing"
        assert ingest.NODE_TYPE_MODELS is schema.NODE_TYPE_MODELS

    def test_db_derives_from_the_registry(self) -> None:
        from writ.graph import db, schema

        assert db.METHODOLOGY_NODE_ID_FIELDS == {
            k: v for k, v in schema.NODE_ID_FIELDS.items() if k != "Rule"
        }
        assert db.METHODOLOGY_NODE_LABELS == frozenset(schema.METHODOLOGY_NODE_TYPES)

    def test_no_hardcoded_id_field_literals(self) -> None:
        # The hardcoded id-field MAP entries (e.g. `"Skill": "skill_id"`) must be gone --
        # ingest imports the registry, db derives it by comprehension. A derivation that opens
        # `... = {k: v for ...}` is fine; a literal `"Skill": "skill_id"` mapping is the smell.
        sources = {"ingest.py": INGEST.read_text(encoding="utf-8"), "db": _db_source()}
        for name, src in sources.items():
            assert '"Skill": "skill_id"' not in src, (
                f"{name} still hardcodes the node-type id-field map (should import/derive it)"
            )
        # db derives from the registry rather than re-listing it.
        assert "for k, v in NODE_ID_FIELDS.items()" in sources["db"], (
            "db should derive METHODOLOGY_NODE_ID_FIELDS from the schema registry"
        )


class TestInc7StragglerFolded:
    def test_no_local_live_pipeline_or_asyncio(self) -> None:
        src = INC7.read_text(encoding="utf-8")
        import re

        assert not re.search(r"def\s+live_pipeline\b", src), (
            "test_inc7 still defines a local live_pipeline (should use the shared conftest fixture)"
        )
        assert "import asyncio" not in src, "test_inc7 still imports asyncio (now unused)"
