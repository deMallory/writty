"""Wave-3 dedup Cycle E: writ/compression/abstractions.py persist-loop helper.

materialize_abstractions_from_artifact (lines 126-181) and write_abstractions_to_graph
(lines 220-247) each hand-roll the same persist shape: delete this project's existing
Abstraction nodes, then for every abstraction dict create an Abstraction node and its
ABSTRACTS edges. The two callers build DIFFERENT node_data dicts (materialize is
tolerant .get-based reads with NO domain key -- the artifact has no domain field;
write_abstractions_to_graph is strict abst[...] access WITH a domain key -- generate_
abstractions always includes one) but the delete+create+edge-loop+count shape itself
is identical. The planned refactor extracts a single

    async def _persist_abstraction_layer(db, entries, project) -> int

where `entries` is a list of (node_data, rule_ids) tuples already built by each
caller, and both functions build their own entries list and delegate to it.

RED-now / GREEN-after-implementation split in THIS file:

  - TestPersistHelper is the actual RED signal for this cycle: the helper does
    not exist yet. Guarded like tests/test_db_run_helper.py's
    TestQueryRunnerHelper -- setup_method fails each test in the class
    individually with a clear reason instead of one opaque collection error
    for the whole file.
  - TestSourceGuards is RED now: materialize_abstractions_from_artifact and
    write_abstractions_to_graph each still inline their own
    `await db.delete_abstractions(project=project)` call and neither calls
    `_persist_abstraction_layer(...)` yet.
  - TestWriteAbstractionsDifferential and TestMaterializeDifferential are
    GREEN now: each defines a FROZEN `_head_*` function that reproduces the
    target function's HEAD (pre-refactor) persist loop verbatim, then runs
    both the frozen copy and the real imported function against fresh
    _FakeDb instances for the same inputs. Today the real function IS this
    inline code, so the call sequences are trivially identical; this is the
    regression net that must stay green once the real function is refactored
    to route through _persist_abstraction_layer -- if the helper silently
    reordered the delete/create/edge sequence, dropped the domain key, or
    changed a default, these differentials would catch it.

ENF-SYS-005 disclosure: every test below drives the target functions (and,
once it exists, _persist_abstraction_layer directly) against a hermetic fake
async db (_FakeDb) -- no real Neo4j, the shared graph is never touched. This
proves the call order (delete -> create_abstraction -> create_abstracts_edge
per rule_id) and the exact node_data/edge argument shapes each function must
preserve. It does NOT and CANNOT prove that delete_abstractions/create_abstraction/
create_abstracts_edge execute correctly against a real Neo4j engine, that the
MERGE-based idempotency claims documented on AbstractionStoreMixin actually
hold, or anything about concurrent-write safety. That coverage is a separate
concern already owned by the live-Neo4j-gated tests in
tests/test_abstraction_artifact.py (TestRunCompressionWritesArtifact,
TestMaterializeFromArtifactIsDepFree), which this file does not duplicate or
replace.

Run: .venv/bin/python -m pytest tests/test_abstraction_persist_helper.py -q
"""
from __future__ import annotations

import asyncio
import inspect
import json

import pytest

import writ.compression.abstractions as abstractions_module
from writ.compression.abstractions import (
    materialize_abstractions_from_artifact,
    write_abstractions_to_graph,
)

try:
    from writ.compression.abstractions import _persist_abstraction_layer  # noqa: E402  # RED until helper exists
    _IMPORT_ERROR = None
except ImportError as exc:  # RED until helper exists
    _persist_abstraction_layer = None
    _IMPORT_ERROR = exc


def _require_persist_helper() -> None:
    """Fail the calling test with a clear reason if the helper isn't importable
    yet (mirrors tests/test_db_run_helper.py's _require_query_runner_module)."""
    if _IMPORT_ERROR is not None:
        pytest.fail(
            "writ.compression.abstractions._persist_abstraction_layer is not "
            f"importable yet: {_IMPORT_ERROR!r}"
        )


# ---------------------------------------------------------------------------
# Hermetic fake async db -- records every call, in order, to a shared list.
# Never opens a socket, never touches the shared Neo4j graph.
# ---------------------------------------------------------------------------


class _FakeDb:
    def __init__(self) -> None:
        self.calls: list[tuple] = []

    async def delete_abstractions(self, project: str = "writ") -> None:
        self.calls.append(("delete", project))

    async def create_abstraction(self, node_data: dict) -> str:
        self.calls.append(("node", dict(node_data)))
        return node_data["abstraction_id"]

    async def create_abstracts_edge(
        self, abstraction_id: str, rule_id: str, project: str = "writ"
    ) -> None:
        self.calls.append(("edge", abstraction_id, rule_id, project))


# ---------------------------------------------------------------------------
# Minimal abstraction-dict factory (TEST-FIXTURE-001): the shape
# write_abstractions_to_graph reads strictly (abst["domain"] etc).
# ---------------------------------------------------------------------------


def _abst(**overrides) -> dict:
    defaults = {
        "abstraction_id": "ABS-TESTING-001",
        "summary": "test summary",
        "domain": "testing",
        "compression_ratio": 2.0,
        "rule_ids": ["RULE-1", "RULE-2"],
    }
    return {**defaults, **overrides}


# ---------------------------------------------------------------------------
# Section 1: the helper itself. RED until _persist_abstraction_layer exists.
# ---------------------------------------------------------------------------


class TestPersistHelper:
    def setup_method(self) -> None:
        _require_persist_helper()

    def test_is_a_coroutine_function(self) -> None:
        assert inspect.iscoroutinefunction(_persist_abstraction_layer)

    def test_entries_with_and_without_rule_ids_produce_expected_call_sequence(
        self,
    ) -> None:
        nd1 = {"abstraction_id": "ABS-1", "summary": "s1"}
        nd2 = {"abstraction_id": "ABS-2", "summary": "s2"}
        proj = "writ"
        fake = _FakeDb()

        result = asyncio.run(
            _persist_abstraction_layer(
                fake, [(nd1, ["r1", "r2"]), (nd2, [])], proj
            )
        )

        assert fake.calls == [
            ("delete", proj),
            ("node", nd1),
            ("edge", "ABS-1", "r1", proj),
            ("edge", "ABS-1", "r2", proj),
            ("node", nd2),
        ]
        assert result == 2

    def test_empty_entries_only_deletes_and_returns_zero(self) -> None:
        proj = "writ"
        fake = _FakeDb()

        result = asyncio.run(_persist_abstraction_layer(fake, [], proj))

        assert fake.calls == [("delete", proj)]
        assert result == 0

    def test_project_threads_through_delete_and_edges(self) -> None:
        nd = {"abstraction_id": "ABS-1", "summary": "s1"}
        fake = _FakeDb()

        asyncio.run(
            _persist_abstraction_layer(fake, [(nd, ["r1"])], "otherproj")
        )

        assert fake.calls == [
            ("delete", "otherproj"),
            ("node", nd),
            ("edge", "ABS-1", "r1", "otherproj"),
        ]


# ---------------------------------------------------------------------------
# Section 2: write_abstractions_to_graph differential. GREEN now (today's
# inline code); must stay green after the _persist_abstraction_layer migration.
# ---------------------------------------------------------------------------


class TestWriteAbstractionsDifferential:
    """FROZEN _head_write reproduces write_abstractions_to_graph's HEAD persist
    loop verbatim (writ/compression/abstractions.py:220-247 at HEAD, before the
    Cycle E refactor). Running both the frozen copy and the real imported
    function against fresh _FakeDb instances for the same abstractions input
    must produce identical call sequences and identical return values.
    """

    @staticmethod
    async def _head_write(db, abstractions: list[dict], project: str = "writ") -> int:
        await db.delete_abstractions(project=project)

        for abst in abstractions:
            node_data = {
                "abstraction_id": abst["abstraction_id"],
                "summary": abst["summary"],
                "domain": abst["domain"],
                "compression_ratio": abst["compression_ratio"],
                "rule_count": len(abst["rule_ids"]),
                "project": project,
            }
            await db.create_abstraction(node_data)
            for rid in abst["rule_ids"]:
                await db.create_abstracts_edge(abst["abstraction_id"], rid, project=project)

        return len(abstractions)

    def _run_both(self, abstractions: list[dict], project: str = "writ"):
        fake_head, fake_real = _FakeDb(), _FakeDb()
        head_result = asyncio.run(self._head_write(fake_head, abstractions, project=project))
        real_result = asyncio.run(
            write_abstractions_to_graph(fake_real, abstractions, project=project)
        )
        return fake_head, fake_real, head_result, real_result

    def test_empty_abstractions_list(self) -> None:
        fake_head, fake_real, head_result, real_result = self._run_both([])
        assert fake_head.calls == fake_real.calls
        assert head_result == real_result == 0

    def test_single_abstraction_with_rule_ids(self) -> None:
        abstractions = [_abst(rule_ids=["RULE-1", "RULE-2"])]
        fake_head, fake_real, head_result, real_result = self._run_both(abstractions)
        assert fake_head.calls == fake_real.calls
        assert head_result == real_result == 1

    def test_several_abstractions_each_with_domain_summary_ratio_rule_ids(self) -> None:
        abstractions = [
            _abst(
                abstraction_id="ABS-A-001",
                domain="alpha",
                summary="summary a",
                compression_ratio=1.5,
                rule_ids=["R1"],
            ),
            _abst(
                abstraction_id="ABS-B-002",
                domain="beta",
                summary="summary b",
                compression_ratio=3.0,
                rule_ids=["R2", "R3"],
            ),
            _abst(
                abstraction_id="ABS-C-003",
                domain="gamma",
                summary="summary c",
                compression_ratio=2.0,
                rule_ids=[],
            ),
        ]
        fake_head, fake_real, head_result, real_result = self._run_both(abstractions)
        assert fake_head.calls == fake_real.calls
        assert head_result == real_result == 3

        node_calls = [c for c in fake_real.calls if c[0] == "node"]
        assert len(node_calls) == 3
        assert all("domain" in c[1] for c in node_calls), (
            "write_abstractions_to_graph's node_data must carry a domain key"
        )

    def test_custom_project_threads_through_delete_and_edges(self) -> None:
        abstractions = [_abst(rule_ids=["R1"])]
        fake_head, fake_real, head_result, real_result = self._run_both(
            abstractions, project="otherproj"
        )
        assert fake_head.calls == fake_real.calls
        assert head_result == real_result == 1
        assert fake_real.calls[0] == ("delete", "otherproj")
        assert fake_real.calls[-1] == ("edge", "ABS-TESTING-001", "R1", "otherproj")


# ---------------------------------------------------------------------------
# Section 3: materialize_abstractions_from_artifact differential. GREEN now
# (today's inline code); must stay green after the _persist_abstraction_layer
# migration.
# ---------------------------------------------------------------------------


class TestMaterializeDifferential:
    """FROZEN _head_materialize reproduces materialize_abstractions_from_artifact's
    HEAD persist loop verbatim (writ/compression/abstractions.py:126-181 at
    HEAD, before the Cycle E refactor). Same contract as
    TestWriteAbstractionsDifferential above, for the dep-free artifact-reading
    path: tolerant .get-based node_data with NO domain key.
    """

    @staticmethod
    async def _head_materialize(artifact_path, db, project: str = "writ") -> int:
        if not artifact_path.exists():
            return 0

        data = json.loads(artifact_path.read_text(encoding="utf-8"))
        artifact_project = data.get("project")
        if artifact_project is not None and artifact_project != project:
            raise ValueError(
                f"abstractions artifact declares project={artifact_project!r} but "
                f"materialization was requested for project={project!r}; refusing a "
                f"cross-project delete/create"
            )
        abstractions = data.get("abstractions", [])

        await db.delete_abstractions(project=project)

        count = 0
        for abst in abstractions:
            rule_ids = abst.get("rule_ids", [])
            node_data = {
                "abstraction_id": abst["abstraction_id"],
                "summary": abst.get("summary", ""),
                "compression_ratio": abst.get("compression_ratio"),
                "rule_count": len(rule_ids),
                "project": project,
            }
            await db.create_abstraction(node_data)
            for rid in rule_ids:
                await db.create_abstracts_edge(
                    abst["abstraction_id"], rid, project=project
                )
            count += 1

        return count

    def _run_both(self, artifact_path, project: str = "writ"):
        fake_head, fake_real = _FakeDb(), _FakeDb()
        head_result = head_exc = real_result = real_exc = None

        try:
            head_result = asyncio.run(
                self._head_materialize(artifact_path, fake_head, project=project)
            )
        except ValueError as exc:  # noqa: BLE001
            head_exc = exc

        try:
            real_result = asyncio.run(
                materialize_abstractions_from_artifact(
                    artifact_path, fake_real, project=project
                )
            )
        except ValueError as exc:  # noqa: BLE001
            real_exc = exc

        return fake_head, fake_real, head_result, real_result, head_exc, real_exc

    def test_missing_artifact_file_both_return_zero_with_no_db_calls(self, tmp_path) -> None:
        artifact_path = tmp_path / "does_not_exist.json"

        fake_head, fake_real, head_result, real_result, head_exc, real_exc = (
            self._run_both(artifact_path)
        )

        assert head_exc is None
        assert real_exc is None
        assert head_result == real_result == 0
        assert fake_head.calls == fake_real.calls == []

    def test_project_mismatch_both_raise_value_error_before_any_db_call(
        self, tmp_path
    ) -> None:
        artifact_path = tmp_path / "abstractions.json"
        artifact_path.write_text(
            json.dumps({"project": "otherproj", "abstractions": []}), encoding="utf-8"
        )

        fake_head, fake_real, head_result, real_result, head_exc, real_exc = (
            self._run_both(artifact_path, project="writ")
        )

        assert isinstance(head_exc, ValueError)
        assert isinstance(real_exc, ValueError)
        assert head_result is None
        assert real_result is None
        assert fake_head.calls == fake_real.calls == []

    def test_normal_artifact_identical_call_sequence_and_no_domain_key(
        self, tmp_path
    ) -> None:
        artifact_path = tmp_path / "abstractions.json"
        artifact_data = {
            "project": "writ",
            "abstractions": [
                {
                    "abstraction_id": "ABS-TESTING-000",
                    "summary": "has a summary",
                    "rule_ids": ["R1", "R2"],
                    "compression_ratio": 2.5,
                },
                {
                    "abstraction_id": "ABS-TESTING-001",
                    # no "summary" key -- exercises the .get("summary", "") default
                    "rule_ids": ["R1"],
                    "compression_ratio": 1.0,
                },
            ],
        }
        artifact_path.write_text(json.dumps(artifact_data), encoding="utf-8")

        fake_head, fake_real, head_result, real_result, head_exc, real_exc = (
            self._run_both(artifact_path)
        )

        assert head_exc is None
        assert real_exc is None
        assert fake_head.calls == fake_real.calls
        assert head_result == real_result == 2

        node_calls = [c for c in fake_real.calls if c[0] == "node"]
        assert len(node_calls) == 2
        for c in node_calls:
            assert "domain" not in c[1], (
                "materialize's node_data must NOT carry a domain key -- the "
                "artifact has no domain field"
            )

        summaries = {c[1]["abstraction_id"]: c[1]["summary"] for c in node_calls}
        assert summaries["ABS-TESTING-000"] == "has a summary"
        assert summaries["ABS-TESTING-001"] == "", (
            "missing 'summary' in the artifact entry must default to '' via .get"
        )

    def test_artifact_with_no_project_key_is_accepted_for_any_requested_project(
        self, tmp_path
    ) -> None:
        """artifact_project is None (key absent) skips the mismatch guard
        entirely -- both the frozen copy and the real function must accept it."""
        artifact_path = tmp_path / "abstractions.json"
        artifact_path.write_text(
            json.dumps(
                {
                    "abstractions": [
                        {
                            "abstraction_id": "ABS-NOPROJECT-000",
                            "summary": "s",
                            "rule_ids": [],
                            "compression_ratio": 1.0,
                        }
                    ]
                }
            ),
            encoding="utf-8",
        )

        fake_head, fake_real, head_result, real_result, head_exc, real_exc = (
            self._run_both(artifact_path, project="writ")
        )

        assert head_exc is None
        assert real_exc is None
        assert fake_head.calls == fake_real.calls
        assert head_result == real_result == 1


# ---------------------------------------------------------------------------
# Section 4: source guards. RED now, GREEN once both functions are migrated
# to build entries + delegate to _persist_abstraction_layer.
# ---------------------------------------------------------------------------


class TestSourceGuards:
    def test_module_source_defines_persist_abstraction_layer(self) -> None:
        source = inspect.getsource(abstractions_module)
        assert "def _persist_abstraction_layer" in source, (
            "writ/compression/abstractions.py does not define "
            "_persist_abstraction_layer yet (Wave-3 Cycle E)"
        )

    def test_materialize_calls_the_helper_and_no_longer_inlines_the_delete(self) -> None:
        src = inspect.getsource(materialize_abstractions_from_artifact)
        assert "_persist_abstraction_layer(" in src, (
            "materialize_abstractions_from_artifact has not been migrated to "
            "call _persist_abstraction_layer(...) yet"
        )
        assert "await db.delete_abstractions(project=project)" not in src, (
            "materialize_abstractions_from_artifact still inlines the delete "
            "call; it should have moved into _persist_abstraction_layer"
        )

    def test_write_abstractions_calls_the_helper_and_no_longer_inlines_the_delete(
        self,
    ) -> None:
        src = inspect.getsource(write_abstractions_to_graph)
        assert "_persist_abstraction_layer(" in src, (
            "write_abstractions_to_graph has not been migrated to call "
            "_persist_abstraction_layer(...) yet"
        )
        assert "await db.delete_abstractions(project=project)" not in src, (
            "write_abstractions_to_graph still inlines the delete call; it "
            "should have moved into _persist_abstraction_layer"
        )

    def test_helpers_own_source_contains_the_delete_call(self) -> None:
        _require_persist_helper()
        src = inspect.getsource(_persist_abstraction_layer)
        assert "await db.delete_abstractions(project=project)" in src, (
            "_persist_abstraction_layer must itself perform the delete that "
            "materialize/write_abstractions_to_graph no longer inline"
        )
