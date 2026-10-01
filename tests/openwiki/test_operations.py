"""Pins the operations pages to the sources they summarize.

The service lifecycle page names ports, a systemd unit and the macOS realign; the upstream
sync page lists the hooks only this fork has; the project log is dated, newest first. Each
check reads the file the fact comes from, so a moved port, a renamed unit or a new fork hook
fails here instead of leaving a page that reads right and is wrong.

Files only, like test_structure.py:

    python -m pytest --noconftest tests/openwiki -q
"""

from __future__ import annotations

import ast
import json
import os
import re

from tests.openwiki.test_structure import REPO_ROOT, WIKI_ROOT

OPERATIONS = WIKI_ROOT / "operations"
_SYSTEMCTL_UNIT = re.compile(r"systemctl --user \w+ ([\w.-]+)")
_DARWIN_BRANCH = re.compile(r'= "Darwin" \]; then\n(.*?)\n(?:else|fi)\b', re.DOTALL)
_CURRENT_STATE = re.compile(r"^## Current state as of (\d{4}-\d{2}-\d{2})$", re.MULTILINE)
_TIMELINE_DATE = re.compile(r"^- (\d{4}-\d{2}-\d{2})\b")


def _read(rel_path: str) -> str:
    return (REPO_ROOT / rel_path).read_text(encoding="utf-8")


def _page(name: str) -> str:
    return (OPERATIONS / name).read_text(encoding="utf-8")


def _table(markdown: str, *header: str) -> list[list[str]]:
    """Body rows of the first table whose leading header cells are `header`."""
    rows: list[list[str]] = []
    in_table = False
    for line in markdown.split("\n"):
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if not in_table and cells[: len(header)] == list(header):
            in_table = True
        elif in_table and not line.startswith("|"):
            break
        elif in_table and not set(cells[0]) <= set("-: "):
            rows.append(cells)
    return rows


def _registered_hooks() -> dict[str, set[str]]:
    """Script basename -> the events `hooks/hooks.json` registers it on."""
    events: dict[str, set[str]] = {}
    for event, groups in json.loads(_read("hooks/hooks.json"))["hooks"].items():
        for group in groups:
            for hook in group.get("hooks", []):
                script = os.path.basename(hook["command"].split()[-1].strip("\"'"))
                events.setdefault(script, set()).add(event)
    return events


def _timeline_dates(markdown: str) -> list[str]:
    """Dates of the `- YYYY-MM-DD` bullets under the `## Timeline` heading, in page order."""
    dates: list[str] = []
    in_timeline = False
    for line in markdown.split("\n"):
        if line.startswith("## "):
            in_timeline = line.strip() == "## Timeline"
        elif in_timeline and (match := _TIMELINE_DATE.match(line)):
            dates.append(match.group(1))
    return dates


def test_every_port_in_the_service_table_is_set_in_the_file_it_names():
    rows = _table(_page("service-lifecycle.md"), "What", "Port", "Set in")
    assert rows, "the service lifecycle page has no What | Port | Set in table"
    unset = [
        row[:3]
        for row in rows
        if not re.search(rf"\b{re.escape(row[1])}\b", _read(row[2].strip("`")))
    ]
    assert unset == []


def test_every_systemd_unit_the_page_names_is_installed_by_the_service_script():
    units = _SYSTEMCTL_UNIT.findall(_page("service-lifecycle.md"))
    assert units, "the service lifecycle page names no systemd unit"
    installer = _read("scripts/install-server-service.sh")
    full_names = {u if "." in u else f"{u}.service" for u in units}
    assert sorted(u for u in full_names if u not in installer) == []


def test_the_macos_realign_the_page_describes_is_still_in_the_session_start_hook():
    branch = _DARWIN_BRANCH.search(_read("hooks/scripts/session-start-bootstrap.sh"))
    assert branch, "session-start-bootstrap.sh no longer has a Darwin branch"
    assert "WRIT_REALIGN_CACHE=1" in branch.group(1)
    assert "WRIT_REALIGN_CACHE" in _page("service-lifecycle.md")


def test_every_ported_fork_hook_appears_on_the_upstream_sync_page():
    tree = ast.parse(_read("tests/test_fork_hooks_ported.py"))
    ported = next(
        ast.literal_eval(node.value)
        for node in tree.body
        if isinstance(node, ast.Assign)
        and isinstance(node.targets[0], ast.Name)
        and node.targets[0].id == "PORTED"
    )
    page = _page("upstream-sync.md")
    assert [hook for hook in ported if f"`{hook}`" not in page] == []


def test_every_hook_the_fork_table_lists_is_registered_on_its_event():
    rows = _table(_page("upstream-sync.md"), "Fork hook", "Event")
    assert rows, "the upstream sync page has no Fork hook | Event table"
    registered = _registered_hooks()
    wrong = [
        row[:2]
        for row in rows
        if not (REPO_ROOT / "hooks/scripts" / row[0].strip("`")).is_file()
        or row[1].strip("`") not in registered.get(row[0].strip("`"), set())
    ]
    assert wrong == []


def test_the_project_log_runs_newest_first():
    log = _page("project-log.md")
    current = _CURRENT_STATE.findall(log)
    timeline = _timeline_dates(log)
    assert current, "the project log has no 'Current state as of YYYY-MM-DD' heading"
    assert timeline, "the project log has no dated bullet under '## Timeline'"
    assert current == sorted(current, reverse=True)
    assert timeline == sorted(timeline, reverse=True)
    assert current[0] >= timeline[0]


def test_timeline_dates_read_only_the_timeline_section():
    markdown = "\n".join(
        [
            "## Current state as of 2026-09-28",
            "- 2026-09-28: not a timeline entry",
            "## Timeline",
            "- 2026-09-14: second",
            "  - 2026-01-01: nested, not an entry",
            "- 2026-08-01: third",
            "## How to add an entry",
            "- 2026-12-31: example, not an entry",
        ]
    )
    assert _timeline_dates(markdown) == ["2026-09-14", "2026-08-01"]
