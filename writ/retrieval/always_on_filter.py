"""Applicability-scoped selection for always-on Rules (WRIT-BLUEPRINT 3.5).

The always-on bundle used to inject every rule on every UserPromptSubmit. This filter
selects only the rules applicable at the current injection point, so a rule reaches the
agent at the moment its WHEN matches instead of all-of-them-every-turn. No weights and no
budget drop: applicability decides, not ranking. Fail-open: a rule with no routing data is
treated as universal so it is never silently dropped.

Each rule dict carries:
  applicability_scope: list[str]  -- injection points: universal / prompt / write / bash / stop
  trigger_keywords:    list[str]  -- whole-word context keywords matched at write/bash/prompt

Injection points (the `at` argument), each a hook call site:
  prompt -- UserPromptSubmit (per turn). Receives universal + empty-scope + prompt-keyword matches.
  write  -- PreToolUse(Write|Edit). Receives write-scope rules whose keywords match path+content.
  bash   -- PreToolUse(Bash). Receives bash-scope rules whose keywords match the command.
  stop   -- Stop. Receives stop-scope rules (response/verification discipline; no keyword needed).
"""

from __future__ import annotations

from writ.retrieval.trigger_index import _keyword_matches

INJECTION_POINTS = ("prompt", "write", "bash", "stop")


def rule_applies_at(rule: dict, at: str, context: str = "") -> bool:
    """True if `rule` should inject at injection point `at` given `context`.

    A rule applies at `at` when its scope lists `at`, OR it is universal/empty-scope and
    `at` is the per-turn point (`prompt`). When it applies and carries trigger_keywords, at
    least one keyword must whole-word-match `context`; a scope with no keywords always
    applies at its point (e.g. a stop-discipline rule). Empty scope is fail-open universal.
    """
    scope = rule.get("applicability_scope") or []
    keywords = rule.get("trigger_keywords") or []
    applies_here = (at in scope) or ((not scope or "universal" in scope) and at == "prompt")
    if not applies_here:
        return False
    if keywords and not any(_keyword_matches(k, context) for k in keywords):
        return False
    return True


def select_always_on(rules: list[dict], at: str, context: str = "") -> list[dict]:
    """Filter always-on rule dicts to those applicable at injection point `at`.

    Order-preserving. No ranking, no budget drop (every applicable rule is returned).
    """
    return [r for r in rules if rule_applies_at(r, at, context)]
