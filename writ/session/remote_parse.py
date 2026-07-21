"""Bitbucket remote-URL parsing for the per-file PR-comment command (Phase 1e).

Derives (workspace, repo_slug) from a project's `remote_url` via the shared
`normalize_remote_url` (git_identity) and enforces the `{bitbucket.org}` host
allowlist in one audited place BEFORE any request URL is built (SEC-INJ-SSRF-001).
A non-bitbucket.org host (e.g. a self-hosted bitbucket.mycompany.com) returns
None, never an exception, so the workspace/slug can only ever flow into a path on
the hardcoded API base host and never into the host position.
"""

from __future__ import annotations

from writ.session.git_identity import normalize_remote_url

# The single allowlisted remote host. A self-hosted Bitbucket Server or any other
# host is rejected at parse time so a derived workspace/slug never reaches a
# non-allowlisted destination.
_ALLOWED_REMOTE_HOST = "bitbucket.org"


def parse_bitbucket_remote(remote_url: str | None) -> tuple[str, str] | None:
    """Return (workspace, repo_slug) for a bitbucket.org remote, else None.

    normalize_remote_url maps both the https and ssh forms to 'host/org/repo'.
    Returns (workspace, repo_slug) only when the first segment is 'bitbucket.org'
    and at least three segments exist; otherwise None (host allowlist reject, no
    exception). A None or empty remote_url returns None.
    """
    if not remote_url:
        return None

    normalized = normalize_remote_url(remote_url)
    parts = normalized.split("/")
    if len(parts) < 3 or parts[0] != _ALLOWED_REMOTE_HOST:
        return None

    return (parts[1], parts[2])


def normalize_path(path: str) -> str:
    """Repo-root-relative normalization shared by diffstat and FileChange paths.

    Strips a single leading './' then a single leading '/', with no case folding.
    Applied IDENTICALLY to a diffstat path and a FileChange path before the
    IN-list lookup so the join cannot silently miss (a './x' diffstat path vs an
    'x' FileChange path).
    """
    if path.startswith("./"):
        path = path[2:]
    if path.startswith("/"):
        path = path[1:]
    return path
