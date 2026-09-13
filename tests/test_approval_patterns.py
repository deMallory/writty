"""Tests for the approval detection module (bin/lib/approval_match.py).

Imports is_approval directly from the module (single source of truth).
The hook (auto-approve-gate.sh) delegates to the same module, so these
tests exercise the exact logic that runs in production.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "bin", "lib"))

from approval_match import is_approval  # noqa: E402  # RED until module exists


def _check_approval(prompt: str) -> bool:
    """Thin wrapper so existing call-sites keep working unchanged."""
    prompt_lower = prompt.lower().strip()
    return is_approval(prompt_lower)


# -- Exact matches (existing behavior) ---------------------------------------

class TestExactMatches:
    def test_approved_returns_true(self):
        assert _check_approval("approved")

    def test_approve_returns_true(self):
        assert _check_approval("approve")

    def test_lgtm_returns_true(self):
        assert _check_approval("lgtm")

    def test_proceed_returns_true(self):
        assert _check_approval("proceed")

    def test_go_ahead_returns_true(self):
        assert _check_approval("go ahead")

    def test_yes_returns_true(self):
        assert _check_approval("yes")

    def test_continue_returns_true(self):
        assert _check_approval("continue")

    def test_trailing_exclamation_approved_returns_true(self):
        assert _check_approval("approved!")

    def test_trailing_period_approved_returns_true(self):
        assert _check_approval("approved.")


# -- Prefix-tolerant patterns (existing behavior) ----------------------------

class TestPrefixPatterns:
    def test_ok_proceed_with_remaining_work_returns_true(self):
        """Friction log line 5: this exact phrase was missed."""
        assert _check_approval("ok proceed with remaining work")

    def test_sure_go_ahead_returns_true(self):
        assert _check_approval("sure, go ahead")

    def test_yeah_approved_continue_returns_true(self):
        assert _check_approval("yeah approved, continue with implementation")

    def test_okay_proceed_returns_true(self):
        assert _check_approval("okay proceed")

    def test_sure_approved_returns_true(self):
        assert _check_approval("sure, approved")

    def test_ok_continue_returns_true(self):
        assert _check_approval("ok continue")

    def test_yeah_go_ahead_returns_true(self):
        assert _check_approval("yeah go ahead")

    def test_yes_proceed_with_that_returns_true(self):
        assert _check_approval("yes proceed with that")

    def test_ok_looks_good_returns_true(self):
        assert _check_approval("ok looks good")


# -- New conjunction/comma pattern: accept tests (RED until pattern added) ---

class TestConjunctionPattern:
    def test_approved_and_push_returns_true(self):
        """Approval word + 'and' + short instruction -> accepted."""
        assert _check_approval("approved and push")

    def test_approved_comma_ship_it_returns_true(self):
        """Approval word + comma + short instruction -> accepted."""
        assert _check_approval("approved, ship it")

    def test_approved_then_commit_returns_true(self):
        """Approval word + 'then' + short instruction -> accepted."""
        assert _check_approval("approved then commit")

    def test_approve_and_merge_returns_true(self):
        """Approval word + 'and' + short instruction -> accepted."""
        assert _check_approval("approve and merge")


# -- Non-approval: must NOT match (existing + new governance guards) ----------

class TestNonApproval:
    def test_question_about_approval_returns_false(self):
        assert not _check_approval("how do I get this approved?")

    def test_code_with_approval_word_returns_false(self):
        assert not _check_approval("the proceed function needs to handle errors")

    def test_discussing_continue_returns_false(self):
        assert not _check_approval("add a continue statement in the loop")

    def test_empty_string_returns_false(self):
        assert not _check_approval("")

    def test_unrelated_prompt_returns_false(self):
        assert not _check_approval("refactor the database module")

    def test_question_with_ok_returns_false(self):
        assert not _check_approval("is it ok to delete the old migration files?")

    def test_go_in_sentence_returns_false(self):
        assert not _check_approval("where does this function go in the architecture?")

    def test_approve_the_design_before_merging_returns_false(self):
        """No conjunction/comma immediately after the approval word -> rejected."""
        assert not _check_approval("approve the design before merging")

    def test_approved_changes_need_review_returns_false(self):
        """No conjunction/comma immediately after the approval word -> rejected."""
        assert not _check_approval("approved changes need review")

    def test_is_this_approved_question_returns_false(self):
        """Fails ^ anchor (starts with 'is') and contains '?' -> rejected."""
        assert not _check_approval("is this approved?")

    def test_not_approved_returns_false(self):
        """Fails ^ anchor (starts with 'not') -> rejected."""
        assert not _check_approval("not approved")

    def test_how_do_i_get_this_approved_returns_false(self):
        """Fails ^ anchor (starts with 'how') -> rejected."""
        assert not _check_approval("how do I get this approved?")


# -- Hook/module agreement test ----------------------------------------------

class TestHookModuleAgreement:
    def test_hook_references_approval_match_module(self):
        """auto-approve-gate.sh must reference approval_match so hook and module
        are provably the same source of truth (no inline-regex regression)."""
        hook_path = os.path.join(
            os.path.dirname(__file__), "..", "hooks", "scripts", "auto-approve-gate.sh"
        )
        with open(hook_path) as f:
            content = f.read()
        assert "approval_match" in content, (
            "auto-approve-gate.sh does not reference approval_match; "
            "the hook may still be using the old inline detector instead of the module."
        )


# -- Position-free matching (2026-09-13) ------------------------------------
#
# The anchored patterns missed real approvals with a preamble ("Sounds lovely,
# approved !", "You have my explicit go ahead"), so no token was minted and the user
# had to retype a bare "approved". An approval word anywhere in a short prompt now
# counts, guarded against negation and questions.

class TestPositionFree:
    def test_preamble_then_approved_is_approval(self):
        assert _check_approval("Sounds lovely, approved !")

    def test_explicit_go_ahead_is_approval(self):
        assert _check_approval("You have my explicit go ahead")

    def test_plan_is_fine_approved_is_approval(self):
        assert _check_approval("the plan is fine, approved")

    def test_great_proceed_is_approval(self):
        assert _check_approval("great, proceed with it")

    def test_negated_is_not_approval(self):
        assert not _check_approval("not approved")
        assert not _check_approval("this is not approved yet")
        assert not _check_approval("don't proceed")
        assert not _check_approval("do not proceed yet")

    def test_question_is_not_approval(self):
        assert not _check_approval("is this approved?")
        assert not _check_approval("should I approve this?")

    def test_long_prompt_is_not_approval(self):
        long = ("i approved the budget last year for the whole team, now can you "
                "explain how the hook decides which plan file it validates and why")
        assert len(long) >= 120
        assert not _check_approval(long)
