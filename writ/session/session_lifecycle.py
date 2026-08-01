"""Session-cache lifecycle and introspection commands.

POL-6g-3 extracts the cache dump (cmd_read) and the compaction-boundary commands
(cmd_clear_rules_for_compaction for PreCompact, cmd_reset_after_compaction for PostCompact)
out of bin/lib/writ-session.py. Imports only lower layers (cache, friction, config) + stdlib;
acyclic. The facade re-exports these; server.py's compaction routes resolve unchanged.
"""

import json
import sys

from writ.session.cache import _read_cache, mutate_cache
from writ.session.friction import _log_friction_event
from writ.session.config import DEFAULT_SESSION_BUDGET, APPROX_TOKENS_PER_RULE_FULL


def cmd_read(session_id: str) -> None:
    cache = _read_cache(session_id)
    json.dump(cache, sys.stdout)
    sys.stdout.write("\n")


def cmd_clear_rules_for_compaction(session_id: str) -> None:
    """Drop the now-stale loaded_rules full objects at the compaction boundary,
    keeping the IDs (for exclusion/coverage). For the PreCompact hook.

    NOTE: the session cache is a separate /tmp file, NOT part of the compacted
    conversation context, so this does not reduce what the summarizer compresses.
    It is boundary hygiene: the conversation those full objects annotated is being
    summarized away. bytes_freed is cache-file bytes, not context tokens.
    """
    with mutate_cache(session_id) as cache:
        rules = cache.get("loaded_rules", [])
        rules_cleared = len(rules)
        bytes_freed = rules_cleared * APPROX_TOKENS_PER_RULE_FULL  # cache-file bytes, not context tokens
        cache["loaded_rules"] = []
    _log_friction_event(
        session_id, cache.get("mode"), "pre_compaction",
        rules_cleared=rules_cleared, bytes_freed=bytes_freed,
    )
    result = {"rules_cleared": rules_cleared, "bytes_freed": bytes_freed}
    json.dump(result, sys.stdout)
    sys.stdout.write("\n")


def cmd_detect_compaction(session_id: str, current_context_percent: int) -> dict:
    """Detect context window compaction via context_percent drop.

    Compares the previous context_percent snapshot in the session cache with the
    current value. A drop of >20% triggers recovery: clearing the current phase's
    exclusion list and resetting remaining_budget to DEFAULT_SESSION_BUDGET.

    Returns a dict with {compacted, context_drop_percent, rules_cleared}.
    """
    cache = _read_cache(session_id)
    previous_pct = cache.get("context_percent", 0)
    drop = previous_pct - current_context_percent

    if drop > 20:
        with mutate_cache(session_id) as cache:
            current_phase = cache.get("current_phase", "unknown")
            by_phase = cache.get("loaded_rule_ids_by_phase", {})
            rules_cleared = list(by_phase.get(current_phase, []))
            # Clear exclusion list for current phase only
            by_phase[current_phase] = []
            cache["loaded_rule_ids_by_phase"] = by_phase
            cache["remaining_budget"] = DEFAULT_SESSION_BUDGET
            # Clear sticky rules preference (stale after compaction)
            cache["last_injected_rule_ids"] = []
        _log_friction_event(
            session_id, cache.get("mode"), "compaction_detected",
            context_drop_percent=drop,
            previous_context_percent=previous_pct,
            current_context_percent=current_context_percent,
            rules_cleared=rules_cleared,
            phase=current_phase,
        )
        result = {
            "compacted": True,
            "context_drop_percent": drop,
            "rules_cleared": rules_cleared,
        }
        json.dump(result, sys.stdout)
        sys.stdout.write("\n")
        return result

    result = {
        "compacted": False,
        "context_drop_percent": drop,
    }
    json.dump(result, sys.stdout)
    sys.stdout.write("\n")
    return result


def cmd_reset_after_compaction(session_id: str) -> None:
    """Clear current phase's exclusion list and reset budget. For PostCompact hook."""
    with mutate_cache(session_id) as cache:
        current_phase = cache.get("current_phase", "unknown")
        by_phase = cache.get("loaded_rule_ids_by_phase", {})
        cleared = list(by_phase.get(current_phase, []))
        by_phase[current_phase] = []
        cache["loaded_rule_ids_by_phase"] = by_phase
        cache["remaining_budget"] = DEFAULT_SESSION_BUDGET
        # Clear sticky rules preference (stale after compaction)
        cache["last_injected_rule_ids"] = []
        # Re-arm context-watcher debounce: PostCompact frees the window, so the
        # 50% / 75% bands should re-fire on the next crossing.
        cache["context_warning_emitted_at_pct"] = 0
    _log_friction_event(
        session_id, cache.get("mode"), "post_compaction",
        rules_cleared=cleared, budget_reset=True, phase=current_phase,
    )
    # mode + phase are returned so the PostCompact hook can re-state the
    # agent's workflow position (the next rag-inject only fires on the next
    # user prompt; an autonomously-resuming agent would otherwise have none).
    result = {
        "rules_cleared": cleared,
        "budget_reset": True,
        "mode": cache.get("mode"),
        "phase": current_phase,
    }
    json.dump(result, sys.stdout)
    sys.stdout.write("\n")
