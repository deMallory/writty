"""Git-derived project identity for the decision-memory substrate (Phase 1b).

Pure helpers that turn a working directory into a clone-stable project identity:
the repo root, the origin remote URL, and a 1:1 name derived from that remote.
The raw `git` subprocess is wrapped here behind `derive_project_identity` /
`normalize_remote_url` so the db layer and the register-before-capture seam never
shell out directly (ARCH-BOUNDARY-001). stdlib only; no other writ imports
(mirrors locators.py:1-7).
"""

import os
import re
import subprocess

# Small, explicit timeout for the git subprocess calls (ERR-HANDLE-001): a hung
# git invocation must not stall the seam.
_GIT_TIMEOUT = 5


class NotInRepoError(Exception):
    """cwd is not inside any git work tree (git rev-parse exits non-zero)."""


def normalize_remote_url(remote_url: str) -> str:
    """Map a git remote URL to a clone-stable host/org/repo name, 1:1.

    Strips the scheme (everything up to '://'), strips user@ credentials,
    converts the SSH ':' separator after the host to '/', strips a trailing
    '.git', and strips a trailing '/'. The result is always 'host/org/repo'
    and is identical across every clone of the same repo regardless of the
    https/ssh form used to clone it.
    """
    url = remote_url.strip()

    # Strip the scheme (everything up to and including '://'), e.g. 'https://'.
    scheme_split = url.split("://", 1)
    if len(scheme_split) == 2:
        url = scheme_split[1]

    # Strip 'user@' credentials (covers both https user@host and ssh git@host).
    at_split = url.rsplit("@", 1)
    if len(at_split) == 2:
        url = at_split[1]

    # Convert the SSH ':' host separator to '/'. For ssh-style remotes the form
    # is 'host:org/repo'; for https-style the host is already '/'-separated, so
    # only replace the FIRST ':' (the host separator), leaving any path intact.
    url = url.replace(":", "/", 1)

    # Strip a trailing '.git', then a trailing '/'.
    url = re.sub(r"\.git$", "", url)
    url = url.rstrip("/")

    return url


def derive_project_identity(cwd: str, *, runner=None):
    """Derive (repo_root, remote_url_or_None, name) for the repo containing cwd.

    repo_root: `git rev-parse --show-toplevel` run with cwd=cwd, abspath'd.
      When cwd is in no git repo, raises NotInRepoError.
    remote_url: `git remote get-url origin`; None when origin is absent.
    name: normalize_remote_url(remote_url) when a remote exists; otherwise the
      abspath repo_root (deterministic per machine, not clone-stable, never the
      bare 'writ' literal for a real repo).

    `runner` is an injectable callable matching subprocess.run's signature so
    tests substitute canned git output with no real repo.
    """
    run = runner or subprocess.run

    try:
        rev = run(
            ["git", "rev-parse", "--show-toplevel"],
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=_GIT_TIMEOUT,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
        raise NotInRepoError(
            f"git rev-parse failed for cwd {cwd!r}: {exc}"
        ) from exc

    if rev.returncode != 0:
        raise NotInRepoError(
            f"cwd {cwd!r} is not inside a git work tree "
            f"(git rev-parse exited {rev.returncode})"
        )

    repo_root = os.path.abspath(rev.stdout.strip())

    try:
        remote = run(
            ["git", "remote", "get-url", "origin"],
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=_GIT_TIMEOUT,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return (repo_root, None, repo_root)

    if remote.returncode != 0:
        return (repo_root, None, repo_root)

    remote_url = remote.stdout.strip()
    return (repo_root, remote_url, normalize_remote_url(remote_url))
