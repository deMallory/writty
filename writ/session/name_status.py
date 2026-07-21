"""Parser for `git diff --cached --name-status` / `git diff-tree --name-status`
output (decision-memory Phase 1d).

Pure, stdlib-only, no git and no Neo4j so the parse is unit-testable without a
repo. Each output line is TAB-separated. A/M/D/T lines carry one status letter and
one path; R/C lines carry a status with a similarity score (e.g. "R100", "C75")
plus the old path and the new path. The status letter maps to a stable
change_type used throughout the commit-capture path.
"""

from __future__ import annotations

# Map the git status letter to the change_type recorded on a FileChange.
_STATUS_CHANGE_TYPE = {
    "A": "add",
    "M": "modify",
    "D": "delete",
    "T": "modify",
    "R": "rename",
    "C": "rename",
}


def parse_name_status(text: str) -> list[dict]:
    """Parse name-status output into a list of {path, change_type[, old_path]}.

    A/M/D/T lines produce {path, change_type} (single path). R/C lines produce
    {path, change_type, old_path} where path is the NEW path and old_path is the
    OLD path; the status field carries a similarity score (R100, C75) so only its
    first letter is read. Empty or whitespace-only input returns [] (an empty
    commit or a clean merge).
    """
    entries: list[dict] = []
    for line in text.splitlines():
        if not line.strip():
            continue
        parts = line.split("\t")
        status = parts[0].strip()
        if not status:
            continue
        letter = status[0]
        change_type = _STATUS_CHANGE_TYPE.get(letter, "modify")
        if letter in ("R", "C"):
            if len(parts) < 3:
                continue
            old_path = parts[1]
            new_path = parts[2]
            entries.append(
                {
                    "path": new_path,
                    "change_type": change_type,
                    "old_path": old_path,
                }
            )
        else:
            if len(parts) < 2:
                continue
            entries.append({"path": parts[1], "change_type": change_type})
    return entries
