# writ-auth-scan: internal-service
"""Decision-memory routes: commit capture + recall.

2 routes: /commit/capture, /recall.

_db, capture_commit and log_friction_event are read via live `server.<attr>`
access inside handler bodies (the monkeypatch seam).
"""

from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter

import writ.server as server
from writ.server.models import CommitCaptureRequest, RecallRequest

router = APIRouter()


@router.post("/commit/capture")
async def commit_capture(request: CommitCaptureRequest) -> dict[str, Any]:
    """Create the Commit + FileChange records for a landed commit (Phase 1d).

    The post-commit hook curls this. The capture runs inside a try/except so a
    failure (including the DB raising) is logged and the route still returns
    (fail-open): a commit is never blocked by a graph-write failure. _db None
    returns the error shape without raising.
    """
    if server._db is None:
        return {"error": "Database not connected."}

    try:
        await server.capture_commit(
            server._db,
            cwd=request.project_root,
            commit_hash=request.commit_hash,
            subject=request.subject,
            author=request.author,
            branch=request.branch,
            files=request.files,
            session_id=request.session_id,
        )
    except Exception as exc:
        await asyncio.to_thread(
            server.log_friction_event,
            session_id=request.commit_hash,
            mode=None,
            event="commit_capture_failed",
            error=str(exc),
        )
        return {"ok": True}
    return {"ok": True}


@router.post("/recall")
async def recall(request: RecallRequest) -> dict[str, Any]:
    """Compile the project's recent rule-grounded Decisions (Phase 2 recall).

    The first-prompt briefing hook and `writ recall` both reach this route.
    Recall is a SEPARATE project-scoped read (Decision is excluded from the RAG
    pipeline), scoped to the project resolved from the caller's cwd. Fail-open:
    _db None returns the error shape, and any failure is logged and returns an
    empty-but-valid payload so a recall failure never blocks a prompt.

    Access boundary: localhost-only daemon route, single-user, no auth tier;
    reads project-scoped Decision records on the caller's own machine.
    """
    if server._db is None:
        return {"error": "Database not connected."}

    try:
        from writ.session.recall import compile_recall

        project = await server._db.resolve_project_for_cwd(request.project_root)
        payload = await compile_recall(
            server._db, project, budget=request.budget, full=request.full
        )
    except Exception as exc:
        try:
            await asyncio.to_thread(
                server.log_friction_event,
                session_id=request.project_root,
                mode=None,
                event="recall_failed",
                error=str(exc),
            )
        except Exception:
            pass
        return {"ok": True, "briefing": "", "decisions": []}
    return {"ok": True, "briefing": payload["briefing"], "decisions": payload["decisions"]}
