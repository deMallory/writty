"""Per-role effort: SubagentRole.effort_preference end to end, with no Neo4j.

Covers the schema field, the exporter render (`effort:` after `model:`), the ingest
inverse, the shipped agents/*.md and writ-corpus.cypher values, exporter-shape parity of
the agent files, and the two read surfaces (GET /subagent-role/{name} and
`writ role-prompt`). Runs under --noconftest: files are read as text and the DB is faked.
"""
from __future__ import annotations

import asyncio
import importlib.util
import re
import sys
from contextlib import asynccontextmanager
from pathlib import Path

import pydantic
import pytest
import yaml
from typer.testing import CliRunner

WRIT_ROOT = Path(__file__).resolve().parent.parent
AGENTS_DIR = WRIT_ROOT / "agents"
CORPUS = WRIT_ROOT / "writ-corpus.cypher"
EXPORT_SCRIPT = WRIT_ROOT / "scripts" / "export_subagent_roles.py"
INGEST_SCRIPT = WRIT_ROOT / "scripts" / "ingest_subagent_roles.py"

ALLOWED = ("low", "medium", "high", "xhigh", "max")

# agent name -> (role_id, model, effort)
EXPECTED = {
    "writ-planner": ("ROL-PLANNER-001", "opus", "high"),
    "writ-implementer": ("ROL-IMPLEMENTER-001", "opus", "high"),
    "writ-explorer": ("ROL-EXPLORER-001", "sonnet", "medium"),
    "writ-test-writer": ("ROL-TEST-WRITER-001", "sonnet", "medium"),
    "writ-reviewer": ("ROL-REVIEWER-001", "sonnet", "medium"),
    # Fork-only: the split reviewers the review-order gate dispatches. Effort follows the
    # model tier: haiku low, sonnet medium.
    "writ-spec-reviewer": ("ROL-SPEC-REVIEWER-001", "haiku", "low"),
    "writ-code-quality-reviewer": ("ROL-CODE-QUALITY-REVIEWER-001", "sonnet", "medium"),
}

FRONT_MATTER = re.compile(r"^---\n(.*?)\n---\n(.*)", re.DOTALL)


def _load(mod_name: str, path: Path):
    spec = importlib.util.spec_from_file_location(mod_name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[mod_name] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def export_mod():
    return _load("export_subagent_roles", EXPORT_SCRIPT)


@pytest.fixture(scope="module")
def ingest_mod():
    return _load("ingest_subagent_roles", INGEST_SCRIPT)


def _row(**over) -> dict:
    base = {
        "name": "writ-example",
        "description": "An example agent.",
        "model_preference": "sonnet",
        "tools": "Read Glob",
        "prompt_template": "You are an example.",
    }
    base.update(over)
    return base


def _write_agent(tmp_path: Path, frontmatter: str) -> Path:
    p = tmp_path / "writ-example.md"
    p.write_text(f"---\n{frontmatter}\n---\n\nBody.\n", encoding="utf-8")
    return p


# --- Schema -------------------------------------------------------------------


class TestSchema:
    @staticmethod
    def _kwargs(ingest_mod, **over) -> dict:
        agent = {
            "role_id": "ROL-EXAMPLE-001",
            "name": "writ-example",
            "description": "d",
            "model": "sonnet",
            "tools": "Read",
            "prompt_template": "body",
        }
        node = ingest_mod.build_node(agent)
        node.pop("effort_preference", None)
        node.update(over)
        return node

    @pytest.mark.parametrize("value", ALLOWED)
    def test_accepts_each_allowed_value(self, ingest_mod, value: str) -> None:
        from writ.graph.schema import SubagentRole

        role = SubagentRole(**self._kwargs(ingest_mod, effort_preference=value))
        assert role.effort_preference == value

    def test_none_is_accepted_explicitly(self, ingest_mod) -> None:
        from writ.graph.schema import SubagentRole

        role = SubagentRole(**self._kwargs(ingest_mod, effort_preference=None))
        assert role.effort_preference is None

    def test_default_is_none(self, ingest_mod) -> None:
        from writ.graph.schema import SubagentRole

        role = SubagentRole(**self._kwargs(ingest_mod))
        assert role.effort_preference is None

    @pytest.mark.parametrize("bad", ["extreme", "", "High"])
    def test_rejects_invalid_values(self, ingest_mod, bad: str) -> None:
        from writ.graph.schema import SubagentRole

        with pytest.raises(pydantic.ValidationError):
            SubagentRole(**self._kwargs(ingest_mod, effort_preference=bad))

    def test_valid_constant_lists_exactly_the_allowed_values(self) -> None:
        from writ.graph.schema import VALID_EFFORT_PREFERENCES

        assert tuple(VALID_EFFORT_PREFERENCES) == ALLOWED

    def test_effort_preference_is_a_managed_prop(self) -> None:
        from writ.graph.schema import MANAGED_PROP_NAMES

        assert "effort_preference" in MANAGED_PROP_NAMES


# --- Exporter render ----------------------------------------------------------


class TestRender:
    def test_effort_emitted_directly_after_model_and_before_tools(self, export_mod) -> None:
        out = export_mod.render_agent_md(_row(effort_preference="high"))
        assert "\nmodel: sonnet\neffort: high\ntools: Read Glob\n" in out

    @pytest.mark.parametrize("value", ALLOWED)
    def test_each_value_renders(self, export_mod, value: str) -> None:
        out = export_mod.render_agent_md(_row(effort_preference=value))
        assert f"\neffort: {value}\n" in out

    def test_omitted_when_none(self, export_mod) -> None:
        out = export_mod.render_agent_md(_row(effort_preference=None))
        assert "effort:" not in out

    def test_omitted_when_key_absent(self, export_mod) -> None:
        out = export_mod.render_agent_md(_row())
        assert "effort:" not in out

    def test_role_without_effort_renders_as_before(self, export_mod) -> None:
        out = export_mod.render_agent_md(_row())
        assert out.startswith(
            '---\nname: writ-example\ndescription: "An example agent."\n'
            "model: sonnet\ntools: Read Glob\n---\n"
        )

    def test_effort_without_model_still_precedes_tools(self, export_mod) -> None:
        out = export_mod.render_agent_md(_row(model_preference=None, effort_preference="low"))
        assert "\neffort: low\ntools: Read Glob\n" in out
        assert "model:" not in out

    def test_fetch_roles_query_projects_effort_preference(self) -> None:
        text = EXPORT_SCRIPT.read_text(encoding="utf-8")
        assert "r.effort_preference AS effort_preference" in text


# --- Ingest inverse -----------------------------------------------------------


class TestIngest:
    def test_parse_and_build_map_effort_to_effort_preference(self, ingest_mod, tmp_path) -> None:
        p = _write_agent(
            tmp_path,
            'name: writ-example\ndescription: "d"\nmodel: opus\neffort: high\ntools: Read',
        )
        agent = ingest_mod.parse_agent_file(p)
        node = ingest_mod.build_node(agent)
        assert node["effort_preference"] == "high"
        assert node["model_preference"] == "opus"

    def test_absent_effort_yields_none(self, ingest_mod, tmp_path) -> None:
        p = _write_agent(tmp_path, 'name: writ-example\ndescription: "d"\nmodel: opus\ntools: Read')
        node = ingest_mod.build_node(ingest_mod.parse_agent_file(p))
        assert "effort_preference" in node
        assert node["effort_preference"] is None

    @pytest.mark.parametrize("name", sorted(EXPECTED))
    def test_shipped_agent_files_ingest_with_expected_effort(self, ingest_mod, name: str) -> None:
        node = ingest_mod.build_node(ingest_mod.parse_agent_file(AGENTS_DIR / f"{name}.md"))
        assert node["effort_preference"] == EXPECTED[name][2]


# --- Shipped data -------------------------------------------------------------


def _frontmatter(name: str) -> tuple[dict, str]:
    text = (AGENTS_DIR / f"{name}.md").read_text(encoding="utf-8")
    m = FRONT_MATTER.match(text)
    assert m, f"{name}.md has no front matter"
    return yaml.safe_load(m.group(1)), m.group(2)


class TestAgentFiles:
    def test_exactly_the_expected_agent_files(self) -> None:
        assert {p.stem for p in AGENTS_DIR.glob("*.md")} == set(EXPECTED)

    @pytest.mark.parametrize("name", sorted(EXPECTED))
    def test_model_and_effort(self, name: str) -> None:
        fm, _ = _frontmatter(name)
        _, model, effort = EXPECTED[name]
        assert fm["model"] == model
        assert fm["effort"] == effort

    @pytest.mark.parametrize("name", sorted(EXPECTED))
    def test_effort_line_sits_between_model_and_tools(self, name: str) -> None:
        lines = (AGENTS_DIR / f"{name}.md").read_text(encoding="utf-8").splitlines()
        i = next(k for k, ln in enumerate(lines) if ln.startswith("model:"))
        assert lines[i + 1].startswith("effort: ")
        assert lines[i + 2].startswith("tools:")

    @pytest.mark.parametrize("name", sorted(EXPECTED))
    def test_file_byte_matches_exporter_render_of_its_own_fields(
        self, name: str, export_mod, ingest_mod
    ) -> None:
        path = AGENTS_DIR / f"{name}.md"
        node = ingest_mod.build_node(ingest_mod.parse_agent_file(path))
        assert export_mod.render_agent_md(node) == path.read_text(encoding="utf-8")


class TestCorpusCypher:
    @staticmethod
    def _line(role_id: str) -> str:
        lines = [
            ln
            for ln in CORPUS.read_text(encoding="utf-8").splitlines()
            if ln.startswith("CREATE (:SubagentRole") and f"role_id: '{role_id}'" in ln
        ]
        assert len(lines) == 1, f"{role_id}: expected one CREATE line, got {len(lines)}"
        return lines[0]

    def test_exactly_seven_subagent_role_creates(self) -> None:
        n = sum(
            1
            for ln in CORPUS.read_text(encoding="utf-8").splitlines()
            if ln.startswith("CREATE (:SubagentRole")
        )
        assert n == len(EXPECTED) == 7

    @pytest.mark.parametrize("name", sorted(EXPECTED))
    def test_effort_and_model_preference(self, name: str) -> None:
        role_id, model, effort = EXPECTED[name]
        line = self._line(role_id)
        assert f"name: '{name}'" in line
        assert f"model_preference: '{model}', effort_preference: '{effort}'" in line

    @pytest.mark.parametrize("name", sorted(EXPECTED))
    def test_effort_appears_once(self, name: str) -> None:
        assert self._line(EXPECTED[name][0]).count("effort_preference:") == 1


# --- Read surfaces ------------------------------------------------------------


class _FakeDB:
    def __init__(self, rec: dict | None) -> None:
        self._rec = rec
        self.asked: list[str] = []

    async def get_subagent_role(self, name: str):
        self.asked.append(name)
        return self._rec


def _rec(**over) -> dict:
    rec = {
        "role_id": "ROL-PLANNER-001",
        "name": "writ-planner",
        "prompt_template": "PLAN PROMPT",
        "model_preference": "opus",
        "effort_preference": "high",
        "dispatched_by": [],
        "write_scope": ["plan.md"],
    }
    rec.update(over)
    return rec


class TestRoute:
    def test_returns_effort_beside_model(self, monkeypatch) -> None:
        import writ.server as server
        from writ.server.routes.query import subagent_role_get

        monkeypatch.setattr(server, "_db", _FakeDB(_rec()))
        result = asyncio.run(subagent_role_get("writ-planner"))
        assert result["model_preference"] == "opus"
        assert result["effort_preference"] == "high"

    def test_effort_none_passes_through_as_none(self, monkeypatch) -> None:
        import writ.server as server
        from writ.server.routes.query import subagent_role_get

        monkeypatch.setattr(server, "_db", _FakeDB(_rec(effort_preference=None)))
        result = asyncio.run(subagent_role_get("writ-planner"))
        assert "effort_preference" in result
        assert result["effort_preference"] is None


class TestRolePromptCli:
    def test_header_prints_effort_beside_model(self, monkeypatch) -> None:
        import writ.cli as cli

        @asynccontextmanager
        async def _fake_writ_db():
            yield _FakeDB(_rec())

        monkeypatch.setattr(cli, "_writ_db", _fake_writ_db)
        result = CliRunner().invoke(cli.app, ["role-prompt", "writ-planner"])
        assert result.exit_code == 0, result.output
        first = result.output.splitlines()[0]
        assert "model=opus" in first
        assert "effort=high" in first
        assert first.index("model=opus") < first.index("effort=high")
        assert "PLAN PROMPT" in result.output
