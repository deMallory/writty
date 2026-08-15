"""Locate a Grok session plan.md and copy it to the repo-root artifact.

Materialize is a copy, not a rewrite. A Grok plan that lacks Writ sections
fails the existing phase-a validator; this module will not invent them.
"""

from __future__ import annotations

import os
import shutil
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote

from writ.session.locators import resolve_project_root


def grok_home() -> Path:
    return Path(os.environ.get("GROK_HOME") or Path.home() / ".grok")


def encode_session_cwd(cwd: str) -> str:
    return quote(os.path.abspath(cwd), safe="")


def session_plan_path(cwd: str, session_id: str, home: Path | None = None) -> Path:
    return (home or grok_home()) / "sessions" / encode_session_cwd(cwd) / session_id / "plan.md"


@dataclass(frozen=True)
class MaterializeResult:
    ok: bool
    action: str
    source: str
    dest: str
    error: str = ""


def materialize_plan(
    cwd: str,
    session_id: str,
    project_root: str = "",
    force: bool = False,
    home: Path | None = None,
) -> MaterializeResult:
    """Copy the Grok session plan to <project_root>/plan.md.

    Refuses a missing or empty source. Leaves a newer repo-root plan in place
    unless force=True.
    """
    source = session_plan_path(cwd, session_id, home=home)
    root, _tier = resolve_project_root(explicit=project_root, start=os.path.abspath(cwd))
    dest = Path(root) / "plan.md" if root else Path()

    if not source.is_file():
        return MaterializeResult(
            False, "missing", str(source), str(dest),
            f"Grok session plan not found: {source}",
        )
    text = source.read_text(encoding="utf-8")
    if not text.strip():
        return MaterializeResult(
            False, "empty", str(source), str(dest),
            f"Grok session plan is empty: {source}",
        )
    if not root:
        return MaterializeResult(
            False, "no-root", str(source), "",
            "Could not resolve project root from cwd",
        )

    if dest.is_file() and not force:
        if dest.stat().st_mtime > source.stat().st_mtime:
            return MaterializeResult(
                True, "kept", str(source), str(dest),
                "repo-root plan.md is newer; pass --force to overwrite",
            )

    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, dest)
    return MaterializeResult(True, "copied", str(source), str(dest))
