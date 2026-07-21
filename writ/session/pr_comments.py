"""Per-PR comment sync: the heart of the per-file PR-comment command (Phase 1e).

`sync_pr_comments` joins the PR diffstat (changed paths) to the most-recent
captured FileChange reason per path, then upserts ONE file-level PR comment per
changed path that has a reason. Our own comment is identified by its inline path
plus the visible "Posted by Writ" attribution (no HTML marker, which Bitbucket
renders visibly): a path whose comment already exists is updated-not-duplicated,
and an unchanged body posts nothing. A path
with no captured reason is skipped (no comment manufactured); an empty reason
renders the "No reason recorded" placeholder (never a blank comment). The sync
consumes only the PrHost protocol and the documented DB return shapes, so it
works with any conforming host. A non-429 create/update error FAILS LOUD (it
surfaces; there is no fallback to a line-level or general comment).
"""

from __future__ import annotations

from writ.session.pr_host import PrHost
from writ.session.remote_parse import normalize_path

NO_REASON_PLACEHOLDER = "No reason recorded"
# The visible attribution doubles as the idempotency signature: a human will not
# type it, so (inline path + this line) uniquely identifies our own comment. No
# HTML marker is used because Bitbucket renders HTML comments visibly.
_ATTRIBUTION = "_Posted by Writ_"

__all__ = [
    "NO_REASON_PLACEHOLDER",
    "normalize_path",
    "file_comment_body",
    "find_existing_comment",
    "sync_pr_comments",
    "render_commit_notes",
    "write_commit_notes",
]


def file_comment_body(
    path: str,
    change_type: str,
    reason: str,
    queried_rules: list[dict],
    cited_rules: list[dict],
) -> str:
    """Render an organized markdown file-level comment body for `path`.

    Sections: a header (path + change type), the why (reason, or the placeholder
    when empty -- never blank), the rules the AI was shown (queried, the RAG
    ground truth), the rules the AI cited (governing, self-reported in the plan),
    each entry showing the rule id AND its statement. The last line is the
    attribution, which also serves as the idempotency signature
    (find_existing_comment matches inline path + this attribution). The commit
    summary is intentionally NOT shown here -- commit messages stay normal and are
    visible on the Commits tab. A section is omitted when its list is empty.
    """
    reason_text = reason if reason else NO_REASON_PLACEHOLDER
    lines = [
        f"**Why this change** -- `{path}` ({change_type})",
        "",
        reason_text,
    ]
    if queried_rules:
        lines += ["", "**Rules the AI was shown (queried)**"]
        for rule in queried_rules:
            rid = rule.get("rule_id", "")
            statement = rule.get("statement") or ""
            lines.append(f"- **{rid}**" + (f" -- {statement}" if statement else ""))
    if cited_rules:
        lines += ["", "**Rules the AI cited (governing)**"]
        for rule in cited_rules:
            rid = rule.get("rule_id", "")
            statement = rule.get("statement") or ""
            lines.append(f"- **{rid}**" + (f" -- {statement}" if statement else ""))
    lines += ["", _ATTRIBUTION]
    return "\n".join(lines)


def _comment_inline_path(comment: dict) -> str:
    """The inline.path of a comment, or '' when not an inline/file comment."""
    return (comment.get("inline") or {}).get("path", "") or ""


def find_existing_comment(comments: list[dict], path: str) -> int | None:
    """Return the id of OUR non-deleted file-level comment for `path`, else None.

    Ours = an inline comment on this path whose body carries the Writ attribution.
    No HTML marker is used (Bitbucket renders it visibly); the attribution string
    is the human-readable idempotency signature a human would not type.
    """
    for comment in comments:
        if comment.get("deleted"):
            continue
        if _comment_inline_path(comment) != path:
            continue
        raw = (comment.get("content") or {}).get("raw", "")
        if _ATTRIBUTION in raw:
            return comment.get("id")
    return None


async def sync_pr_comments(
    host: PrHost,
    db,
    workspace: str,
    repo_slug: str,
    project: str,
    pr_id: int,
) -> dict:
    """Sync the captured per-file reasons onto a single PR. Returns counts.

    Reads the diffstat, normalizes each path, joins reasons via
    get_latest_filechange_per_path (same normalization, so the join cannot
    silently miss), lists existing comments to build the marker index, and upserts
    ONE file-level comment per changed path with a reason (create if no marker,
    update if marker found and the body changed, no-op if unchanged). A path with
    no reason is skipped. A non-429 create/update error surfaces (FAIL LOUD). A
    deleted file is commented on its old.path (already resolved by the host's
    get_pr_diffstat). Returns {created, updated, unchanged, skipped_no_reason}.
    """
    counts = {"created": 0, "updated": 0, "unchanged": 0, "skipped_no_reason": 0}

    diffstat = await host.get_pr_diffstat(workspace, repo_slug, pr_id)
    # Normalize each diffstat path so it joins the equally-normalized FileChange.
    # A host may return the resolved {path, status} form or the raw Bitbucket
    # {new, old, status} form; resolve both here without dereferencing a null
    # new/old (a deleted file uses old.path).
    changed = []
    for entry in diffstat:
        raw_path = _resolve_diffstat_path(entry)
        if not raw_path:
            continue
        changed.append({"path": normalize_path(raw_path), "status": entry.get("status")})
    paths = [entry["path"] for entry in changed]

    reasons = await db.get_latest_filechange_per_path(project, paths)
    existing_comments = await host.list_comments(workspace, repo_slug, pr_id)

    # Pass 1: read each path's queried rule ids (the RAG ground truth) and cited
    # rule ids (the governing snapshot) from the ONE stable FileChange record, then
    # accumulate the union so statements are fetched in ONE batched query.
    cited_ids_by_path: dict[str, list[str]] = {}
    queried_ids_by_path: dict[str, list[str]] = {}
    all_rule_ids: list[str] = []
    for entry in changed:
        path = entry["path"]
        record = reasons.get(path)
        if record is None:
            continue
        queried = record.get("queried_rule_ids") or []
        queried_ids_by_path[path] = queried
        # cited is the commit-time snapshot on the FileChange (cited_rule_ids), NOT
        # a live get_open_decisions_for_path lookup: the claim is resolved by the
        # time pr sync runs, so a live lookup would render empty. Reading the
        # snapshot makes the comment render identically after the claim resolves.
        cited = record.get("cited_rule_ids") or []
        cited_ids_by_path[path] = cited
        for rid in list(queried) + list(cited):
            if rid not in all_rule_ids:
                all_rule_ids.append(rid)
    statements = await db.get_rule_statements(all_rule_ids)

    for entry in changed:
        path = entry["path"]
        record = reasons.get(path)
        if record is None:
            counts["skipped_no_reason"] += 1
            continue

        reason = record.get("reason") or ""
        change_type = record.get("change_type") or entry.get("status") or ""
        queried_rules = [
            {"rule_id": rid, "statement": statements.get(rid, "")}
            for rid in queried_ids_by_path.get(path, [])
        ]
        cited_rules = [
            {"rule_id": rid, "statement": statements.get(rid, "")}
            for rid in cited_ids_by_path.get(path, [])
        ]
        body = file_comment_body(path, change_type, reason, queried_rules, cited_rules)
        existing_id = find_existing_comment(existing_comments, path)

        if existing_id is None:
            await host.create_file_comment(workspace, repo_slug, pr_id, path, body)
            counts["created"] += 1
            continue

        existing_body = _existing_body(existing_comments, existing_id)
        if existing_body == body:
            counts["unchanged"] += 1
            continue

        await host.update_comment(workspace, repo_slug, pr_id, existing_id, body)
        counts["updated"] += 1

    return counts


def _resolve_diffstat_path(entry: dict) -> str | None:
    """Return the path for a diffstat entry, accepting resolved or raw forms.

    A resolved entry carries 'path' directly. A raw Bitbucket entry carries
    new/old objects: path = new.path when new and new.path are present, else
    old.path (a deleted file). A null new/old is never dereferenced.
    """
    if entry.get("path"):
        return entry["path"]
    new = entry.get("new")
    old = entry.get("old")
    if new and new.get("path"):
        return new["path"]
    if old and old.get("path"):
        return old["path"]
    return None


def _existing_body(comments: list[dict], comment_id: int) -> str:
    """Return the raw body of the comment with `comment_id`, or '' when absent."""
    for comment in comments:
        if comment.get("id") == comment_id:
            return (comment.get("content") or {}).get("raw", "")
    return ""


# --- Commit-notes channel (relocated from writ/cli.py) -----------------------


async def render_commit_notes(
    db, host, workspace: str, repo_slug: str, project: str, pr_id: int
) -> dict[str, str]:
    """Return {commit_hash: note_body}: per commit, the concatenated file_comment_body
    for each changed path on that commit, joined by a horizontal rule. Fetches the
    diffstat + FileChange records + statements independently of sync_pr_comments (the
    notes channel is decoupled); it applies the SAME file_comment_body renderer, so
    each note body matches the corresponding PR comment."""
    diffstat = await host.get_pr_diffstat(workspace, repo_slug, pr_id)
    paths: list[str] = []
    for entry in diffstat:
        raw = entry.get("path") or (entry.get("new") or {}).get("path") or (entry.get("old") or {}).get("path")
        if raw:
            paths.append(normalize_path(raw))
    records = await db.get_latest_filechange_per_path(project, paths)

    all_ids: list[str] = []
    for rec in records.values():
        for rid in (rec.get("queried_rule_ids") or []) + (rec.get("cited_rule_ids") or []):
            if rid not in all_ids:
                all_ids.append(rid)
    statements = await db.get_rule_statements(all_ids)

    by_commit: dict[str, list[str]] = {}
    for path in paths:
        rec = records.get(path)
        if rec is None:
            continue
        commit_hash = rec.get("commit_hash")
        if not commit_hash:
            continue
        queried_rules = [
            {"rule_id": rid, "statement": statements.get(rid, "")}
            for rid in (rec.get("queried_rule_ids") or [])
        ]
        cited_rules = [
            {"rule_id": rid, "statement": statements.get(rid, "")}
            for rid in (rec.get("cited_rule_ids") or [])
        ]
        body = file_comment_body(
            path, rec.get("change_type") or "", rec.get("reason") or "",
            queried_rules, cited_rules,
        )
        by_commit.setdefault(commit_hash, []).append(body)

    return {ch: "\n\n---\n\n".join(bodies) for ch, bodies in by_commit.items()}


def write_commit_notes(repo_root: str, notes_by_commit: dict[str, str]) -> int:
    """Write one git note per commit on the writ-decisions ref, then push once.

    Returns the number of notes written. Uses cwd=repo_root on every subprocess.
    A push failure logs a warning and is swallowed (offline / perms must not fail
    the PR sync); the notes are already written locally."""
    import logging
    import subprocess

    log = logging.getLogger("writ.pr_sync")
    written = 0
    for commit_hash, body in notes_by_commit.items():
        # Per-note write is guarded: a single bad object (e.g. an amended/missing
        # commit hash) must not abort the whole pr sync or drop the other notes.
        try:
            subprocess.run(
                ["git", "notes", "--ref=writ-decisions", "add", "-f", "-m", body, commit_hash],
                cwd=repo_root, check=True,
            )
            written += 1
        except subprocess.CalledProcessError:
            log.warning("git notes add failed for %s (skipped); others continue", commit_hash)
    if written:
        try:
            subprocess.run(
                ["git", "push", "origin",
                 "refs/notes/writ-decisions:refs/notes/writ-decisions"],
                cwd=repo_root, check=True,
            )
        except subprocess.CalledProcessError:
            log.warning(
                "git push of refs/notes/writ-decisions failed (offline/perms?); "
                "notes are written locally"
            )
    return written
