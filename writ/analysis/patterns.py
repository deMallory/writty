"""Violation pattern extraction and confidence-scored code scanning.

Extracts regex patterns from rule violation examples and scans code
against them. Each match is scored with a confidence tier:
  high: exact match, not in comment/string context
  medium: match in comment, string, or heredoc context
  low: partial match (substring of longer identifier)
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from writ.analysis import Finding

# Method names too generic to be meaningful violation patterns.
_SKIP_METHODS = frozenset({
    "get", "set", "create", "build", "run", "execute", "process",
    "save", "delete", "load", "find", "make", "init", "start", "stop",
})

# Single-line comment prefixes.
_COMMENT_PREFIXES = ("//", "#")


@dataclass(frozen=True)
class ViolationPattern:
    """A regex pattern extracted from a rule's violation example."""

    rule_id: str
    pattern: re.Pattern[str]
    label: str  # human-readable description of what the pattern matches


def extract_violations(rules: list[dict]) -> list[ViolationPattern]:
    """Extract searchable patterns from rule violation examples.

    Deterministic: same input always produces same output.
    Rules with empty violation fields produce zero patterns.
    """
    patterns: list[ViolationPattern] = []

    for rule in rules:
        violation = rule.get("violation", "")
        if not violation:
            continue
        rule_id = rule.get("rule_id", "UNKNOWN")

        # Method calls: ->foo( or ::foo(
        for m in re.finditer(r"(?:->|::)(\w+)\s*\(", violation):
            call = m.group(1)
            if call.lower() in _SKIP_METHODS:
                continue
            patterns.append(ViolationPattern(
                rule_id=rule_id,
                pattern=re.compile(rf"(?:->|::){re.escape(call)}\s*\("),
                label=f"->{call}(",
            ))

        # Instantiation: new ClassName(
        for m in re.finditer(r"\bnew\s+(\w+)\s*\(", violation):
            cls = m.group(1)
            patterns.append(ViolationPattern(
                rule_id=rule_id,
                pattern=re.compile(rf"\bnew\s+{re.escape(cls)}\s*\("),
                label=f"new {cls}(",
            ))

        # Factory->create()->load( chain
        if "Factory->create()->load" in violation or "Factory->create()->loadBy" in violation:
            patterns.append(ViolationPattern(
                rule_id=rule_id,
                pattern=re.compile(r"Factory->create\(\)->load"),
                label="Factory->create()->load",
            ))

        # Hardcoded secrets patterns
        for m in re.finditer(r"['\"]?(sk_live_|AKIA|password\s*=)", violation):
            patterns.append(ViolationPattern(
                rule_id=rule_id,
                pattern=re.compile(re.escape(m.group(1))),
                label=m.group(1),
            ))

    return patterns


def _is_in_comment(line: str, match_start: int) -> bool:
    """Check if a position in a line is inside a comment."""
    for prefix in _COMMENT_PREFIXES:
        idx = line.find(prefix)
        if idx != -1 and idx < match_start:
            return True
    return False


def _is_in_string(line: str, match_start: int) -> bool:
    """Check if a position is inside a string literal (balanced quotes)."""
    in_single = False
    in_double = False
    for i, ch in enumerate(line):
        if i >= match_start:
            break
        if ch == "'" and not in_double:
            in_single = not in_single
        elif ch == '"' and not in_single:
            in_double = not in_double
    return in_single or in_double


def _block_comment_lines(lines: list[str]) -> frozenset[int]:
    """Line indices inside a /* */ block comment, in ONE O(L) pass.

    C-1: scan_code previously re-walked every line per match via
    _is_in_block_comment -> O(patterns x lines x matches x L). Precomputing the
    set once makes the per-match check O(1). Membership matches the old per-line
    walk exactly: a line counts as in-block after its own '/*' is seen, up to and
    INCLUDING its own '*/' line.
    """
    inside: set[int] = set()
    in_block = False
    for i, line in enumerate(lines):
        if "/*" in line:
            in_block = True
        if in_block:
            inside.add(i)
        if "*/" in line:
            in_block = False
    return frozenset(inside)


def _assess_confidence(
    line: str,
    match_start: int,
    match_text: str,
    block_comment_lines: frozenset[int],
    line_idx: int,
) -> str:
    """Determine confidence tier for a pattern match."""
    # Check for substring match (pattern matches inside a longer identifier)
    # -> / :: are operators and 'new ' is a keyword boundary, so the char before
    # the match is fine there; only the default case rejects a substring match.
    # (E-EFFSTART: dropped the dead `effective_start` assignments.)
    if not (match_text.startswith("->") or match_text.startswith("::") or match_text.startswith("new ")):
        before = line[match_start - 1] if match_start > 0 else " "
        if before.isalnum() or before == "_":
            return "low"

    after_pos = match_start + len(match_text)
    after = line[after_pos] if after_pos < len(line) else " "
    if after.isalnum() or after == "_":
        return "low"

    # Check comment/string context
    if line_idx in block_comment_lines:
        return "medium"
    if _is_in_comment(line, match_start):
        return "medium"
    if _is_in_string(line, match_start):
        return "medium"

    return "high"


def scan_code(code: str, patterns: list[ViolationPattern]) -> list[Finding]:
    """Scan code against violation patterns, returning confidence-scored findings."""
    if not patterns or not code:
        return []

    lines = code.split("\n")
    block_comment_lines = _block_comment_lines(lines)  # C-1: one O(L) pass, not per-match
    findings: list[Finding] = []

    for vp in patterns:
        for line_idx, line in enumerate(lines):
            for m in vp.pattern.finditer(line):
                confidence = _assess_confidence(
                    line, m.start(), m.group(), block_comment_lines, line_idx,
                )
                findings.append(Finding(
                    rule_id=vp.rule_id,
                    source="pattern",
                    status="violated",
                    line=line_idx + 1,
                    confidence=confidence,
                    evidence=f"{vp.label} at line {line_idx + 1}: {line.strip()[:120]}",
                    suggestion="",
                ))

    return findings
