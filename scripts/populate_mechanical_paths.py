"""Populate mechanical_enforcement_path on existing mandatory rules.

Phase 1 added the mechanical_enforcement_path field to the Rule model with a
None default. Existing rules in Neo4j predate the field and have it unset.
This script applies the path citations from docs/mandatory-rule-audit.md
to every 'has path' rule so the Phase 2 blocker 'zero mandatory without
mechanical path' is met.

Run AFTER scripts/demote_mandatory_rules.py, which strips the 12 no-viable-
path rules. Remaining 21 has-path + 2 could-have-path rules get their path
populated here.

Usage: .venv/bin/python scripts/populate_mechanical_paths.py [--dry-run]
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from writ.graph.db import Neo4jConnection

NEO4J_URI = "bolt://localhost:7687"
NEO4J_USER = "neo4j"
NEO4J_PASSWORD = "writdevpass"

# Citations from docs/mandatory-rule-audit.md. Each entry is the shortest
# useful reference the auditor verified.
PATHS: dict[str, str] = {
    # Only rules whose mechanical enforcement path is not already declared in
    # bible/methodology. These map mandatory ENF-* rules to their real
    # enforcement entry points in the v2 system.
    "ENF-CTX-003":     "bin/run-analysis.sh (PHPCS lint)",
    "ENF-GATE-007":    "bin/lib/writ-session.py:1125-1370 (can_write test-skeleton gate)",
    "ENF-POST-003":    "bin/run-analysis.sh (PHPStan level 8)",
    "ENF-POST-007":    "bin/run-analysis.sh (PHPStan level 8)",
    "ENF-SEC-001":     "bin/run-analysis.sh:78 (PHPStan ownership check)",
    # Removed in the 2026-05-10 cleanup (rules deleted as tied to the dead
    # Phase A-D / completion-matrix workflow):
    #   ENF-GATE-001..006, ENF-GATE-FINAL, ENF-POST-001/002/006/008,
    #   ENF-CTX-001/002/004, ENF-SYS-001/004, ENF-ROUTE-001
    # Demoted to advisory in the same cleanup (no real mechanical path):
    #   ENF-PRE-001..004, ENF-POST-004/005, ENF-SYS-002/003/005/006,
    #   ENF-OPS-001/002, ENF-SEC-002
}


async def main(dry_run: bool) -> int:
    db = Neo4jConnection(NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD)
    try:
        populated = 0
        skipped = 0
        for rid, path in PATHS.items():
            async with db._driver.session(database=db._database) as session:
                check = await session.run(
                    "MATCH (r:Rule {rule_id: $rid}) RETURN r.mandatory AS m, r.mechanical_enforcement_path AS p",
                    rid=rid,
                )
                rec = await check.single()
                if rec is None:
                    skipped += 1
                    print(f"  skip (not in graph): {rid}")
                    continue
                existing = rec["p"]
                if existing and existing.strip():
                    skipped += 1
                    print(f"  skip (already set): {rid} = {existing[:60]}")
                    continue
                if dry_run:
                    print(f"  [DRY RUN] would populate: {rid} = {path}")
                else:
                    await session.run(
                        "MATCH (r:Rule {rule_id: $rid}) SET r.mechanical_enforcement_path = $p",
                        rid=rid, p=path,
                    )
                    print(f"  populated: {rid}")
                populated += 1
        print()
        print(f"Populated: {populated}  Skipped: {skipped}")

        if not dry_run:
            async with db._driver.session(database=db._database) as session:
                q = """
                    MATCH (r:Rule)
                    WHERE r.mandatory = true
                    AND (r.mechanical_enforcement_path IS NULL
                         OR r.mechanical_enforcement_path = '')
                    RETURN r.rule_id AS rule_id ORDER BY rule_id
                """
                result = await session.run(q)
                violations = [rec["rule_id"] async for rec in result]
                print()
                if violations:
                    print(f"BLOCKER NOT MET: {len(violations)} mandatory rules still lack mechanical_enforcement_path:")
                    for v in violations:
                        print(f"  - {v}")
                    return 1
                print("Phase 2 release-blocker 'zero mandatory without mechanical': MET.")
    finally:
        await db.close()
    return 0


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args()
    raise SystemExit(asyncio.run(main(args.dry_run)))
