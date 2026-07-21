"""plan.md HARVEST parser for decision capture (Phase 1c, deliverable 2).

Reads an approved plan.md into the three pieces a Decision needs: the rationale
(## Analysis body), the planned files (## Files bullets), and the cited rules
(rule IDs in ## Rules Applied). Kept out of approval_workflow.py so the parser is
importable by the server route without pulling in the CLI advance path, and
unit-testable without a session cache.

Phase 3a: real-work projects write PROSE plans (### N. `path` - description) that
the gated Writ format regex never matched, so harvest yielded 0 Decisions for
them. _extract_files now recognizes both formats. A parsed path is admitted only
when it is in the commit's git-touched set (allowed_paths) -- a phantom-path guard
against a plan that mentions a file in prose but never actually changed it.
"""

import logging
import re

from writ.session.approval_workflow import (
    _FILES_BOLD_LINE_RE,
    _FILES_LINE_RE,
    _FILES_PATH_ONLY_RE,
)
from writ.session.gates import _section_body

logger = logging.getLogger(__name__)

# The rule-ID token shape (the exact pattern _validate_phase_a uses).
_RULE_ID_RE = re.compile(r'[A-Z][A-Z0-9]+(?:-[A-Z][A-Z0-9]+)*-\d{3}')

# PROSE plan formats (Phase 3a). Real-work plans head each file with a numbered
# sub-section or a plain bullet naming a backtick path then a single-hyphen
# description: "### 3. `writ/server.py` - add the route" or
# "- `writ/server.py` - add the route". The description is captured as the reason.
_PROSE_HEADING_RE = re.compile(r'^#{2,4}\s+\d+\.\s+`([^`]+)`\s*-\s*(.*)$')
_PROSE_BULLET_RE = re.compile(r'^-\s+`([^`]+)`\s+-\s+(\S.*)$')


def _strip_code_fences(plan_text: str) -> str:
    """Blank lines inside ``` fenced regions so a ## Files literal in a code block
    is never mis-targeted as a section heading by the splitter."""
    out = []
    in_fence = False
    for line in plan_text.splitlines():
        if line.lstrip().startswith("```"):
            in_fence = not in_fence
            out.append("")
            continue
        out.append("" if in_fence else line)
    return "\n".join(out)


def _extract_rationale(plan_text: str) -> str:
    """The ## Analysis body, stripped. Empty string when absent."""
    body = _section_body(plan_text, r'^##\s+Analysis')
    return body.strip() if body else ""


def _extract_files(plan_text: str, allowed_paths: set[str] | None = None) -> list[dict]:
    """Parse the planned files into entries each having path, change_type, reason.

    Two input shapes are recognized:
      1. The gated Writ ## Files bullets: "- `path` (change_type) -- reason" (and a
         reasonless "- `path`" variant, captured with empty change_type/reason).
      2. PROSE plans (real-work): a numbered sub-heading "### N. `path` - description"
         anywhere in the document, or a single-hyphen bullet "- `path` - description".

    The gated format is parsed from the ## Files section body; the prose format is
    scanned across the WHOLE document (real plans do not use a ## Files heading).

    Phantom-path guard: when allowed_paths is given (the commit's git-touched paths),
    a parsed path is dropped unless it is in that set. Paths a plan only mentions in
    prose but never actually changed are excluded, so a FileChange is never minted
    for a file that did not change in this commit. Dedupe preserves first-seen order.
    """
    files: list[dict] = []
    seen_paths: set[str] = set()

    def _admit(path: str, change_type: str, reason: str) -> None:
        if not path or path in seen_paths:
            return
        if allowed_paths is not None and path not in allowed_paths:
            return
        seen_paths.add(path)
        files.append({"path": path, "change_type": change_type, "reason": reason})

    # Shape 1: the gated ## Files section.
    body = _section_body(plan_text, r'^##\s+Files')
    if body:
        for line in body.splitlines():
            stripped = line.strip()
            full = _FILES_LINE_RE.match(stripped)
            if full:
                _admit(stripped.split("`")[1], full.group(1), full.group(2).strip())
                continue
            bold = _FILES_BOLD_LINE_RE.match(stripped)
            if bold:
                _admit(bold.group(2), bold.group(1), bold.group(3).strip())
                continue
            if _FILES_PATH_ONLY_RE.match(stripped):
                path = stripped.split("`")[1]
                logger.info("harvest_reasonless_file: %s", path)
                _admit(path, "", "")

    # Shape 2: PROSE headings/bullets across the whole document.
    for line in plan_text.splitlines():
        stripped = line.strip()
        heading = _PROSE_HEADING_RE.match(stripped)
        if heading:
            _admit(heading.group(1).strip(), "", heading.group(2).strip())
            continue
        bullet = _PROSE_BULLET_RE.match(stripped)
        if bullet:
            _admit(bullet.group(1).strip(), "", bullet.group(2).strip())

    return files


def _extract_cited_rules(plan_text: str) -> list[str]:
    """Rule-id tokens from the ## Rules Applied body only, deduped preserving order."""
    body = _section_body(plan_text, r'^##\s+Rules\s+[Aa]pplied')
    if not body:
        return []
    seen = []
    for rule_id in _RULE_ID_RE.findall(body):
        if rule_id not in seen:
            seen.append(rule_id)
    return seen


def harvest_plan(plan_text: str, allowed_paths: set[str] | None = None) -> dict:
    """Harvest an approved plan.md into {rationale, files, cited_rules}.

    allowed_paths (the commit's git-touched paths) constrains the parsed files to
    real changes (phantom-path guard); None keeps the legacy unfiltered behavior.
    """
    cleaned = _strip_code_fences(plan_text)
    return {
        "rationale": _extract_rationale(cleaned),
        "files": _extract_files(cleaned, allowed_paths=allowed_paths),
        "cited_rules": _extract_cited_rules(cleaned),
    }
