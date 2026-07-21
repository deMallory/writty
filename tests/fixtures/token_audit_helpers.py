"""Shared token-audit test helpers (Wave-5 Cycle 5.3c).

Consolidates the `_ta`/`_usage`/`_write_transcript` trio formerly duplicated in
`test_token_audit.py` and `test_token_audit_prevented.py`. The two files differ
only in their module-loading semantics: the prevented file force-reimports a
fresh module each call, while the base file returns the cached module. That
difference is preserved via the `force_reimport` flag on `load_token_audit`, so
each consumer keeps its current behavior.

SKILL_ROOT is resolved two parents up from `tests/fixtures/` (both source files
compute it one parent up from `tests/`).
"""

from __future__ import annotations

import importlib
import json
import os
import sys
from pathlib import Path

SKILL_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir, os.pardir))


def load_token_audit(force_reimport: bool = False):
    """Import writ.analysis.token_audit, optionally force-reimporting it.

    With ``force_reimport=False`` this returns the cached module (matching
    test_token_audit.py's `_ta`); with ``force_reimport=True`` it drops the
    cached module first so on-disk edits are picked up (matching
    test_token_audit_prevented.py's `_ta`).
    """
    if SKILL_ROOT not in sys.path:
        sys.path.insert(0, SKILL_ROOT)
    mod_name = "writ.analysis.token_audit"
    if force_reimport and mod_name in sys.modules:
        del sys.modules[mod_name]
    return importlib.import_module(mod_name)


def usage(inp=100, out=10, read=1000, write=200, c5=None, c1=None):
    """A well-formed CC assistant-turn usage dict.

    The superset builder: with ``c5``/``c1`` left as None the emitted dict is
    the 4-key form; supplying either adds the `cache_creation` sub-dict.
    """
    u = {
        "input_tokens": inp,
        "output_tokens": out,
        "cache_read_input_tokens": read,
        "cache_creation_input_tokens": write,
    }
    if c5 is not None or c1 is not None:
        u["cache_creation"] = {"ephemeral_5m_input_tokens": c5 or 0,
                               "ephemeral_1h_input_tokens": c1 or 0}
    return u


def write_transcript(path: Path, usages: list[dict], model="claude-opus-4-8") -> Path:
    """Write a minimal CC transcript jsonl: assistant turns carrying message.usage."""
    with open(path, "w") as f:
        for u in usages:
            f.write(json.dumps({"type": "assistant",
                                "message": {"model": model, "usage": u}}) + "\n")
    return path
