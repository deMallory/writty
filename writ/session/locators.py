"""Project-file locators for the session helper.

POL-6d extracts these pure path-walk helpers into a low-level module shared by mode_engine
(the debug->work handoff), the gates, and the approval workflow. Keeping them here (below all
of those) breaks the would-be mode_engine<->gates dependency cycle. stdlib only; no other
writ imports.
"""

import glob
import os

# The files whose presence marks a project root. The root walk tests `any` of
# these, so order is irrelevant -- this is the single source for the set that
# was inlined across mode_engine / approval_workflow / friction / metrics and
# both walks below. NOTE: only the marker SET is shared; the walk semantics
# (cwd-inclusive vs file-dir-first) deliberately differ per caller.
PROJECT_ROOT_MARKERS = ("composer.json", "package.json", "Cargo.toml", "go.mod", "pyproject.toml", ".git")


def _find_debug_md(file_path: str) -> str | None:
    """Find debug.md for the project containing file_path.

    Walks up from the file's directory to a project marker, then checks
    debug.md, docs/debug.md, .claude/debug.md at that root. Returns the path or
    None. Distinct from _find_plan_md (different filename, not reused).
    """
    path = os.path.dirname(os.path.abspath(file_path))
    root = None
    while True:
        if any(os.path.exists(os.path.join(path, m)) for m in PROJECT_ROOT_MARKERS):
            root = path
            break
        parent = os.path.dirname(path)
        if parent == path:
            break
        path = parent
    if root is None:
        return None
    for rel in ("debug.md", os.path.join("docs", "debug.md"), os.path.join(".claude", "debug.md")):
        candidate = os.path.join(root, rel)
        if os.path.isfile(candidate):
            return candidate
    return None


def _find_plan_md(project_root: str) -> str | None:
    """Find plan.md, checking project root first then module directories."""
    candidates = [os.path.join(project_root, 'plan.md')]
    candidates += glob.glob(os.path.join(project_root, 'app/code/*/*/plan.md'))
    candidates += glob.glob(os.path.join(project_root, 'src/*/plan.md'))
    candidates += glob.glob(os.path.join(project_root, '*/plan.md'))
    found = [c for c in candidates if os.path.isfile(c)]
    if not found:
        return None
    found.sort(key=os.path.getmtime, reverse=True)
    return found[0]
