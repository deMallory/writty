#!/usr/bin/env python3
"""Migrate always-on Rules to carry applicability routing (WRIT-BLUEPRINT 3.5).

Inserts **Applicability_Scope** and **Trigger_Keywords** metadata lines into the RULE-START
blocks of the rules that should DEFER off the every-prompt channel. Rules absent from the map
keep no routing data and fail open to universal (inject at the per-turn point) -- so the
every-prompt comms/flow rules are intentionally left untouched.

Format matches writ.export.rule_to_markdown exactly (comma-space lists, placed after the
metadata block) so the source round-trips. Idempotent: a block already carrying
**Applicability_Scope** is skipped.

Usage:
  python3 scripts/migrate_always_on_applicability.py --dry-run   # report only
  python3 scripts/migrate_always_on_applicability.py             # apply
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

BIBLE = Path(__file__).resolve().parent.parent / "bible"

# rule_id -> (applicability_scope, trigger_keywords). Keywords are broad on purpose
# (fail-open: a missed match means a missed advisory injection, so over-match is safer).
CLASSIFICATION: dict[str, tuple[list[str], list[str]]] = {
    # content rules -> inject at the write moment when the code matches
    "ENF-CTX-003": (["write"], ["factory", "repository", "Model::load", "ORM", "service contract"]),
    "SCALE-STATELESS-001": (["write"], ["server", "handler", "worker", "session", "global", "stateless", "request"]),
    "ENF-POST-003": (["write"], ["interface", "implements", "abstract", "signature", "override"]),
    "ENF-SEC-001": (["write"], ["endpoint", "route", "controller", "resolver", "CLI", "command"]),
    "PERF-QUERY-001": (["write"], ["loop", "query", "foreach", "select_related", "prefetch", "eager", "N+1"]),
    "SEC-AUTH-HASH-001": (["write"], ["password", "hash", "bcrypt", "argon2", "scrypt", "credential"]),
    "SEC-AUTH-TOKEN-001": (["write"], ["token", "session", "csrf", "reset", "verification", "API key"]),
    "SEC-AUTHZ-DEFAULT-001": (["write"], ["endpoint", "route", "permission", "decorator", "policy"]),
    "SEC-AUTHZ-ENFORCE-001": (["write"], ["route", "resolver", "handler", "authorization", "auth", "middleware"]),
    "SEC-AUTHZ-IDOR-001": (["write"], ["find", "params", "current_user", "owner", "record"]),
    "SEC-AUTHZ-MASS-001": (["write"], ["request", "permit", "parameters", "mass assignment", "body"]),
    "SEC-CRYPTO-KEY-001": (["write"], ["secret", "API key", "password", "private key", "token", "credential"]),
    "SEC-CRYPTO-RAND-001": (["write"], ["random", "nonce", "salt", "key", "IV", "uuid", "token"]),
    "SEC-DATA-PII-001": (["write"], ["log", "email", "phone", "SSN", "address", "PII", "DOB"]),
    "SEC-INJ-CMD-001": (["write"], ["subprocess", "exec", "shell", "system", "popen"]),
    "SEC-INJ-CSRF-001": (["write"], ["POST", "PUT", "PATCH", "DELETE", "csrf", "form"]),
    "SEC-INJ-DESER-001": (["write"], ["pickle", "unserialize", "yaml", "marshal", "deserialize"]),
    "SEC-INJ-SQL-001": (["write"], ["sql", "query", "select", "insert", "update", "where", "execute"]),
    "SEC-INJ-SSRF-001": (["write"], ["url", "request", "webhook", "fetch", "http", "outbound"]),
    "SEC-INJ-XSS-001": (["write"], ["html", "render", "template", "jsx", "escape"]),
    "SEC-VAL-FILE-001": (["write"], ["upload", "file", "mime", "attachment", "avatar"]),
    "SEC-VAL-SERVER-001": (["write"], ["request", "validation", "input", "payload", "webhook"]),
    "ENF-POST-007": (["write"], ["phpstan", "static analysis", "lint", "analyze"]),
    "ENF-GATE-006": (["write"], ["handoff", ".claude/handoffs"]),
    "ENF-POST-006": (["write"], ["handoff", ".claude/handoffs"]),
    # NOTE: only the `write` injection point is used (plus the per-turn `prompt` point for
    # fail-open universals). `stop` is NOT an injection point: a Stop-hook additionalContext
    # is treated by CC as a turn-block (stop-hook-block-loop gotcha), so stop-discipline
    # rules (ENF-TEST-001, ENF-PROC-VERIFY-001) stay fail-open universal and gate-enforced.
    # The work-gated process rules (ENF-PROC-BRAIN/PLAN/TDD/VERIFY/WORKTREE) and the comms
    # rules (ENF-COMMS-*, FRB-COMMS-*) are likewise left universal: they are YAML methodology
    # nodes and/or hard-gated. Only RULE-START content rules whose enforcement IS the
    # injection are deferred to `write`.
}

RULE_START = re.compile(r"<!--\s*RULE START:\s*(\S+)\s*-->")
META_LINE = re.compile(r"^\*\*\w+\*\*:")
SECTION = re.compile(r"^###\s")


def migrate_block(lines: list[str], scope: list[str], kws: list[str]) -> list[str] | None:
    """Insert the two routing lines after the metadata block of one rule's lines.
    Returns new lines, or None if already migrated."""
    if any("**Applicability_Scope**" in ln for ln in lines):
        return None
    # last metadata line index before the first ### section
    last_meta = -1
    for i, ln in enumerate(lines):
        if SECTION.match(ln):
            break
        if META_LINE.match(ln):
            last_meta = i
    if last_meta < 0:
        return None
    insert = [f"**Applicability_Scope**: {', '.join(scope)}"]
    if kws:
        insert.append(f"**Trigger_Keywords**: {', '.join(kws)}")
    return lines[: last_meta + 1] + insert + lines[last_meta + 1 :]


def process_file(path: Path, dry: bool) -> list[str]:
    text = path.read_text(encoding="utf-8")
    starts = list(RULE_START.finditer(text))
    if not starts:
        return []
    changed: list[str] = []
    # work end-to-start so insertion offsets stay valid
    out = text
    edits: list[tuple[int, int, str]] = []  # (block_start, block_end, new_block)
    for m in starts:
        rid = m.group(1)
        if rid not in CLASSIFICATION:
            continue
        end = re.search(rf"<!--\s*RULE END:\s*{re.escape(rid)}\s*-->", text[m.end():])
        if not end:
            continue
        block_start = m.end()
        block_end = m.end() + end.start()
        block = text[block_start:block_end]
        scope, kws = CLASSIFICATION[rid]
        new_lines = migrate_block(block.split("\n"), scope, kws)
        if new_lines is None:
            continue
        edits.append((block_start, block_end, "\n".join(new_lines)))
        changed.append(rid)
    for block_start, block_end, new_block in sorted(edits, key=lambda e: -e[0]):
        out = out[:block_start] + new_block + out[block_end:]
    if changed and not dry:
        path.write_text(out, encoding="utf-8")
    return changed


def main() -> int:
    dry = "--dry-run" in sys.argv
    all_changed: list[str] = []
    for path in sorted(BIBLE.rglob("*.md")):
        all_changed += process_file(path, dry)
    missing = sorted(set(CLASSIFICATION) - set(all_changed))
    print(f"{'DRY-RUN: would migrate' if dry else 'migrated'} {len(all_changed)} rules")
    for rid in sorted(all_changed):
        print(f"  {rid}")
    if missing:
        print(f"NOT FOUND / already migrated ({len(missing)}): {missing}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
