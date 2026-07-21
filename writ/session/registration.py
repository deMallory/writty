"""Register-before-capture seam for the decision-memory substrate (Phase 1b).

`ensure_project_registered` composes the git-derived identity (git_identity) with
the :Project registry (db.create_project / db.get_projects) so that the repo
containing a cwd is registered BEFORE any Decision/FileChange/Commit record is
written. It guarantees a real repo never scopes under the bare 'writ' fallback,
and that one remote_url maps to exactly one name (REUSE), never minting a second
:Project for an already-registered remote.
"""

from writ.session.git_identity import NotInRepoError, derive_project_identity


async def ensure_project_registered(
    db, cwd: str, *, bible_root: str = "bible", runner=None
) -> str | None:
    """Auto-register the repo containing cwd and return its project name.

    Returns None when cwd is in no git repo (no repo -> capture nothing); never
    returns the bare 'writ' fallback for a real repo. The name is a stable
    function of remote_url: an already-registered remote_url REUSES its existing
    name; only a new remote_url (or no remote) uses the freshly derived name.
    """
    try:
        repo_root, remote_url, derived_name = derive_project_identity(cwd, runner=runner)
    except NotInRepoError:
        return None

    name = derived_name
    if remote_url is not None:
        # REUSE lookup (remote_url -> name): if some project already carries this
        # remote_url, reuse its name instead of minting the derived one, so a
        # single remote_url maps to exactly one :Project across the registry.
        for project in await db.get_projects():
            if project.get("remote_url") == remote_url:
                name = project["name"]
                break

    await db.create_project(name, repo_root, bible_root, remote_url)
    return name
