"""The PrHost protocol: the swappable host boundary for PR-comment sync (Phase 1e).

`PrHost` is the narrow typing.Protocol the command and `sync_pr_comments` depend
on, never `BitbucketClient` concretely (ARCH-BOUNDARY-001, SOLID-LSP-001,
SOLID-ISP-002). It declares exactly the five methods the per-PR sync uses, so a
future `GitHubClient` can satisfy the same surface without inheriting unused
methods or raising NotImplementedError.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class PrHost(Protocol):
    """The host contract the PR-comment sync consumes.

    Any conforming client (BitbucketClient now, a GitHubClient later) is
    substitutable wherever a PrHost is expected: same preconditions, same
    documented return shapes.
    """

    async def find_open_pr(
        self, workspace: str, repo_slug: str, source_branch: str
    ) -> int | None:
        """Return the id of the open PR for `source_branch`, or None when none."""
        ...

    async def get_pr_diffstat(
        self, workspace: str, repo_slug: str, pr_id: int
    ) -> list[dict]:
        """Return the PR's changed entries as [{path, status}, ...]."""
        ...

    async def create_file_comment(
        self, workspace: str, repo_slug: str, pr_id: int, path: str, body: str
    ) -> dict:
        """Create one file-level PR comment on `path` and return the created dict."""
        ...

    async def list_comments(
        self, workspace: str, repo_slug: str, pr_id: int
    ) -> list[dict]:
        """Return the PR's non-deleted comment dicts."""
        ...

    async def update_comment(
        self, workspace: str, repo_slug: str, pr_id: int, comment_id: int, body: str
    ) -> dict:
        """Update an existing comment's body and return the updated dict."""
        ...
