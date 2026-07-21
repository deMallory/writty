"""Wave-3 DRY dedup: writ-subagent-start.sh and writ-subagent-stop.sh each
inline the same `python3 -c "...json.load(sys.stdin).get(FIELD,'')..."` idiom
three times (agent_id, agent_type, session_id) instead of calling the
common.sh `parsed_field` helper (see bin/lib/common.sh ~line 142) that already
exists for exactly this purpose.

This file is RED today and GREEN once both hooks are edited to call
`parsed_field "$STDIN_JSON" "FIELD"` in place of the six inlined python3 calls:

- TestExtractionEquivalence is the behavior net. It proves parsed_field is a
  byte-identical drop-in for the HEAD idiom, at the shell level, without
  running the hooks (which have heavy side effects: session cache writes,
  curl calls, friction-log appends). It must PASS now and after.
- TestHooksUseParsedField is the source guard for the dedup itself. It FAILS
  today (hooks still inline python3) and must PASS once the hooks are edited.
- TestNoBehaviorDriftOnEarlyExit pins the downstream early-exit/branch
  contract so the mechanical edit can't silently drop it.
"""
from __future__ import annotations

import itertools
import os
import shlex
import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
COMMON_SH = REPO_ROOT / "bin" / "lib" / "common.sh"
START_HOOK = REPO_ROOT / "hooks" / "scripts" / "writ-subagent-start.sh"
STOP_HOOK = REPO_ROOT / "hooks" / "scripts" / "writ-subagent-stop.sh"

JQ_AVAILABLE = shutil.which("jq") is not None


def _run(script: str, payload: str, *, no_jq: bool = False) -> str:
    env = os.environ.copy()
    env["WRIT_TEST_JSON"] = payload
    if no_jq:
        env["WRIT_NO_JQ"] = "1"
    else:
        env.pop("WRIT_NO_JQ", None)
    result = subprocess.run(
        ["bash", "-c", script], capture_output=True, text=True, timeout=10, env=env
    )
    return result.stdout


def _old_extract(payload: str, field: str) -> str:
    """The exact HEAD inlined idiom, run verbatim via bash -c.

    Quote style for the python dict default (' vs ") is switched purely to
    make bash-embedding tractable via shlex.quote; the python is semantically
    identical to `json.load(sys.stdin).get('FIELD','')`.
    """
    py_code = f"import sys,json; print(json.load(sys.stdin).get('{field}',''))"
    script = (
        'printf "%s" "$('
        f"echo \"$WRIT_TEST_JSON\" | python3 -c {shlex.quote(py_code)} "
        '2>/dev/null || echo "")"'
    )
    return _run(script, payload)


def _new_extract(payload: str, field: str, *, no_jq: bool = False) -> str:
    """The dedup target: source common.sh, call parsed_field."""
    script = (
        f"source {shlex.quote(str(COMMON_SH))}; "
        f'printf "%s" "$(parsed_field \"$WRIT_TEST_JSON\" {shlex.quote(field)})"'
    )
    return _run(script, payload, no_jq=no_jq)


FIELDS = ["agent_id", "agent_type", "session_id"]

PAYLOADS = {
    "normal": '{"agent_id":"agt-123","agent_type":"writ-explorer","session_id":"sess-abc"}',
    "missing_field": '{"other":"value"}',
    "malformed": "not json{",
    "empty_object": "{}",
}

EQUIVALENCE_CASES = [
    (field, payload_name, payload)
    for field, (payload_name, payload) in itertools.product(FIELDS, PAYLOADS.items())
]
EQUIVALENCE_IDS = [f"{field}-{name}" for field, name, _ in EQUIVALENCE_CASES]


class TestExtractionEquivalence:
    """parsed_field must be a byte-identical drop-in for the HEAD inlined
    python3 idiom, for scalar field extraction (agent_id, agent_type,
    session_id) as used by writ-subagent-start.sh and writ-subagent-stop.sh.

    NOTE: only present STRING values (and the missing-key case) are covered
    here. Pure-python `.get(k, '')` substitutes the default only for a MISSING
    key; for any present NON-string value it prints python's str()/repr, which
    diverges from parsed_field's jq `-r` rendering:
      - JSON null   -> python prints 'None';  parsed_field yields '' (default)
      - boolean     -> python prints 'True'/'False'; jq prints 'true'/'false'
      - array/object-> python prints the list/dict repr; jq prints JSON
      (numbers agree: both print the bare number.)
    These are real, documented divergences between the two mechanisms -- but
    Claude Code always sends agent_id/agent_type/session_id as plain strings
    (verified against 300+ captured SubagentStart/Stop envelopes), never as
    null/bool/array/object, so they are out of scope for the drop-in
    equivalence claim and are deliberately not asserted on here.
    """

    @pytest.mark.parametrize("field,payload_name,payload", EQUIVALENCE_CASES, ids=EQUIVALENCE_IDS)
    def test_python_fallback_matches_old_idiom(self, field, payload_name, payload):
        old = _old_extract(payload, field)
        new = _new_extract(payload, field, no_jq=True)
        assert old == new

    @pytest.mark.parametrize("field,payload_name,payload", EQUIVALENCE_CASES, ids=EQUIVALENCE_IDS)
    def test_jq_path_matches_old_idiom(self, field, payload_name, payload):
        if not JQ_AVAILABLE:
            pytest.skip("jq not installed; only the WRIT_NO_JQ fallback path is testable here")
        old = _old_extract(payload, field)
        new = _new_extract(payload, field, no_jq=False)
        assert old == new


class TestHooksUseParsedField:
    """Source guard for the dedup: both subagent hooks must call the common.sh
    `parsed_field` helper for agent_id/agent_type/session_id instead of
    inlining the python3 idiom.

    RED now: the hooks still inline `python3 -c "...json.load(sys.stdin)..."`
    six times combined (3 fields x 2 hooks).
    GREEN once both hooks are edited to call parsed_field.
    """

    HOOKS = {"start": START_HOOK, "stop": STOP_HOOK}

    @pytest.fixture(params=["start", "stop"])
    def hook_source(self, request) -> str:
        return self.HOOKS[request.param].read_text()

    @pytest.mark.parametrize("field", FIELDS)
    def test_uses_parsed_field_helper(self, hook_source, field):
        assert f'parsed_field "$STDIN_JSON" "{field}"' in hook_source

    @pytest.mark.parametrize("field", FIELDS)
    def test_no_longer_inlines_python_idiom(self, hook_source, field):
        assert f"json.load(sys.stdin).get('{field}'" not in hook_source


class TestNoBehaviorDriftOnEarlyExit:
    """Guards the downstream contract so the mechanical dedup can't silently
    drop the emptiness / parent-session branches these hooks rely on
    downstream of the (soon-to-be-refactored) extraction block."""

    def test_start_hook_keeps_agent_id_early_exit(self):
        assert '[ -z "$AGENT_ID" ]' in START_HOOK.read_text()

    def test_stop_hook_keeps_agent_id_early_exit(self):
        assert '[ -z "$AGENT_ID" ]' in STOP_HOOK.read_text()

    def test_start_hook_keeps_parent_session_branch(self):
        assert '[ -n "$PARENT_SESSION" ]' in START_HOOK.read_text()
