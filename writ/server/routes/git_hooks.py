# writ-auth-scan: internal-service
"""Git-hook auto-install route.

1 route: /git-hooks/auto-install.

_db and log_friction_event are read via live `server.<attr>` access inside the
handler body (the monkeypatch seam).
"""

from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter

import writ.server as server
from writ.server.models import GitHooksAutoInstallRequest

router = APIRouter()


@router.post("/git-hooks/auto-install")
async def git_hooks_auto_install(request: GitHooksAutoInstallRequest) -> dict[str, Any]:
    """Install the Writ git hooks into a repo on first work-mode entry (Phase 1d).

    The CwdChanged seam curls this. Installs only when the marker is absent
    (idempotent): a present marker returns already=true with no rewrite. A
    non-repo project_root is a no-op. (Writ's own project keeps the name 'writ'
    via the separate `writ git-hooks bootstrap` command, not this route.) _db None
    returns the error shape; failures are logged and the route returns (fail-open,
    never blocks a session).
    """
    if server._db is None:
        return {"error": "Database not connected."}

    from writ.session import git_hooks
    from writ.session.git_identity import NotInRepoError, derive_project_identity

    # Not-in-a-repo is a no-op (never install hooks for a non-repo directory).
    try:
        derive_project_identity(request.project_root)
    except NotInRepoError:
        return {"installed": False, "already": False}

    try:
        already = git_hooks.git_hooks_installed(request.project_root)
    except Exception:
        # A non-repo project_root (git rev-parse fails) is a no-op, not an error.
        return {"installed": False, "already": False}

    if already:
        return {"installed": False, "already": True}

    try:
        git_hooks.install_git_hooks(request.project_root)
    except Exception as exc:
        await asyncio.to_thread(
            server.log_friction_event,
            session_id=request.project_root,
            mode=None,
            event="git_hooks_auto_install_failed",
            error=str(exc),
        )
        return {"installed": False, "already": False}

    return {"installed": True, "already": False}
