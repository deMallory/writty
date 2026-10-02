"""Pair Ledger gatherers: the rules Claude follows and the memory it keeps.

Three read-only queries behind the /dashboard sections of the same names:
rule_sources(), memory_copies() and stale_notes(). Each takes `home` (default
Path.home()) so tests can point it at a temporary directory, and none writes to
disk or graph. The dashboard composes; it never computes these itself.

Nothing is hard-coded to one machine. Project directories come from
~/.claude/projects/<encoded>/, and the working directory each one stands for comes
from the `cwd` its newest transcript records.
"""
from __future__ import annotations

import functools
import importlib.util
import json
import re
import subprocess
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from types import ModuleType
from typing import Any

# A hung git (network filesystem, lock contention) must not hang the page.
_GIT_TIMEOUT_SECONDS = 5
_BULLET_RE = re.compile(r"^\s*[-*+] ")
_NAMED_PATH_RE = re.compile(r"~/[^\s`'\"()<>\[\]]+\.md")
# A worktree cwd copies a repo that is already listed through its main checkout.
_WORKTREE_SEGMENT = "/.claude/worktrees/"


@dataclass(frozen=True)
class RuleSource:
    label: str
    display_path: str
    rules: int | None
    changed: str | None
    sync: str


@dataclass(frozen=True)
class ProjectCopies:
    project: str
    copied: int
    outdated: int
    missing: int
    outdated_names: tuple[str, ...] = ()


@dataclass(frozen=True)
class StaleNote:
    name: str
    project: str
    changed: str
    age_days: int


@dataclass(frozen=True)
class _Project:
    directory: Path
    cwd: Path | None

    @property
    def label(self) -> str:
        return self.cwd.name if self.cwd else self.directory.name


@functools.cache
def _memory_capture() -> ModuleType:
    """bin/lib/memory_capture.py, the parser the mirror hook and the backfill use.

    Loaded by path, the same idiom as writ/cli.py::_memory_capture: it is a
    stdlib-only hook script, not a package. Sharing it means a note parses here to
    exactly the name, description and body the graph would hold.
    """
    module_path = Path(__file__).resolve().parents[2] / "bin" / "lib" / "memory_capture.py"
    spec = importlib.util.spec_from_file_location("writ_memory_capture", str(module_path))
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _date(timestamp: float) -> str:
    return datetime.fromtimestamp(timestamp, UTC).strftime("%Y-%m-%d")


def _read(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None


def _git(cwd: Path, *args: str) -> subprocess.CompletedProcess[str] | None:
    try:
        return subprocess.run(
            ["git", *args], cwd=cwd, capture_output=True, text=True,
            timeout=_GIT_TIMEOUT_SECONDS, check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None


def _tracked(path: Path) -> bool:
    result = _git(path.parent, "ls-files", "--error-unmatch", "--", path.name)
    return result is not None and result.returncode == 0


def _commit_date(path: Path) -> str | None:
    result = _git(path.parent, "log", "-1", "--format=%cs", "--", path.name)
    if result is None or result.returncode != 0:
        return None
    return result.stdout.strip() or None


def _transcript_cwd(directory: Path) -> Path | None:
    """The `cwd` the newest transcript records first, or None."""
    transcripts = []
    for transcript in directory.glob("*.jsonl"):
        try:
            transcripts.append((transcript.stat().st_mtime, transcript))
        except OSError:
            continue
    if not transcripts:
        return None
    newest = max(transcripts)[1]
    try:
        with newest.open(encoding="utf-8", errors="replace") as lines:
            for line in lines:
                try:
                    record = json.loads(line)
                except ValueError:
                    continue
                cwd = record.get("cwd") if isinstance(record, dict) else None
                if isinstance(cwd, str) and cwd:
                    return Path(cwd)
    except OSError:
        return None
    return None


def _projects(home: Path) -> list[_Project]:
    root = home / ".claude" / "projects"
    try:
        directories = sorted(d for d in root.iterdir() if d.is_dir())
    except OSError:
        return []
    return [_Project(d, _transcript_cwd(d)) for d in directories]


def _repo_cwds(projects: list[_Project]) -> list[Path]:
    """Working directories outside worktrees, once each, in project order."""
    seen: dict[str, Path] = {}
    for project in projects:
        cwd = project.cwd
        if cwd is None or _WORKTREE_SEGMENT in f"{cwd}/" or not cwd.is_dir():
            continue
        seen.setdefault(str(cwd), cwd)
    return list(seen.values())


def _display(path: Path, home: Path) -> str:
    try:
        return f"~/{path.relative_to(home)}"
    except ValueError:
        return str(path)


def _twin_state(path: Path, real: Path, home: Path, repos: list[Path]) -> str | None:
    """`copy in <repo>, same|differs` for a home file a discovered repo tracks a twin of."""
    try:
        relative = path.relative_to(home)
    except ValueError:
        return None
    for repo in repos:
        twin = repo / relative
        if not twin.is_file() or twin.resolve() == real or not _tracked(twin.resolve()):
            continue
        try:
            same = real.read_bytes() == twin.read_bytes()
        except OSError:
            continue
        return f"copy in {repo.name}, {'same' if same else 'differs'}"
    return None


def _rule_source(label: str, path: Path, home: Path, repos: list[Path]) -> RuleSource:
    display = _display(path, home)
    text = _read(path)
    if text is None:
        return RuleSource(label, display, None, None, "missing")
    rules = sum(1 for line in text.splitlines() if _BULLET_RE.match(line))
    real = path.resolve()
    if _tracked(real):
        return RuleSource(label, display, rules, _commit_date(real), "in git")
    # lstat: a symlinked file (home-manager points into the Nix store, where every
    # mtime is 1970) last changed when the link was laid down, not at its target's mtime.
    try:
        changed: str | None = _date(path.lstat().st_mtime)
    except OSError:
        changed = None
    sync = _twin_state(path, real, home, repos) or "this Mac only"
    return RuleSource(label, display, rules, changed, sync)


def rule_sources(home: Path | None = None) -> list[RuleSource]:
    """Every instructions file Claude loads: global, output styles, files the global
    names, then each project's CLAUDE.md. Once each, by resolved path."""
    home = home or Path.home()
    claude = home / ".claude"
    global_md = claude / "CLAUDE.md"
    candidates: list[tuple[str, Path]] = [("global", global_md)]
    try:
        candidates += [("output style", p) for p in sorted((claude / "output-styles").glob("*.md"))]
    except OSError:
        pass
    named = _NAMED_PATH_RE.findall(_read(global_md) or "")
    candidates += [("named in global", home / match[2:]) for match in named]

    repos = _repo_cwds(_projects(home))
    for cwd in repos:
        for path in (cwd / "CLAUDE.md", cwd / ".claude" / "CLAUDE.md"):
            if path.is_file():
                candidates.append(("project", path))

    sources: list[RuleSource] = []
    seen: set[Path] = set()
    for label, path in candidates:
        key = path.resolve()
        if key in seen:
            continue
        seen.add(key)
        # An absent global or project file is just not there; a named one is a finding.
        if label in ("global", "project") and not path.exists():
            continue
        sources.append(_rule_source(label, path, home, repos))
    return sources


def _notes(project: _Project) -> list[Path]:
    """The project's memory notes, without the MEMORY.md index."""
    index = _memory_capture().is_memory_index_file
    try:
        return sorted(p for p in (project.directory / "memory").glob("*.md") if not index(str(p)))
    except OSError:
        return []


def memory_copies(
    rows: list[dict[str, Any]] | None, home: Path | None = None
) -> list[ProjectCopies] | None:
    """Per project: notes whose graph copy matches, differs, or does not exist.

    `rows` are list_all_memories() rows; None means the graph was not reachable,
    and the answer is None rather than a table claiming every note is uncopied.
    A tombstoned node is no copy.
    """
    if rows is None:
        return None
    home = home or Path.home()
    capture = _memory_capture()
    live = {
        (row.get("project"), row.get("name")): row
        for row in rows
        if (row.get("status") or "live") != "deleted"
    }
    result: list[ProjectCopies] = []
    for project in _projects(home):
        copied = missing = 0
        outdated: list[str] = []
        for path in _notes(project):
            payload = capture.build_memory_payload(str(path), _read(path) or "")
            if payload is None:
                continue
            row = live.get((payload["project"], payload["name"]))
            if row is None:
                missing += 1
            elif (row.get("description"), row.get("body")) == (payload["description"], payload["body"]):
                copied += 1
            else:
                outdated.append(payload["name"])
        if copied or outdated or missing:
            result.append(ProjectCopies(project.label, copied, len(outdated), missing, tuple(outdated)))
    result.sort(key=lambda p: (-(p.copied + p.outdated + p.missing), p.project))
    return result


def stale_notes(
    home: Path | None = None, *, min_age_days: int = 90, now: datetime | None = None
) -> list[StaleNote]:
    """Memory notes whose file has not changed in `min_age_days` or more, oldest first."""
    home = home or Path.home()
    now = now or datetime.now(UTC)
    stale: list[StaleNote] = []
    for project in _projects(home):
        for path in _notes(project):
            try:
                mtime = path.stat().st_mtime
            except OSError:
                continue
            age = (now - datetime.fromtimestamp(mtime, UTC)).days
            if age >= min_age_days:
                stale.append(StaleNote(path.stem, project.label, _date(mtime), age))
    stale.sort(key=lambda n: (-n.age_days, n.project, n.name))
    return stale
