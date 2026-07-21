"""Calibration logging and escalation decision logic.

Tracks calibration state across requests and server restarts via
line count of the JSONL log file. Provides escalation decisions
based on pattern match confidence and retrieval scores.
"""

from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path

from writ.analysis import Finding
from writ.shared.logging import log_root

CALIBRATION_THRESHOLD = 100
RELEVANCE_SCORE_THRESHOLD = 0.6


class Instrumentation:
    """Calibration and escalation tracking for /analyze."""

    def __init__(self, log_path: str | Path | None = None) -> None:
        # Resolve the default LAZILY from log_root() (DRY-CONFIG-002) so a
        # WRIT_LOG_ROOT set after import, and test monkeypatching, both win.
        self._log_path = (
            Path(log_path) if log_path is not None
            else log_root() / "calibration.jsonl"
        )
        self._counter = self._read_counter()

    def _read_counter(self) -> int:
        """Count lines in JSONL file to resume calibration state."""
        if not self._log_path.exists():
            return 0
        try:
            with open(self._log_path) as f:
                return sum(1 for _ in f)
        except OSError:
            return 0

    def get_mode(self) -> str:
        """Current mode: 'calibration' or 'production'."""
        return "calibration" if self._counter < CALIBRATION_THRESHOLD else "production"

    def should_escalate(
        self,
        matches: list[Finding],
        retrieval_scores: dict[str, float],
    ) -> bool:
        """Decide whether to escalate from pattern matching to LLM.

        Calibration mode: always escalate (log both for paired comparison).
        Production mode: escalate on ambiguous matches or high-relevance rules.
        """
        if self.get_mode() == "calibration":
            return True

        # Any medium or low confidence match: escalate
        for m in matches:
            if m.confidence in ("medium", "low"):
                return True

        # No matches but high-relevance rules exist: escalate
        if not matches:
            has_relevant = any(
                score > RELEVANCE_SCORE_THRESHOLD
                for score in retrieval_scores.values()
            )
            if has_relevant:
                return True

        return False

    def log_calibration(
        self,
        file_path: str,
        phase: str,
        pattern_findings: list[Finding],
        llm_findings: list[Finding],
        rules_checked: list[str],
        retrieval_scores: dict[str, float],
    ) -> None:
        """Append paired comparison to calibration log."""
        pattern_verdict = _derive_verdict(pattern_findings)
        llm_verdict = _derive_verdict(llm_findings)

        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "file_path": file_path,
            "phase": phase,
            # Scrub secret-shaped substrings from the dumped copies before they
            # enter the persisted log (SEC-DATA-MASK-001 / CLEAN-LOG-002). The
            # Finding objects the /analyze HTTP path returns are never mutated.
            "pattern_findings": [_redact_finding(f.model_dump()) for f in pattern_findings],
            "llm_findings": [_redact_finding(f.model_dump()) for f in llm_findings],
            "pattern_verdict": pattern_verdict,
            "llm_verdict": llm_verdict,
            "agreed": pattern_verdict == llm_verdict,
            "rules_checked": rules_checked,
            "retrieval_scores": retrieval_scores,
        }

        try:
            # Create the log parent before the best-effort append so a missing
            # var/logs on a fresh install is not silently swallowed forever
            # (ERR-GRACEFUL-002).
            self._log_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self._log_path, "a") as f:
                f.write(json.dumps(entry) + "\n")
            self._counter += 1
        except OSError:
            pass  # Best-effort logging


# Secret-shaped substrings that must never land in a persisted calibration line
# (SEC-DATA-MASK-001). Standalone token shapes are fully replaced; a key=value /
# key: value credential form and a connection-string keep enough shape to stay
# readable while the secret value is scrubbed.
_SECRET_TOKEN_PATTERNS = (
    re.compile(r"sk_live_[A-Za-z0-9]+"),
    re.compile(r"AKIA[A-Z0-9]{8,}"),
    # JWT / bearer three-segment tokens: header.payload.signature.
    re.compile(r"eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+"),
    # PEM private-key markers (any key type: RSA/DSA/EC/OPENSSH/PGP/plain).
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
)
_SECRET_KV_PATTERN = re.compile(
    r"(?i)\b(password|token|secret|api[_-]?key)\s*[=:]\s*['\"]?[^'\"\s]+['\"]?"
)
# Authorization: Bearer <token> headers -- keep the scheme word, drop the token.
_SECRET_BEARER_PATTERN = re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/\-]+=*")
# Inline connection-string credentials: scheme://user:password@host. Keep the
# ://user:[REDACTED]@host shape so the line stays readable.
_SECRET_CONNSTR_PATTERN = re.compile(r"://([^/\s:@]+):([^@\s]+)@")


def _redact_secrets(text: str) -> str:
    """Replace secret-shaped substrings in free text with [REDACTED]."""
    text = _SECRET_CONNSTR_PATTERN.sub(lambda m: f"://{m.group(1)}:[REDACTED]@", text)
    text = _SECRET_BEARER_PATTERN.sub("Bearer [REDACTED]", text)
    text = _SECRET_KV_PATTERN.sub(lambda m: f"{m.group(1)}=[REDACTED]", text)
    for pat in _SECRET_TOKEN_PATTERNS:
        text = pat.sub("[REDACTED]", text)
    return text


def _redact_finding(d: dict) -> dict:
    """Scrub the free-text fields of a dumped finding dict in place.

    Operates on the `model_dump()` copy, never the Finding object, so the live
    /analyze HTTP response shape is unchanged.
    """
    for field in ("evidence", "suggestion"):
        value = d.get(field)
        if isinstance(value, str):
            d[field] = _redact_secrets(value)
    return d


def _derive_verdict(findings: list[Finding]) -> str:
    """Derive verdict from a list of findings."""
    if not findings:
        return "pass"
    statuses = {f.status for f in findings}
    if "violated" in statuses:
        return "fail"
    if "uncertain" in statuses:
        return "warn"
    return "pass"
