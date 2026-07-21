"""Budget/cost constants for the session helper, loaded from the canonical JSON.

POL-6a extracts this foundational block out of bin/lib/writ-session.py. The facade
re-exports these names, so inline functions and external `mod.<name>` access still
resolve. stdlib only.
"""

import json
import os

# Per DRY-CONFIG-001: budget constants load from the canonical JSON shared with
# writ/retrieval/session.py. Single source of truth. stdlib only. The __file__-relative
# 3-dirname walk resolves to the skill root from writ/session/config.py exactly as it did
# from bin/lib/writ-session.py (both are three levels below the skill root).
_BUDGET_JSON = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "writ", "shared", "budget.json",
)
with open(_BUDGET_JSON) as _budget_file:
    _budget_data = json.load(_budget_file)
DEFAULT_SESSION_BUDGET = _budget_data["default_budget"]
APPROX_TOKENS_PER_RULE_FULL = _budget_data["rule_cost_full"]
APPROX_TOKENS_PER_RULE_STANDARD = _budget_data["rule_cost_standard"]
APPROX_TOKENS_PER_RULE_SUMMARY = _budget_data["rule_cost_summary"]
DEFAULT_ALWAYS_ON_CAP = _budget_data.get("always_on_cap", 5000)

# INV-2: bounds for the unified citation_log (the 7a command_log is a command-type
# partition of it). Values carried over from 7a (10 / 500). Shared by writ/session/cache.py
# (_migrate_command_log) and writ/session/citations.py (_append_citation).
_CITATION_LOG_MAX = 10
_CITATION_EXCERPT_MAX = 500

# INV-3/INV-5: file-extension -> domain/language map. Shared static reference data used
# by investigations.cmd_coverage (domain coverage) and feedback.cmd_auto_feedback. Lives
# here in the lowest layer so neither cluster depends on the other.
EXT_TO_DOMAIN = {
    ".py": "python", ".php": "php",
    ".js": "javascript", ".jsx": "javascript",
    ".ts": "typescript", ".tsx": "typescript",
    ".go": "go", ".rs": "rust", ".java": "java", ".rb": "ruby",
    ".sql": "database", ".xml": "xml", ".graphqls": "graphql",
}

# INV-3/INV-5: rule-ID-prefix -> domain map and the always-relevant domains. The
# prefix analogue of EXT_TO_DOMAIN; shared by investigations.cmd_coverage and
# feedback.cmd_auto_feedback so the prefix vocabulary has one source (a new prefix
# is added once here, not in both clusters).
PREFIX_TO_DOMAIN = {
    "PY": "python", "PHP": "php", "JS": "javascript", "TS": "typescript",
    "GO": "go", "RS": "rust", "JAVA": "java", "RB": "ruby",
    "DB": "database", "SQL": "database",
    "ARCH": "architecture", "PERF": "performance", "TEST": "testing",
    "SEC": "security", "ENF": "enforcement", "OPS": "operations",
    "FW": "framework",
}
UNIVERSAL_DOMAINS = {"architecture", "performance", "testing", "security", "enforcement"}
