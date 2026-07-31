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

# Tiers resolve_project_root reports, in the order it tries them.
ROOT_FROM_EXPLICIT = "explicit"
ROOT_FROM_MARKER = "marker"
ROOT_FROM_CWD = "cwd"
ROOT_FROM_NONE = "none"


def resolve_project_root(explicit: str = "", start: str = "") -> tuple[str, str]:
    """Resolve the project root for a gate decision. Returns (root, tier).

    Tiers, in order: an explicitly supplied root, the nearest marker dir at or above
    `start`, then `start` itself, then nothing.

    The `start`-itself tier exists because Claude Code runs ANYWHERE: a directory with
    no composer.json/package.json/Cargo.toml/go.mod/pyproject.toml/.git resolved to ""
    and the approval gate then refused every advance, so Writ's workflow was unusable
    outside conventionally-marked repos. Marker-first is kept so that working deep
    inside a repo still approves the plan.md at the repo root.

    `start` is REQUIRED for the marker and cwd tiers: this function never consults
    os.getcwd() itself. The daemon's cwd is Writ's own install dir (systemd
    WorkingDirectory), which carries both a .git and a pyproject.toml AND a plan.md, so
    an implicit cwd fallback server-side would validate Writ's own plan for someone
    else's project. Callers that legitimately mean "the user's cwd" (the CLI) pass it
    in; the server passes the cwd from the hook payload.
    """
    if explicit:
        return explicit, ROOT_FROM_EXPLICIT
    # A RELATIVE start is refused, not resolved. os.path.abspath would resolve it against
    # the calling process's cwd -- inside the daemon that is Writ's own install dir, which
    # carries .git, pyproject.toml AND a plan.md, so a caller that sent "." or "sub/dir"
    # would have the gate validate and approve WRIT'S plan for someone else's project.
    # No caller sends a relative cwd today; refusing it here is what makes the "never
    # consults os.getcwd()" guarantee above true of the code and not just of its callers.
    if not start or not os.path.isabs(start):
        return "", ROOT_FROM_NONE
    path = start
    while True:
        if any(os.path.exists(os.path.join(path, m)) for m in PROJECT_ROOT_MARKERS):
            return path, ROOT_FROM_MARKER
        parent = os.path.dirname(path)
        if parent == path:
            break
        path = parent
    return start, ROOT_FROM_CWD


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


def _is_own_project(candidate_dir: str, project_root: str) -> bool:
    """True when candidate_dir is a project in its own right, not a module of project_root.

    A monorepo module (app/code/Vendor/Module, src/pkg) carries no marker of its own, so it
    stays eligible. A sibling checkout with its own .git/package.json/pyproject.toml is a
    different project and its plan must never satisfy this project's gate. The root itself
    is never "its own project" for this purpose -- it is the project.
    """
    if os.path.normpath(candidate_dir) == os.path.normpath(project_root):
        return False
    return any(os.path.exists(os.path.join(candidate_dir, m)) for m in PROJECT_ROOT_MARKERS)


def _find_plan_md(project_root: str) -> str | None:
    """Find the plan.md the approval gate should validate.

    The root plan.md WINS when it exists. That is what the old docstring claimed, but a
    single mtime sort across every candidate meant a more recently touched plan one level
    down beat it -- so the gate could approve a plan the user was not looking at.

    Only when there is no root plan.md do the module globs apply (monorepo layouts keep a
    plan per module), newest first. A candidate whose OWN directory carries a project
    marker is dropped: that is a separate project's plan, not a module of this one. Without
    that filter, a root that resolved high (a $HOME with a .git, say) let `*/plan.md` reach
    into unrelated sibling projects and satisfy this project's gate with their plan.
    """
    root_plan = os.path.join(project_root, 'plan.md')
    if os.path.isfile(root_plan):
        return root_plan

    candidates = glob.glob(os.path.join(project_root, 'app/code/*/*/plan.md'))
    candidates += glob.glob(os.path.join(project_root, 'src/*/plan.md'))
    candidates += glob.glob(os.path.join(project_root, '*/plan.md'))
    found = [
        c for c in candidates
        if os.path.isfile(c) and not _is_own_project(os.path.dirname(c), project_root)
    ]
    if not found:
        return None
    found.sort(key=os.path.getmtime, reverse=True)
    return found[0]
