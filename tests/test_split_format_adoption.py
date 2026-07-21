"""Wave-3 Cycle D: adopt writ.retrieval.prompt_bundle.split_format() in
session_state.py's `_format` inline block and gate.py's pre-write-rag inline
block, retiring the two duplicated WRIT_META-split list-comprehensions.

HERMETIC: pure functions over strings only. No server process, no Neo4j.

Structure:
  1. TestSessionStateFormatEquivalence -- differential: frozen HEAD reference
     vs split_format-based replacement. GREEN now and after (byte-identical
     for every input, including the malformed-JSON case: HEAD also swallows
     and defaults there).
  2. TestGateEquivalence -- differential: frozen HEAD reference (which has NO
     local try/except and so can raise) vs split_format-based replacement.
     Characterizes the two inert deltas: (a) rag_rules gains a .strip() (b)
     malformed WRIT_META no longer raises, it defaults.
  3. TestRoutesAdoptSplitFormat -- source guard. RED now (both routes are
     still inline); flips GREEN once the impl imports and calls split_format
     and deletes the inline list-comp.

Run: .venv/bin/python -m pytest tests/test_split_format_adoption.py -q
"""
from __future__ import annotations

import json as json_mod
import os

import pytest

from writ.retrieval.prompt_bundle import split_format

SKILL_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
SESSION_STATE_PATH = os.path.join(SKILL_ROOT, "writ", "server", "routes", "session_state.py")
GATE_PATH = os.path.join(SKILL_ROOT, "writ", "server", "routes", "gate.py")

# The exact HEAD substring both inline blocks build the "text" side with.
# Cycle D's impl must delete this from both files.
INLINE_SPLIT_SNIPPET = '[ln for ln in lines if not ln.startswith("WRIT_META:")]'

# Battery of raw inputs shared by both equivalence suites where applicable.
WELL_FORMED = 'l1\nl2\nWRIT_META:{"rule_ids":["A","B"],"cost":17}'
NO_META = "l1\nl2"
MALFORMED_META = "t\nWRIT_META:{not json"
BLANK_PADDED = '\n\nRULE\n\nWRIT_META:{"rule_ids":[],"cost":0}\n'
EMPTY_STRING = ""
NONE_INPUT = None


# --------------------------------------------------------------------------- #
# 1. session_state._format equivalence (frozen HEAD vs split_format-based)
# --------------------------------------------------------------------------- #
def _head_session_state(raw):
    """Frozen reproduction of the HEAD inline block in
    writ/server/routes/session_state.py:175-190 (the `_format` closure body).
    Do not "fix" or simplify this -- it is a byte-for-byte pin of HEAD."""
    raw = raw or ""
    lines = raw.splitlines()
    text_lines = [ln for ln in lines if not ln.startswith("WRIT_META:")]
    meta_lines = [ln for ln in lines if ln.startswith("WRIT_META:")]
    text = "\n".join(text_lines).strip()
    meta = {"rule_ids": [], "tokens": 0}
    if meta_lines:
        try:
            parsed = json_mod.loads(meta_lines[0][len("WRIT_META:"):])
            meta = {"rule_ids": parsed.get("rule_ids", []), "tokens": parsed.get("cost", 0)}
        except (ValueError, json_mod.JSONDecodeError):
            pass
    return {"text": text, "meta": meta}


def _new_session_state(raw):
    """The Cycle-D replacement: session_state._format rewritten to delegate
    to split_format(). Mirrors the planned post-impl body exactly."""
    raw = raw or ""
    text, _m = split_format(raw)
    return {"text": text, "meta": {"rule_ids": _m["rule_ids"], "tokens": _m["cost"]}}


class TestSessionStateFormatEquivalence:
    """Differential: for every input in the battery, the split_format-based
    replacement must be byte-identical to the frozen HEAD block. This is the
    behavior contract Cycle D's real edit to session_state.py must preserve;
    it is GREEN both before and after the edit lands."""

    @pytest.mark.parametrize(
        "raw",
        [
            WELL_FORMED,
            NO_META,
            MALFORMED_META,
            BLANK_PADDED,
            EMPTY_STRING,
            NONE_INPUT,
        ],
        ids=["well_formed", "no_meta", "malformed_meta", "blank_padded", "empty_string", "none_input"],
    )
    def test_new_matches_head_for_all_inputs(self, raw):
        assert _new_session_state(raw) == _head_session_state(raw)

    def test_well_formed_extracts_expected_shape(self):
        result = _new_session_state(WELL_FORMED)
        assert result == {"text": "l1\nl2", "meta": {"rule_ids": ["A", "B"], "tokens": 17}}

    def test_malformed_meta_defaults_without_raising(self):
        # HEAD swallows (ValueError, JSONDecodeError) internally in the
        # `_format` closure, so this must not raise either before or after
        # the Cycle-D edit.
        result = _new_session_state(MALFORMED_META)
        assert result == {"text": "t", "meta": {"rule_ids": [], "tokens": 0}}

    def test_none_input_treated_as_empty(self):
        assert _new_session_state(None) == {"text": "", "meta": {"rule_ids": [], "tokens": 0}}


# --------------------------------------------------------------------------- #
# 2. gate.py pre-write-rag block equivalence (characterizes 2 inert deltas)
# --------------------------------------------------------------------------- #
def _head_gate(formatted):
    """Frozen reproduction of the HEAD inline block in
    writ/server/routes/gate.py:379-388. Unlike session_state's `_format`,
    this block has NO local try/except around json_mod.loads -- a malformed
    WRIT_META: line raises and is caught only by the outer `except Exception`
    in the surrounding pre-write-rag handler (fail-open + friction log)."""
    lines = formatted.splitlines()
    text_lines = [ln for ln in lines if not ln.startswith("WRIT_META:")]
    meta_lines = [ln for ln in lines if ln.startswith("WRIT_META:")]
    rag_rules = "\n".join(text_lines)  # NB: no .strip() at HEAD
    rag_meta = {"rule_ids": [], "tokens": 0}
    if meta_lines:
        meta_json = json_mod.loads(meta_lines[0][len("WRIT_META:"):])  # may raise
        rag_meta = {"rule_ids": meta_json.get("rule_ids", []), "tokens": meta_json.get("cost", 0)}
    return {"rag_rules": rag_rules, "rag_meta": rag_meta}


def _new_gate(formatted):
    """The Cycle-D replacement: gate.py's pre-write-rag block rewritten to
    delegate to split_format()."""
    rag_rules, _m = split_format(formatted)
    return {"rag_rules": rag_rules, "rag_meta": {"rule_ids": _m["rule_ids"], "tokens": _m["cost"]}}


class TestGateEquivalence:
    """Differential against the frozen HEAD gate block. split_format()
    introduces two behavior deltas relative to HEAD, both judged inert for
    gate.py's actual call site:
      (a) rag_rules gains a trailing/leading .strip() -- the caller only uses
          rag_rules to compose an already-stripped prompt block, so the whitespace
          difference is not observable downstream.
      (b) malformed WRIT_META no longer raises out of the inline block; it
          defaults to {"rule_ids": [], "tokens": 0} instead of propagating to
          the outer `except Exception` fail-open handler. Net externally-visible
          effect is the same (both paths end up not injecting meaningful rag
          meta), so this delta is also inert.
    """

    @pytest.mark.parametrize(
        "formatted",
        [WELL_FORMED, NO_META, BLANK_PADDED],
        ids=["well_formed", "no_meta", "blank_padded"],
    )
    def test_rag_meta_byte_identical_for_non_raising_inputs(self, formatted):
        assert _new_gate(formatted)["rag_meta"] == _head_gate(formatted)["rag_meta"]

    @pytest.mark.parametrize(
        "formatted",
        [WELL_FORMED, NO_META, BLANK_PADDED],
        ids=["well_formed", "no_meta", "blank_padded"],
    )
    def test_rag_rules_only_delta_is_strip(self, formatted):
        new_rules = _new_gate(formatted)["rag_rules"]
        head_rules = _head_gate(formatted)["rag_rules"]
        assert new_rules == head_rules.strip()

    def test_blank_padded_actually_exercises_a_nontrivial_strip(self):
        # Sanity check that BLANK_PADDED isn't a no-op fixture: HEAD's
        # unstripped rag_rules must differ from the new stripped value, and
        # the new value must equal head.strip().
        new_result = _new_gate(BLANK_PADDED)
        head_result = _head_gate(BLANK_PADDED)
        assert new_result["rag_rules"] != head_result["rag_rules"]
        assert new_result["rag_rules"] == head_result["rag_rules"].strip()

    def test_head_raises_on_malformed_meta(self):
        with pytest.raises((ValueError, json_mod.JSONDecodeError)):
            _head_gate(MALFORMED_META)

    def test_new_swallows_malformed_meta_and_defaults(self):
        # This is the unreachable-in-practice delta: split_format() swallows
        # (ValueError, JSONDecodeError) internally, so the new inline block
        # never raises here, unlike HEAD's bare json_mod.loads() call.
        result = _new_gate(MALFORMED_META)
        assert result["rag_meta"] == {"rule_ids": [], "tokens": 0}
        assert result["rag_rules"] == "t"


# --------------------------------------------------------------------------- #
# 3. source guard: routes must actually adopt split_format (RED until impl)
# --------------------------------------------------------------------------- #
class TestRoutesAdoptSplitFormat:
    """Static source-guard over the two route files. RED today (both files
    still carry the inline WRIT_META-split list-comprehension and neither
    imports split_format); flips GREEN once Cycle D's implementation lands."""

    def _read(self, path):
        with open(path, encoding="utf-8") as f:
            return f.read()

    def test_session_state_imports_split_format(self):
        src = self._read(SESSION_STATE_PATH)
        assert "from writ.retrieval.prompt_bundle import split_format" in src

    def test_session_state_calls_split_format(self):
        src = self._read(SESSION_STATE_PATH)
        assert "split_format(" in src

    def test_session_state_no_longer_has_inline_split(self):
        src = self._read(SESSION_STATE_PATH)
        assert INLINE_SPLIT_SNIPPET not in src

    def test_gate_imports_split_format(self):
        src = self._read(GATE_PATH)
        assert "from writ.retrieval.prompt_bundle import split_format" in src

    def test_gate_calls_split_format(self):
        src = self._read(GATE_PATH)
        assert "split_format(" in src

    def test_gate_no_longer_has_inline_split(self):
        src = self._read(GATE_PATH)
        assert INLINE_SPLIT_SNIPPET not in src
