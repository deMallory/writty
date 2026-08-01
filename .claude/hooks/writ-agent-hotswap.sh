#!/usr/bin/env bash
# Writ agent hot-swap -- PreToolUse hook for Task/Agent spawns.
# Rewrites generic subagent types to their writ-* equivalents and stamps
# the model per the OpusPlan routing policy, via updatedInput. Zero token
# cost: enforcement happens in the harness, not the prompt.
#
# STAGED TEMPLATE: copy to .claude/hooks/writ-agent-hotswap.sh (and the
# installed skill/plugin hooks dir), chmod +x, then register in hooks.json
# and/or settings.json under PreToolUse with matcher "Task".
# Hook type: PreToolUse (matcher: Task). Exit: always 0 (never block).

command -v jq >/dev/null 2>&1 || exit 0

INPUT=$(cat)

# Blackbox capture (see OVERVIEW.md): this hook parses stdin directly, so it
# records its own envelope when the capture flag is on.
if [ -f "$HOME/.claude/writ-blackbox.on" ]; then
  mkdir -p "$HOME/.claude/writ-blackbox" 2>/dev/null || true
  printf '%s\n' "$INPUT" | tr '\n' ' ' >> "$HOME/.claude/writ-blackbox/envelopes.jsonl" 2>/dev/null || true
  printf '\n' >> "$HOME/.claude/writ-blackbox/envelopes.jsonl" 2>/dev/null || true
fi
SUBAGENT=$(echo "$INPUT" | jq -r '.tool_input.subagent_type // empty')

[ -z "$SUBAGENT" ] && exit 0

# Generic -> writ-* routing map
case "$SUBAGENT" in
  Explore|explore)      NEW_TYPE="writ-explorer" ;;
  Plan|plan)            NEW_TYPE="writ-planner" ;;
  *)                    NEW_TYPE="$SUBAGENT" ;;
esac

# OpusPlan model routing: planning/research -> opus, execution -> sonnet.
# Only stamp when the caller did not set a model explicitly.
MODEL=$(echo "$INPUT" | jq -r '.tool_input.model // empty')
if [ -z "$MODEL" ]; then
  case "$NEW_TYPE" in
    writ-explorer|writ-planner|writ-spec-reviewer|writ-code-quality-reviewer)
      NEW_MODEL="opus" ;;
    writ-implementer|writ-test-writer|general-purpose|claude)
      NEW_MODEL="sonnet" ;;
    *)
      NEW_MODEL="" ;;
  esac
else
  NEW_MODEL=""
fi

# Nothing to rewrite -- pass through silently.
if [ "$NEW_TYPE" = "$SUBAGENT" ] && [ -z "$NEW_MODEL" ]; then
  exit 0
fi

UPDATED_INPUT=$(echo "$INPUT" | jq -c --arg t "$NEW_TYPE" --arg m "$NEW_MODEL" '
  .tool_input
  | .subagent_type = $t
  | if $m != "" then .model = $m else . end
')

jq -n --argjson updated "$UPDATED_INPUT" '{
  "hookSpecificOutput": {
    "hookEventName": "PreToolUse",
    "permissionDecision": "allow",
    "permissionDecisionReason": "Writ agent hot-swap",
    "updatedInput": $updated
  }
}'
