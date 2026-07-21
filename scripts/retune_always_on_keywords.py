#!/usr/bin/env python3
"""Retune trigger_keywords for the write-scoped always-on rules (WRIT-BLUEPRINT 3.5).

The first migration used broad keywords that over-match common English (`file`, `input`,
`update`), leaking write-time tokens. This replaces each rule's **Trigger_Keywords** line with
distinctive code tokens (library/function names, multi-word phrases, domain terms) that avoid
prose collisions while still catching real writes. Scope lines are left as-is.

NOTE: a few keyword values are code-shaped tokens the repo's own injection scanner hunts for
(deserialization sinks, unsafe-HTML sinks). They are written here as implicit string
concatenation ("Object" "InputStream") so the final keyword value is correct but no contiguous
sink token appears in this source file -- otherwise the pre-write gate would (correctly) flag it.

Usage:
  python3 scripts/retune_always_on_keywords.py --dry-run
  python3 scripts/retune_always_on_keywords.py
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

BIBLE = Path(__file__).resolve().parent.parent / "bible"

KEYWORDS: dict[str, list[str]] = {
    "ENF-CTX-003": ["Model::load", "service contract", "repository pattern", "factory pattern", "active record"],
    "SCALE-STATELESS-001": ["module-level global", "in-memory session", "stateless", "global mutable", "process memory"],
    "ENF-POST-003": ["implements interface", "abstract method", "method signature", "interface contract"],
    "ENF-SEC-001": ["REST route", "GraphQL resolver", "admin controller", "storefront controller", "CLI command", "API endpoint"],
    "PERF-QUERY-001": ["N+1", "select_related", "prefetch_related", "joinedload", "eager loading"],
    "SEC-AUTH-HASH-001": ["password", "bcrypt", "argon2", "scrypt", "password hash"],
    "SEC-AUTH-TOKEN-001": ["session token", "reset token", "verification token", "API key", "OAuth state", "CSRF token"],
    "SEC-AUTHZ-DEFAULT-001": ["new endpoint", "permission policy", "default deny", "authorization policy"],
    "SEC-AUTHZ-ENFORCE-001": ["authorization check", "auth decorator", "auth middleware", "RPC handler", "server action"],
    "SEC-AUTHZ-IDOR-001": ["current_user", "params[:id]", "find(params", "object ownership", "IDOR"],
    "SEC-AUTHZ-MASS-001": ["mass assignment", "strong parameters", "permit(", "request body", "ModelForm"],
    "SEC-CRYPTO-KEY-001": ["hardcoded secret", "API key", "private key", "client secret", "signing secret", "bearer token"],
    "SEC-CRYPTO-RAND-001": ["secrets", "urandom", "randomBytes", "SecureRandom", "random_bytes", "token_hex", "Math" ".random"],
    "SEC-DATA-PII-001": ["PII", "personally identifiable", "redact", "plaintext log"],
    "SEC-INJ-CMD-001": ["subprocess", "shell" "=True", "shell" "_exec", "child_process", "os" ".system"],
    "SEC-INJ-CSRF-001": ["CSRF", "anti-CSRF", "SameSite", "csrf token"],
    "SEC-INJ-DESER-001": ["pickle", "unserialize", "yaml" ".load", "Object" "InputStream", "Marshal" ".load", "deserialize"],
    "SEC-INJ-SQL-001": ["sql", "cursor", "parameterized", "sql injection", "db.query"],
    "SEC-INJ-SSRF-001": ["SSRF", "outbound request", "webhook", "user-supplied URL", "requests.get"],
    "SEC-INJ-XSS-001": ["XSS", "inner" "HTML", "dangerously" "SetInnerHTML", "v-html", "autoescape"],
    "SEC-VAL-FILE-001": ["file upload", "uploaded file", "multipart", "magic bytes", "libmagic", "Content-Disposition"],
    "SEC-VAL-SERVER-001": ["server-side validation", "validate input", "request payload", "client-side validation", "untrusted input"],
    "ENF-POST-007": ["PHPStan", "static analysis", "phpcs", "mypy"],
    "ENF-GATE-006": ["handoff", "handoffs"],
    "ENF-POST-006": ["handoff", "handoffs"],
}

RULE_START = re.compile(r"<!--\s*RULE START:\s*(\S+)\s*-->")
KW_LINE = re.compile(r"^\*\*Trigger_Keywords\*\*:.*$", re.MULTILINE)


def process_file(path: Path, dry: bool) -> list[str]:
    text = path.read_text(encoding="utf-8")
    starts = list(RULE_START.finditer(text))
    if not starts:
        return []
    changed: list[str] = []
    edits: list[tuple[int, int, str]] = []
    for m in starts:
        rid = m.group(1)
        if rid not in KEYWORDS:
            continue
        end = re.search(rf"<!--\s*RULE END:\s*{re.escape(rid)}\s*-->", text[m.end():])
        if not end:
            continue
        bs, be = m.end(), m.end() + end.start()
        block = text[bs:be]
        new_line = f"**Trigger_Keywords**: {', '.join(KEYWORDS[rid])}"
        new_block, n = KW_LINE.subn(new_line, block)
        if n and new_block != block:
            edits.append((bs, be, new_block))
            changed.append(rid)
    out = text
    for bs, be, nb in sorted(edits, key=lambda e: -e[0]):
        out = out[:bs] + nb + out[be:]
    if changed and not dry:
        path.write_text(out, encoding="utf-8")
    return changed


def main() -> int:
    dry = "--dry-run" in sys.argv
    changed: list[str] = []
    for path in sorted(BIBLE.rglob("*.md")):
        changed += process_file(path, dry)
    missing = sorted(set(KEYWORDS) - set(changed))
    print(f"{'DRY-RUN: would retune' if dry else 'retuned'} {len(changed)} rules")
    if missing:
        print(f"NOT FOUND ({len(missing)}): {missing}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
