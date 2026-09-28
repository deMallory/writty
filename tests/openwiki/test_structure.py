"""Structural checks for the repo's own openwiki/ folder.

Port of paulinator's tests/openwiki/structure.test.ts. The two parsers below use the
regexes of paulinator's scope/wiki.ts, so the wiki keeps the OKF v0.1 shape the openwiki
CLI writes and reads: root index -> section index -> page, two levels, nothing deeper.

Files only, no graph and no daemon, so the checks run on a bare CI runner:

    python -m pytest --noconftest tests/openwiki -q

--noconftest matters: tests/conftest.py refuses the session when the isolated Neo4j is
unreachable, and the scheduled wiki refresh job has no Neo4j.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
WIKI_ROOT = REPO_ROOT / "openwiki"
SECTIONS = ["workflows", "architecture", "testing", "integrations", "operations"]
MERMAID_KEYWORDS = (
    "flowchart",
    "graph",
    "sequenceDiagram",
    "stateDiagram-v2",
    "timeline",
    "classDiagram",
    "erDiagram",
)

_FRONTMATTER = re.compile(r"^---\r?\n([\s\S]*?)\r?\n---\r?\n")
_FRONTMATTER_PAIR = re.compile(r"^(title|description|type):\s*(.*)$")
_INDEX_LINK = re.compile(r"\]\(([^)#\s]+)\)")
_BACKTICK_TOKEN = re.compile(r"`([^`\n]+)`")
_CITED_PATH = re.compile(
    r"^[A-Za-z0-9_.-]+(/[A-Za-z0-9_.@-]+)+\.(py|sh|md|json|yml|yaml|toml|cypher|html)$"
)
# A row is `| `path` | N | ...`: an inventory table with a Lines column.
_COUNTED_ROW = re.compile(r"^\|\s*`([^`]+)`\s*\|\s*(\d+)\s*\|")


def parse_frontmatter(markdown: str) -> tuple[dict[str, str], str]:
    """Flat `key: value` pairs from a leading --- block; only type, title, description."""
    meta = {"type": "", "title": "", "description": ""}
    match = _FRONTMATTER.match(markdown)
    if not match:
        return meta, markdown
    for line in re.split(r"\r?\n", match.group(1)):
        pair = _FRONTMATTER_PAIR.match(line)
        if pair:
            meta[pair.group(1)] = re.sub(r"^[\"']|[\"']$", "", pair.group(2).strip())
    return meta, markdown[match.end() :]


def parse_index_links(markdown: str) -> tuple[list[str], list[str]]:
    """Relative `.md` file links and `dir/` links of an index, deduplicated, in order."""
    files: list[str] = []
    dirs: list[str] = []
    for target in _INDEX_LINK.findall(markdown):
        if re.match(r"^[a-z]+://", target, re.IGNORECASE) or target.startswith("/"):
            continue
        if target.endswith(".md"):
            files.append(target)
        elif target.endswith("/"):
            dirs.append(target[:-1])
    return list(dict.fromkeys(files)), list(dict.fromkeys(dirs))


def cited_paths(markdown: str) -> list[str]:
    """Backtick tokens that look like repo paths. A token whose first segment is not at
    the repo root belongs to another repo or to $HOME and is left alone."""
    cited = []
    for token in _BACKTICK_TOKEN.findall(markdown):
        candidate = token.split(":")[0]
        if not _CITED_PATH.match(candidate) or "<" in candidate or "*" in candidate:
            continue
        if (REPO_ROOT / candidate.split("/")[0]).exists():
            cited.append(candidate)
    return cited


def _read_wiki(rel_path: str) -> str:
    return (WIKI_ROOT / rel_path).read_text(encoding="utf-8")


def _is_reserved(rel_path: str) -> bool:
    name = rel_path.rsplit("/", 1)[-1]
    return name == "index.md" or name.lower() == "instructions.md"


def _all_wiki_files() -> list[str]:
    return sorted(p.relative_to(WIKI_ROOT).as_posix() for p in WIKI_ROOT.rglob("*.md"))


def _reachable_pages() -> tuple[list[str], list[str]]:
    """Walk root index -> section indexes the way the OKF reader does."""
    pages: list[str] = []
    missing: list[str] = []
    root_files, root_dirs = parse_index_links(_read_wiki("index.md"))
    for rel in root_files:
        (pages if (WIKI_ROOT / rel).is_file() else missing).append(rel)
    for section in root_dirs:
        index = f"{section}/index.md"
        if not (WIKI_ROOT / index).is_file():
            missing.append(index)
            continue
        section_files, _ = parse_index_links(_read_wiki(index))
        for name in section_files:
            rel = f"{section}/{name}"
            (pages if (WIKI_ROOT / rel).is_file() else missing).append(rel)
    return pages, missing


def test_root_index_declares_documentation_index():
    meta, _ = parse_frontmatter(_read_wiki("index.md"))
    assert meta["type"] == "Documentation Index"


def test_root_index_links_quickstart_and_every_section():
    files, dirs = parse_index_links(_read_wiki("index.md"))
    assert "quickstart.md" in files
    assert [s for s in SECTIONS if s not in dirs] == []


def test_every_index_link_resolves():
    _, missing = _reachable_pages()
    assert missing == []


def test_no_orphan_pages():
    pages, _ = _reachable_pages()
    orphans = [f for f in _all_wiki_files() if not _is_reserved(f) and f not in pages]
    assert orphans == []


def test_every_page_carries_front_matter():
    problems = []
    for rel in _all_wiki_files():
        raw = _read_wiki(rel)
        if not raw.startswith("---\n"):
            problems.append(f"{rel}: front matter must open on line 1")
            continue
        meta, _ = parse_frontmatter(raw)
        if not meta["type"]:
            problems.append(f"{rel}: missing type")
        if not _is_reserved(rel) or rel == "INSTRUCTIONS.md":
            problems.extend(
                f"{rel}: missing {key}"
                for key in ("title", "description")
                if not meta[key]
            )
    assert problems == []


def test_every_cited_path_exists():
    dangling = [
        f"openwiki/{rel} -> {cited}"
        for rel in _all_wiki_files()
        for cited in cited_paths(_read_wiki(rel))
        if not (REPO_ROOT / cited).exists()
    ]
    assert dangling == []


def test_cited_paths_ignore_tokens_outside_the_repo():
    markdown = "See `elsewhere/app/models.py`, `docs/nope.md:12` and `docs/<name>.md`."
    assert cited_paths(markdown) == ["docs/nope.md"]


def test_mermaid_fences_are_closed_and_typed():
    problems = []
    for rel in _all_wiki_files():
        lines = _read_wiki(rel).split("\n")
        open_fence = False
        for number, line in enumerate(lines, start=1):
            if line.strip() == "```mermaid":
                open_fence = True
                first = lines[number].strip() if number < len(lines) else ""
                if not first.startswith(MERMAID_KEYWORDS):
                    problems.append(f'{rel}:{number + 1} fence starts with "{first}"')
            elif open_fence and line.strip() == "```":
                open_fence = False
        if open_fence:
            problems.append(f"{rel}: unclosed mermaid fence")
    assert problems == []


def test_lines_column_matches_the_file():
    # Rows whose path does not resolve are left to test_every_cited_path_exists.
    problems = []
    for rel in _all_wiki_files():
        for number, line in enumerate(_read_wiki(rel).split("\n"), start=1):
            row = _COUNTED_ROW.match(line)
            if not row:
                continue
            target = REPO_ROOT / row.group(1)
            if not target.is_file():
                continue
            actual = target.read_text(encoding="utf-8").count("\n")
            if actual != int(row.group(2)):
                problems.append(
                    f"{rel}:{number} {row.group(1)} says {row.group(2)} lines, file has {actual}"
                )
    assert problems == []


def test_readme_points_at_the_wiki():
    assert "openwiki/" in (REPO_ROOT / "README.md").read_text(encoding="utf-8")


def test_parse_frontmatter_without_front_matter_returns_empty_fields_and_body():
    body = "# Title\n\ntype: Guide\n"
    meta, rest = parse_frontmatter(body)
    assert meta == {"type": "", "title": "", "description": ""}
    assert rest == body


def test_parse_frontmatter_strips_quotes_and_ignores_other_keys():
    meta, rest = parse_frontmatter(
        '---\ntype: Guide\ntitle: "Hooks"\nowner: me\n---\n# Hooks\n'
    )
    assert meta == {"type": "Guide", "title": "Hooks", "description": ""}
    assert rest == "# Hooks\n"


def test_parse_index_links_skips_external_absolute_and_anchored_links_and_dedupes():
    markdown = (
        "- [A](a.md)\n- [A again](a.md)\n- [Web](https://example.com/x.md)\n"
        "- [Abs](/abs.md)\n- [Anchor](b.md#part)\n- [Section](workflows/)\n"
    )
    assert parse_index_links(markdown) == (["a.md"], ["workflows"])
