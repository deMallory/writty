"""P3 logging backup: an off-root copy of the compressed archive generations.

`backup_archives(dest)` walks the central Writ log root once and copies every
gzipped archive generation (`archive/<stream>-<date>[.-N].jsonl.gz`) to
`dest / <path-relative-to-root>`, so the `<project>/archive/` layout (including
nested project scopes like `github.com/org/repo`) is preserved intact.

Matching keys off the P2 `_ARCHIVE_GZ_RE` filename invariant imported DOWN from
`writ.session.log_rotation` (DRY-DUP-001): because only the `.jsonl.gz` shape
matches, backup structurally cannot touch a live `<stream>.jsonl` or an
uncompressed archive `.jsonl` generation. It COPIES (`shutil.copy2`, preserving
mtime); the source of record stays in place. Idempotent: a dest file that
already exists with the same byte size AND mtime is skipped, otherwise it is
re-copied (`shutil.copy2` preserves mtime, so a genuine re-run of the same
archive still skips on the second pass).

The `dest` subtree is pruned from the walk (`dirnames` mutation on the topdown
`os.walk`) so a `dest` that lives UNDER the log root never re-copies backup's own
previous `.jsonl.gz` output into itself, which would otherwise nest
`backup/backup/...` deeper every run and grow disk without bound.

Fail-soft (ERR-HANDLE-003): each file copy is wrapped in its own try/except so a
single unreadable source or an uncreatable dest is counted and the run
continues; the function never raises. A missing log root yields an all-zero
summary. stdlib only; no daemon, no Neo4j (ARCH-LAYER-001).
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path

from writ.session.log_rotation import _ARCHIVE_GZ_RE
from writ.shared.logging import log_root


def backup_archives(dest: str | Path, *, root: Path | None = None) -> dict:
    """Copy every gzipped archive generation under `root` to `dest`, preserving
    the `<project>/archive/` layout. Returns `{"copied", "skipped", "bytes",
    "errors"}` int counts and never raises.

    `root` defaults to `log_root()` (an injectable kwarg so a caller can point
    backup at an arbitrary tree). `bytes` is the total size of the files copied
    this run (skipped files do not contribute).
    """
    summary = {"copied": 0, "skipped": 0, "bytes": 0, "errors": 0}
    base = Path(root) if root is not None else log_root()
    dest_root = Path(dest)
    if not base.is_dir():
        return summary

    # Prune the dest subtree so a dest UNDER the log root never re-copies backup's
    # own prior output into itself (unbounded backup/backup/... nesting).
    dest_abs = dest_root.resolve()
    for dirpath, dirnames, filenames in os.walk(base):  # topdown so the prune takes
        dirnames[:] = [
            d for d in dirnames if (Path(dirpath) / d).resolve() != dest_abs
        ]
        for fn in filenames:
            if not _ARCHIVE_GZ_RE.match(fn):
                continue
            src = Path(dirpath) / fn
            target = dest_root / src.relative_to(base)
            try:
                src_stat = os.stat(src)
                if target.exists():
                    tgt_stat = os.stat(target)
                    # Archive generations are write-once-immutable, but skipping on
                    # size AND mtime hardens against a same-size-different-content
                    # dest (copy2 preserves mtime, so a true re-run still skips).
                    if (
                        tgt_stat.st_size == src_stat.st_size
                        and tgt_stat.st_mtime_ns == src_stat.st_mtime_ns
                    ):
                        summary["skipped"] += 1
                        continue
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, target)
                summary["copied"] += 1
                summary["bytes"] += src_stat.st_size
            except OSError:
                summary["errors"] += 1
                continue

    return summary
