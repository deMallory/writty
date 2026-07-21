"""Static delivery lint for Writ hooks (Task #7C: the "never blind again" guard).

Reads hooks/hooks.json and each wired script, then flags injectors whose rule
text cannot reach the model. A hook on a NON-special event that emits directive/
RAG text to plain stdout without an additionalContext / permissionDecisionReason
wrapper goes only to the CC debug log (see writ.shared.delivery), so the model
never sees those rules -- cost paid, nothing delivered.

This is the STATIC complement to the runtime delivery telemetry in
writ.analysis.friction: the linter catches an inert injector before it ever runs;
the telemetry confirms it from real events. A source whose logged deliveries are
all "debug-log" is the runtime confirmation of a static "inert" flag here.

Conservative by design (the C1 lesson, where a 13-agent audit false-flagged a
working security gate): two-signal matching, an explicit allowlist, and findings
default to WARNINGS rather than hard failures.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from writ.shared.delivery import STDOUT_TO_MODEL_EVENTS

# Writ's injection signature: model-facing directive blocks start with "[Writ:"
# or "[WRIT ...". Detected only when rendered to BARE STDOUT (the channel that
# fails to reach the model on a non-special event) -- never when it merely
# appears in source (a comment, a stderr warning, or inside an additionalContext
# JSON string is NOT an inert injection). This precision is the C1 lesson:
# validate-rules.sh emits "[Writ ...]" to stderr and must NOT be flagged.
_INJECT_MARKER = re.compile(r"\[[Ww][Rr][Ii][Tt][ :\]]")
# echo/printf <text>. The marker + redirection are checked against the rest.
_BARE_MARKER_LINE = re.compile(r"^\s*(echo|printf)\b(?P<rest>[^\n]*)")
# cat <<EOF / cat << 'DELIM' / cat <<-DELIM : start of a heredoc whose body
# streams to stdout (unless the same line redirects it away).
_HEREDOC_START = re.compile(r"^(?P<pre>.*?)<<-?\s*['\"]?(?P<delim>\w+)['\"]?")
_REDIRECT = re.compile(r">&2|1>&2|>>?\s*\S")
# If the emitted text is itself a model-facing wrapper, it is NOT bare injection:
# an `echo`/`printf` of a hookSpecificOutput/additionalContext JSON reaches the
# model regardless of event. Skip such emissions.
_MODEL_CHANNEL_TOKENS = ("additionalContext", "hookSpecificOutput", "permissionDecisionReason")

# Scripts known-correct or intentionally debug-log-only. Empty for now: the
# heuristic is precise enough against the current set. Add a basename here (with
# a reason) only after verifying by triggering that it is not inert.
_ALLOWLIST: frozenset[str] = frozenset()


def _resolve_script(command: str, plugin_root: Path) -> Path | None:
    """Resolve a hooks.json command string to a script path under plugin_root."""
    m = re.search(r"\$\{CLAUDE_PLUGIN_ROOT\}/(\S+)", command)
    if m:
        return plugin_root / m.group(1)
    for tok in reversed(command.split()):
        if tok.endswith(".sh"):
            return plugin_root / tok.lstrip("/")
    return None


def _reaches_model(src: str) -> bool:
    """True if the script has any model-facing channel (additionalContext or
    permissionDecisionReason)."""
    return ("additionalContext" in src) or ("permissionDecisionReason" in src)


def _emits_marker_to_stdout(src: str) -> bool:
    """True if the script renders the Writ injection marker to BARE stdout, via
    echo/printf or a cat-heredoc, without redirecting it to stderr or a file.

    This is the precise "injection text the model would only see on a special
    event" signal. It deliberately ignores the marker inside additionalContext
    JSON (bible-authoring-push) and on stderr (validate-rules)."""
    lines = src.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i]
        m = _BARE_MARKER_LINE.match(line)
        if m:
            rest = m.group("rest")
            wraps_model_channel = any(t in rest for t in _MODEL_CHANNEL_TOKENS)
            if (not (">&2" in rest or "1>&2" in rest)
                    and not wraps_model_channel
                    and _INJECT_MARKER.search(rest)):
                return True
        hd = _HEREDOC_START.search(line)
        if hd and "cat" in line.split("<<")[0]:
            pre = line.split("<<")[0]
            # Captured by a command substitution (VAR=$(cat <<...) or `cat <<...`)
            # -> the heredoc feeds the substitution, NOT the hook's stdout, so it
            # is not bare injection (it is typically delivered via additionalContext).
            captured = ("$(" in pre) or ("`" in pre)
            redirected = bool(_REDIRECT.search(pre))
            delim = hd.group("delim")
            j = i + 1
            body_has_marker = False
            body_wraps_channel = False
            while j < len(lines) and lines[j].strip() != delim:
                if _INJECT_MARKER.search(lines[j]):
                    body_has_marker = True
                if any(t in lines[j] for t in _MODEL_CHANNEL_TOKENS):
                    body_wraps_channel = True
                j += 1
            if not captured and not redirected and body_has_marker and not body_wraps_channel:
                return True
            i = j
            continue
        i += 1
    return False


def _is_injector(src: str) -> bool:
    """True if the script delivers rules/directives meant for the model: it logs
    an injection (log_rag_query_event) or renders the marker to bare stdout."""
    return ("log_rag_query_event" in src) or _emits_marker_to_stdout(src)


def lint_hooks(hooks_json: Path, plugin_root: Path) -> list[dict]:
    """Return delivery findings for every injector wired to a non-special event.

    Each finding: {severity, script, event, matcher, detail}. severity is
    "inert" (high confidence: no model channel at all), "review" (a model
    channel exists but the script ALSO emits injection text to bare stdout on
    this event), or "error" (could not read hooks.json).
    """
    findings: list[dict] = []
    try:
        data = json.loads(hooks_json.read_text())
    except (OSError, json.JSONDecodeError) as e:
        return [{
            "severity": "error", "script": str(hooks_json), "event": "-",
            "matcher": "-", "detail": f"cannot read hooks.json: {e}",
        }]

    hooks = data.get("hooks", data)
    for event, groups in hooks.items():
        # On these events plain stdout reaches the model, so injecting freely is
        # correct -- nothing to flag.
        if event in STDOUT_TO_MODEL_EVENTS:
            continue
        if not isinstance(groups, list):
            continue
        for g in groups:
            matcher = g.get("matcher", "")
            for h in g.get("hooks", []):
                spath = _resolve_script(h.get("command", ""), plugin_root)
                if spath is None or not spath.exists():
                    continue
                name = spath.name
                if name in _ALLOWLIST:
                    continue
                try:
                    src = spath.read_text()
                except OSError:
                    continue
                if not _is_injector(src):
                    continue
                if not _reaches_model(src):
                    findings.append({
                        "severity": "inert", "script": name, "event": event,
                        "matcher": matcher,
                        "detail": (
                            "injects rule/directive text to plain stdout on a "
                            "non-special event -> CC debug log; the model never "
                            "sees it. Wrap in hookSpecificOutput.additionalContext "
                            "(see writ-bible-authoring-push.sh)."
                        ),
                    })
                elif _emits_marker_to_stdout(src):
                    findings.append({
                        "severity": "review", "script": name, "event": event,
                        "matcher": matcher,
                        "detail": (
                            "has a model channel (additionalContext/"
                            "permissionDecisionReason) but ALSO emits injection "
                            "text to bare stdout on this event (debug-log only); "
                            "verify nothing model-facing rides the bare path."
                        ),
                    })
    # Stable order for deterministic output / tests.
    sev_order = {"error": 0, "inert": 1, "review": 2}
    findings.sort(key=lambda f: (sev_order.get(f["severity"], 9), f["event"], f["script"]))
    return findings
