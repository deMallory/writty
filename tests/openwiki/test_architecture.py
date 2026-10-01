"""Pins the architecture pages to the code they describe.

Each check reads the source a page summarizes: the `writ/` package tree and its imports,
`hooks/hooks.json`, the route modules, the graph schema, the retrieval constants and
`docs/adr/`. A new subpackage, hook event, route module, node type or ADR fails here
instead of leaving a page that reads right and is wrong. The topography chart is held to
the rule in INSTRUCTIONS.md: no edge that no import backs.

Files only, like test_structure.py:

    python -m pytest --noconftest tests/openwiki -q
"""

from __future__ import annotations

import ast
import json
import re

from tests.openwiki.test_structure import REPO_ROOT, WIKI_ROOT

ARCHITECTURE = WIKI_ROOT / "architecture"
WRIT = REPO_ROOT / "writ"
_BACKTICK = re.compile(r"`([^`\n]+)`")
# Solid, dotted and thick flowchart arrows; an optional |label| follows the arrow.
_ARROW = re.compile(r"\s*(?:-->|-\.->|==>)\s*(?:\|[^|]*\|\s*)?")
_NODE_ID = re.compile(r"^\s*([A-Za-z_]\w*)")


def _page(name: str) -> str:
    return (ARCHITECTURE / name).read_text(encoding="utf-8")


def _backticked(name: str) -> set[str]:
    return set(_BACKTICK.findall(_page(name)))


def _table(name: str, *header: str) -> list[list[str]]:
    """Body rows of the first table on the page whose leading header cells are `header`."""
    rows: list[list[str]] = []
    in_table = False
    for line in _page(name).split("\n"):
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if not in_table and cells[: len(header)] == list(header):
            in_table = True
        elif in_table and not line.startswith("|"):
            break
        elif in_table and not set(cells[0]) <= set("-: "):
            rows.append(cells)
    return rows


def _mermaid_blocks(name: str, kind: str) -> list[str]:
    """Bodies of the mermaid fences on the page whose first line starts with `kind`."""
    blocks: list[str] = []
    body: list[str] | None = None
    for line in _page(name).split("\n"):
        if line.strip() == "```mermaid":
            body = []
        elif body is not None and line.strip() == "```":
            if body and body[0].strip().startswith(kind):
                blocks.append("\n".join(body))
            body = None
        elif body is not None:
            body.append(line)
    return blocks


def _subpackages() -> list[str]:
    return sorted(p.parent.name for p in WRIT.glob("*/__init__.py"))


def _imports(source_pkg: str, target_pkg: str) -> bool:
    pattern = re.compile(rf"^\s*(?:from|import)\s+writ\.{target_pkg}\b", re.MULTILINE)
    return any(
        pattern.search(path.read_text(encoding="utf-8"))
        for path in (WRIT / source_pkg).rglob("*.py")
    )


def _drawn_edges(name: str) -> list[tuple[str, str]]:
    """(from, to) node ids of every arrow in the page's flowcharts, chains included.

    Ids are lowercased: mermaid reserves `graph`, so the chart has to spell that node `Graph`.
    """
    edges: list[tuple[str, str]] = []
    for block in _mermaid_blocks(name, "flowchart"):
        for line in block.split("\n"):
            if line.strip().startswith("%%"):
                continue
            ids = [m.group(1).lower() for part in _ARROW.split(line) if (m := _NODE_ID.match(part))]
            edges.extend(zip(ids, ids[1:]))
    return edges


def _module_assignments(rel_path: str) -> dict[str, ast.expr]:
    """Module-level `NAME = value` and `NAME: T = value` nodes, read without importing writ."""
    tree = ast.parse((REPO_ROOT / rel_path).read_text(encoding="utf-8"))
    found: dict[str, ast.expr] = {}
    for node in tree.body:
        if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name):
            found[node.targets[0].id] = node.value
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name) and node.value:
            found[node.target.id] = node.value
    return found


def _adr_status(path) -> str:
    """The `Status:` line of an ADR up to its first parenthesis or full stop."""
    match = re.search(r"^Status:\s*([^(.\n]+)", path.read_text(encoding="utf-8"), re.MULTILINE)
    assert match, f"{path.name} has no Status line"
    return match.group(1).strip().lower()


def test_the_topography_page_names_every_subpackage():
    listed = _backticked("topography.md")
    assert [p for p in _subpackages() if f"writ/{p}/" not in listed] == []


def test_every_drawn_import_edge_is_backed_by_an_import():
    packages = set(_subpackages())
    drawn = [(a, b) for a, b in _drawn_edges("topography.md") if a in packages and b in packages]
    assert drawn, "the topography flowchart draws no edge between writ subpackages"
    assert [f"{a} --> {b}" for a, b in drawn if not _imports(a, b)] == []


def test_the_hooks_table_lists_exactly_the_hook_events():
    registered = set(json.loads((REPO_ROOT / "hooks/hooks.json").read_text(encoding="utf-8"))["hooks"])
    listed = {row[0].strip("`") for row in _table("hooks.md", "Event")}
    assert sorted(registered - listed) == []
    assert sorted(listed - registered) == []


def test_every_script_the_hooks_page_names_exists():
    named = [t for t in _backticked("hooks.md") if t.endswith(".sh") and "/" not in t]
    assert named, "the hooks page names no script"
    assert [s for s in named if not (REPO_ROOT / "hooks/scripts" / s).is_file()] == []


def test_the_local_service_page_names_every_route_module():
    listed = _backticked("local-service.md")
    modules = sorted(
        p.relative_to(REPO_ROOT).as_posix()
        for p in (WRIT / "server/routes").glob("*.py")
        if p.name != "__init__.py"
    )
    assert [m for m in modules if m not in listed] == []


def test_the_rule_graph_page_names_every_node_type():
    registry = _module_assignments("writ/graph/schema.py")["NODE_TYPE_MODELS"]
    node_types = [key.value for key in registry.keys]
    listed = _backticked("rule-graph.md")
    assert [t for t in node_types if t not in listed] == []


def test_the_provenance_diagram_carries_every_state():
    states = ast.literal_eval(_module_assignments("writ/graph/schema.py")["VALID_PROVENANCE"])
    diagrams = _mermaid_blocks("rule-graph.md", "stateDiagram-v2")
    assert diagrams, "the rule graph page has no state diagram"
    assert [s for s in states if not any(s in d for d in diagrams)] == []


def test_the_retrieval_page_states_the_code_abstention_threshold():
    name = "RULE_INJECTION_ABSTENTION_THRESHOLD"
    in_code = ast.literal_eval(_module_assignments("writ/retrieval/pipeline.py")[name])
    lines = [line for line in _page("retrieval.md").split("\n") if f"`{name}`" in line]
    assert lines, f"the retrieval page does not name `{name}`"
    stated = re.search(r"\d+\.\d+", lines[0])
    assert stated and float(stated.group()) == in_code


def test_the_retrieval_page_names_both_floor_predicates():
    defined = _module_assignments("writ/graph/predicates.py")
    listed = _backticked("retrieval.md")
    predicates = ["INJECTION_RULE_WHERE", "RANKED_INCLUDE_WHERE"]
    assert [p for p in predicates if p not in defined] == []
    assert [p for p in predicates if p not in listed] == []


def test_the_decisions_page_indexes_every_adr_with_its_status():
    expected = {
        p.relative_to(REPO_ROOT).as_posix(): _adr_status(p)
        for p in sorted((REPO_ROOT / "docs/adr").glob("*.md"))
    }
    indexed = {row[0].strip("`"): row[2].lower() for row in _table("decisions.md", "ADR", "Title", "Status")}
    assert sorted(set(expected) ^ set(indexed)) == []
    assert {k: v for k, v in indexed.items() if v != expected[k]} == {}
