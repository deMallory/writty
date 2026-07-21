"""Project registry (create_project is the TOCTOU/CAS keystone).

Moved verbatim from the former writ/graph/db.py (Wave 2 mixin split); methods read self._driver / self._database set by Neo4jConnection.__init__."""
from __future__ import annotations

from writ.graph.db._common import (
    ProjectIdentityConflict,
)


class ProjectStoreMixin:
    async def create_project(
        self, name: str, repo_root: str, bible_root: str, remote_url: str | None = None
    ) -> str:
        """Register (or update) a project atomically. Idempotent via MERGE on name.

        remote_url is additive cross-clone identity (the dedup key); the scope key
        stays = name (M.1-compatible). A None remote_url argument never nulls an
        existing value, so a 3-arg call preserves any registered remote_url.

        C4 (audit): a single MERGE + guarded conditional SET + result read, replacing
        the former read-then-separate-MERGE check-then-act race (two concurrent
        conflicting creates could both pass the read check, and the loser's
        unconditional SET silently overwrote the winner). remote_url is set ONLY when
        a non-null arg is given AND the stored value is currently NULL
        (first-writer-wins). The unconditional SET of repo_root/bible_root forces the
        node write-lock BEFORE the FOREACH reads p.remote_url (the _cas_lock keystone),
        and the RETURNed stored remote_url drives the ProjectIdentityConflict raise, so
        a concurrent conflicting create raises rather than silently overwriting. The
        project_name_unique constraint (apply_constraints) serializes concurrent MERGE
        creates so the loser MATCHES the winner's committed node.
        """
        rec = await self._run_single(
            "MERGE (p:Project {name: $name}) "
            "SET p.repo_root = $repo_root, p.bible_root = $bible_root "
            "FOREACH (_ IN CASE WHEN $remote_url IS NOT NULL AND p.remote_url IS NULL "
            "THEN [1] ELSE [] END | SET p.remote_url = $remote_url) "
            "RETURN p.name AS name, p.remote_url AS remote_url",
            name=name, repo_root=repo_root, bible_root=bible_root,
            remote_url=remote_url,
        )
        stored_remote = rec["remote_url"]
        if (
            remote_url is not None
            and stored_remote is not None
            and stored_remote != remote_url
        ):
            raise ProjectIdentityConflict(
                f"project {name!r} is already bound to remote_url "
                f"{stored_remote!r}; refusing to overwrite with {remote_url!r}"
            )
        return rec["name"]

    async def get_projects(self) -> list[dict]:
        """All registered projects as {name, repo_root, bible_root, remote_url}."""
        rows = await self._run(
            "MATCH (p:Project) RETURN p.name AS name, p.repo_root AS repo_root, "
            "p.bible_root AS bible_root, p.remote_url AS remote_url ORDER BY name"
        )
        return [dict(r) for r in rows]

    async def resolve_project_for_cwd(self, cwd: str, default: str = "writ") -> str:
        """Map a working directory to its project by longest repo_root prefix.

        A cwd under a registered project's repo_root resolves to that project;
        the longest matching repo_root wins (nested repos). Falls back to
        `default` ('writ') when no registered repo_root is a prefix -- so a
        single-project install (or an unregistered cwd) behaves as today.
        """
        projects = await self.get_projects()
        best_name, best_len = default, -1
        for p in projects:
            root = p.get("repo_root") or ""
            if root and (cwd == root or cwd.startswith(root.rstrip("/") + "/")):
                if len(root) > best_len:
                    best_name, best_len = p["name"], len(root)
        return best_name
