"""Non-clobbering git-hook installer for decision-memory Phase 1d.

install_git_hooks writes the post-commit hook body (shipped under hooks/git/) into
a repo's hooks directory inside a marker-delimited block, so a re-install replaces
the block in place (no growth) and an uninstall strips only Writ's block, leaving
any pre-existing hook content intact. The retired prepare-commit-msg hook is no
longer installed (commit messages stay normal); install/uninstall strip any block
it left behind. The hooks directory is resolved via `git rev-parse --git-common-dir`
so a worktree shares the common .git/hooks. git_hooks_installed is the marker-present
predicate (on post-commit) the CwdChanged auto-install seam guards on. stdlib only; no Neo4j.
"""

from __future__ import annotations

import os
import re
import subprocess

# The git hooks Writ installs. Only post-commit (it captures FileChange/Decision
# records to the graph). prepare-commit-msg is RETIRED: commit messages stay normal;
# the decision/rule detail lives in the per-file PR comments and the graph, not the
# commit body. install strips any already-installed retired block (migration).
_HOOK_NAMES = ("post-commit",)
_RETIRED_HOOK_NAMES = ("prepare-commit-msg",)

# The marker prefix the predicate greps on and the uninstaller strips.
_MARKER_PREFIX = "# >>> Writ"

# Small explicit timeout: a hung git invocation must not stall the seam.
_GIT_TIMEOUT = 5


def _skill_root() -> str:
    """The skill root (writ/session/git_hooks.py -> writ/ -> skill root)."""
    return os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _begin_marker(name: str) -> str:
    return f"{_MARKER_PREFIX} {name} hook >>>"


def _end_marker(name: str) -> str:
    return f"# <<< Writ {name} hook <<<"


def _hooks_dir(repo_cwd: str) -> str:
    """Resolve the hooks directory for repo_cwd, worktree-safe.

    `git rev-parse --git-common-dir` returns the shared .git dir (a worktree
    points at the main checkout's .git), so all worktrees install into one
    hooks dir. A relative result is resolved against repo_cwd.
    """
    result = subprocess.run(
        ["git", "-C", repo_cwd, "rev-parse", "--git-common-dir"],
        capture_output=True, text=True, timeout=_GIT_TIMEOUT,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"cwd {repo_cwd!r} is not inside a git work tree "
            f"(git rev-parse exited {result.returncode})"
        )
    git_common = result.stdout.strip()
    if not os.path.isabs(git_common):
        git_common = os.path.join(repo_cwd, git_common)
    return os.path.join(git_common, "hooks")


def _read_body(name: str) -> str:
    """Read the shipped hook body for `name` from hooks/git/<name>."""
    body_path = os.path.join(_skill_root(), "hooks", "git", name)
    with open(body_path) as f:
        return f.read()


def _marker_block(name: str) -> str:
    """The full marked block for `name`: begin marker, body, end marker."""
    body = _read_body(name).rstrip("\n")
    return f"{_begin_marker(name)}\n{body}\n{_end_marker(name)}\n"


def _block_pattern(name: str) -> re.Pattern:
    """A regex matching the existing marked block (begin..end, inclusive)."""
    return re.compile(
        re.escape(_begin_marker(name)) + r".*?" + re.escape(_end_marker(name)) + r"\n?",
        re.DOTALL,
    )


def _strip_blocks(hooks_dir: str, names: tuple[str, ...]) -> None:
    """Strip Writ's marked block for each `name`, deleting a file left bare.

    Shared by uninstall and by install's retired-hook cleanup so an existing
    prepare-commit-msg block is removed when a repo re-installs.
    """
    for name in names:
        hook_path = os.path.join(hooks_dir, name)
        if not os.path.exists(hook_path):
            continue
        with open(hook_path) as f:
            existing = f.read()
        stripped = _block_pattern(name).sub("", existing)
        if stripped.strip() in ("", "#!/bin/sh"):
            os.remove(hook_path)
            continue
        with open(hook_path, "w") as f:
            f.write(stripped)
        os.chmod(hook_path, 0o755)


def install_git_hooks(repo_cwd: str) -> None:
    """Install the Writ post-commit hook into repo_cwd's hooks dir, non-destructively.

    Strips any already-installed retired hook block (prepare-commit-msg) first. For
    post-commit: if absent, write a shebang plus the marked block; if present without
    the marker, append it; if the marker is present, replace it in place (idempotent,
    no growth). chmod 0o755.
    """
    hooks_dir = _hooks_dir(repo_cwd)
    os.makedirs(hooks_dir, exist_ok=True)
    _strip_blocks(hooks_dir, _RETIRED_HOOK_NAMES)
    for name in _HOOK_NAMES:
        hook_path = os.path.join(hooks_dir, name)
        block = _marker_block(name)
        if not os.path.exists(hook_path):
            content = "#!/bin/sh\n" + block
        else:
            with open(hook_path) as f:
                existing = f.read()
            pattern = _block_pattern(name)
            if pattern.search(existing):
                content = pattern.sub(block, existing)
            else:
                if existing and not existing.endswith("\n"):
                    existing += "\n"
                content = existing + block
        with open(hook_path, "w") as f:
            f.write(content)
        os.chmod(hook_path, 0o755)


def uninstall_git_hooks(repo_cwd: str) -> None:
    """Strip Writ's marked block from the current and retired hooks, preserving
    other content. Removes only the begin..end block; if only the shebang remains
    (Writ created the file from scratch), delete the file rather than leave a stub.
    """
    hooks_dir = _hooks_dir(repo_cwd)
    _strip_blocks(hooks_dir, _HOOK_NAMES + _RETIRED_HOOK_NAMES)


def git_hooks_installed(repo_cwd: str) -> bool:
    """True iff the Writ marker is present in the repo's post-commit hook."""
    hooks_dir = _hooks_dir(repo_cwd)
    hook_path = os.path.join(hooks_dir, "post-commit")
    if not os.path.exists(hook_path):
        return False
    with open(hook_path) as f:
        return _MARKER_PREFIX in f.read()
