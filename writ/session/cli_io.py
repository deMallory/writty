"""Shared CLI-I/O helpers for the writ-session CLI (bin/lib/writ-session.py facade).

A dependency-free leaf module (stdlib only) so the dispatch layer (cli_dispatch) and the
domain modules it calls (approval_workflow, metrics) can all import these without a cycle.
"""

import json
import sys


def _usage_exit(msg: str) -> None:
    """Print a usage/error message to stderr and exit with status 2."""
    print(msg, file=sys.stderr)
    sys.exit(2)


def _emit_json(obj, **kwargs) -> None:
    """Serialize obj as JSON to stdout (kwargs pass through to json.dump, e.g. indent=2)."""
    json.dump(obj, sys.stdout, **kwargs)
