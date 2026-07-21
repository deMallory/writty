"""P3 logging read surface: fail-open helpers behind `writ logs [tail|stats|list]`.

Lets an operator inspect the durable typed streams without hand-navigating the
central log root, and without any full-file parse (PERF-IO-001):

  - `tail_stream(project, stream, n)` returns the last N raw JSON lines of a
    stream via a bounded backward read (`_tail_lines`), never slurping the file.
  - `stream_stats(project)` reports per-present-stream cheap counts: live line
    count (chunked newline count), live byte size (`os.stat`), gzipped archive
    generation count, and oldest/newest `ts` read from only the first and the
    tailed-last line.
  - `list_projects(project=None)` inventories projects from a directory scan
    only (`_discover_projects`), with each project's live streams + sizes and
    its archive generation count.

Filename invariants are reused DOWN from `writ.session.log_rotation`
(`_KNOWN_STREAMS`, `_is_live_stream_file`, `_ARCHIVE_GZ_RE`) so a nested scope
like `github.com/org/repo` enumerates correctly and a project literally named
`archive` is never mistaken for the `archive/` generations folder (the P2
data-loss regression class). Every helper degrades to empty/zero on a missing,
empty, or unreadable file (ERR-HANDLE-003); none raises. stdlib only; no daemon,
no Neo4j (ARCH-LAYER-001).
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from writ.session.log_rotation import (
    _ARCHIVE_GZ_RE,
    _KNOWN_STREAMS,
    _is_live_stream_file,
)
from writ.shared.logging import archive_dir, log_root, stream_path

# Bounded backward-read block size for `_tail_lines`; parameterized so a test can
# force cross-block correctness with a tiny value (PERF-IO-001 / TEST-PERF-001).
_TAIL_BLOCK_SIZE = 8192
# Chunk size for the cheap forward newline/byte scans in `stream_stats`.
_SCAN_BLOCK_SIZE = 1 << 16


def _tail_lines(path: str | Path, n: int, block_size: int = _TAIL_BLOCK_SIZE) -> list[str]:
    """Return the last `n` lines of `path`, newest last, via a bounded backward
    read (seek from the end in `block_size` chunks until `n` complete lines or the
    file start). Never slurps the whole file. `n <= 0` or a missing/unreadable
    file -> `[]`."""
    if n <= 0:
        return []
    try:
        with open(path, "rb") as fh:
            fh.seek(0, os.SEEK_END)
            pos = fh.tell()
            if pos == 0:
                return []
            blocks: list[bytes] = []
            newlines = 0
            # Read backward until we have captured n+1 newlines (which guarantees
            # the last n lines are complete) or we reach the start of the file.
            while pos > 0 and newlines <= n:
                read_size = min(block_size, pos)
                pos -= read_size
                fh.seek(pos)
                chunk = fh.read(read_size)
                blocks.append(chunk)
                newlines += chunk.count(b"\n")
            data = b"".join(reversed(blocks))
    except OSError:
        return []
    lines = data.decode("utf-8", errors="replace").splitlines()
    return lines[-n:]


def tail_stream(project: str, stream: str, n: int) -> list[str]:
    """Return the last `n` raw lines of a project's stream, newest last. `n <= 0`
    or a missing/unreadable stream file -> `[]` (fail-open)."""
    if n <= 0:
        return []
    return _tail_lines(stream_path(project, stream), n)


def _safe_size(path: Path) -> int:
    """`os.stat` byte size of `path`, or 0 when it is missing/unstattable."""
    try:
        return os.stat(path).st_size
    except OSError:
        return 0


def _count_lines(path: Path) -> int:
    """Cheap chunked newline count for `path` (no whole-file parse). 0 on error."""
    count = 0
    try:
        with open(path, "rb") as fh:
            while True:
                chunk = fh.read(_SCAN_BLOCK_SIZE)
                if not chunk:
                    break
                count += chunk.count(b"\n")
    except OSError:
        return 0
    return count


# How many tail lines to scan backward for the newest non-blank line -- a log may
# end with a trailing blank line (or a couple), so the literal last line is not
# reliably the newest event.
_NEWEST_TAIL_WINDOW = 5


def _first_nonblank_line(path: Path) -> str | None:
    """The first NON-BLANK line of `path`, read forward line-by-line (bounded to
    the leading blank run, not the whole file). None if empty or unreadable.

    A leading blank line must not mask the oldest event on the adjacent line.
    """
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            for raw in fh:
                stripped = raw.strip()
                if stripped:
                    return stripped
    except OSError:
        return None
    return None


def _last_nonblank_line(path: Path) -> str | None:
    """The last NON-BLANK line of `path`, chosen from a small backward tail window
    so a trailing blank line does not mask the newest event. None if none found."""
    tail = _tail_lines(path, _NEWEST_TAIL_WINDOW)
    return next((ln for ln in reversed(tail) if ln.strip()), None)


def _ts_of(line: str | None) -> str | None:
    """The `ts` field of one JSON log line, or None if absent/unparseable."""
    if not line:
        return None
    try:
        obj = json.loads(line)
    except (json.JSONDecodeError, ValueError):
        return None
    ts = obj.get("ts") if isinstance(obj, dict) else None
    return ts if isinstance(ts, str) else None


def _archive_count(project: str, stream: str | None = None) -> int:
    """Count gzipped archive generations in a project's `archive/` dir, optionally
    filtered to a single `stream`. 0 when the dir is missing/unreadable."""
    arc = archive_dir(project)
    if not arc.is_dir():
        return 0
    count = 0
    try:
        for fn in os.listdir(arc):
            match = _ARCHIVE_GZ_RE.match(fn)
            if match and (stream is None or match.group("stream") == stream):
                count += 1
    except OSError:
        return 0
    return count


def stream_stats(project: str) -> dict[str, dict]:
    """Per-present-stream cheap stats for a project: `{live_lines, live_bytes,
    archive_count, oldest_ts, newest_ts}`. Only streams whose live file exists are
    reported; a project with no logs -> `{}`."""
    stats: dict[str, dict] = {}
    for stream in sorted(_KNOWN_STREAMS):
        path = stream_path(project, stream)
        if not path.is_file():
            continue
        stats[stream] = {
            "live_lines": _count_lines(path),
            "live_bytes": _safe_size(path),
            "archive_count": _archive_count(project, stream),
            "oldest_ts": _ts_of(_first_nonblank_line(path)),
            "newest_ts": _ts_of(_last_nonblank_line(path)),
        }
    return stats


def _discover_projects(root: str | Path) -> set[str]:
    """Enumerate project scopes under `root` from a directory scan only (no line
    parsing). A live `<stream>.jsonl` marks its parent dir as a project; a gzipped
    archive generation marks its `archive/` grandparent (`gz.parent.parent`) as a
    project. Classification is by FILENAME invariant, so nested scopes like
    `github.com/org/repo` enumerate correctly and a project literally named
    `archive` is never mistaken for the `archive/` folder. Empty/missing root ->
    empty set."""
    root = Path(root)
    projects: set[str] = set()
    if not root.is_dir():
        return projects
    root_str = str(root)
    for dirpath, _dirnames, filenames in os.walk(root):
        at_root = dirpath == root_str
        for fn in filenames:
            if _ARCHIVE_GZ_RE.match(fn):
                proj_dir = (Path(dirpath) / fn).parent.parent
            elif not at_root and _is_live_stream_file(fn):
                proj_dir = Path(dirpath)
            else:
                continue
            try:
                rel = proj_dir.relative_to(root)
            except ValueError:
                continue
            name = rel.as_posix()
            if name and name != ".":
                projects.add(name)
    return projects


def list_projects(project: str | None = None) -> list[dict]:
    """Inventory projects under the log root from a directory scan only. Each entry
    is `{project, streams:[{stream, bytes}], archive_count}`. `project` filters to
    a single scope; an empty/missing root -> `[]`."""
    discovered = _discover_projects(log_root())
    if project is not None:
        discovered = {p for p in discovered if p == project}
    result: list[dict] = []
    for proj in sorted(discovered):
        streams = []
        for stream in sorted(_KNOWN_STREAMS):
            path = stream_path(proj, stream)
            if path.is_file():
                streams.append({"stream": stream, "bytes": _safe_size(path)})
        result.append(
            {
                "project": proj,
                "streams": streams,
                "archive_count": _archive_count(proj),
            }
        )
    return result
