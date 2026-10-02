"""Writ analysis module -- code compliance checking.

Provides the /analyze endpoint's core logic: pattern extraction,
confidence-scored scanning, LLM escalation, and calibration instrumentation.

The pydantic models are built on first attribute access (PEP 562 module __getattr__), so
importing this package or its stdlib-only submodules (token_audit, token_tree, jsonl) never
imports pydantic. Hook interpreters load those submodules and may not have pydantic at all.
The models are built once, under a lock, and cached in the module namespace, so every access
returns the same class object.
"""

import threading

_MODEL_NAMES = frozenset({"AnalyzeRequest", "Finding", "AnalyzeResponse"})
_build_lock = threading.Lock()


def _build_models() -> dict[str, type]:
    # Each class pins __qualname__ in its body, before pydantic builds its schema refs, so it
    # reads `Finding` rather than `_build_models.<locals>.Finding`.
    from pydantic import BaseModel

    class AnalyzeRequest(BaseModel):
        """Request body for POST /analyze."""

        __qualname__ = "AnalyzeRequest"
        code: str
        file_path: str
        phase: str  # "planning" | "code_generation" | "testing" | "review"
        context: str

    class Finding(BaseModel):
        """Unified finding from pattern matching or LLM analysis."""

        __qualname__ = "Finding"
        rule_id: str
        source: str  # "pattern" | "llm"
        status: str  # "violated" | "pass" | "uncertain"
        line: int | None = None
        confidence: str | None = None  # "high" | "medium" | "low" | None (null for llm)
        evidence: str = ""
        suggestion: str = ""

    class AnalyzeResponse(BaseModel):
        """Response body for POST /analyze."""

        __qualname__ = "AnalyzeResponse"
        verdict: str  # "pass" | "fail" | "warn"
        findings: list[Finding] = []
        rules_checked: list[str] = []
        analysis_method: str = "pattern"  # "pattern" | "llm" | "hybrid" | "calibration"
        retrieval_scores: dict[str, float] = {}
        summary: str = ""

    return {"AnalyzeRequest": AnalyzeRequest, "Finding": Finding,
            "AnalyzeResponse": AnalyzeResponse}


def __getattr__(name: str):
    if name not in _MODEL_NAMES:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    with _build_lock:
        namespace = globals()
        if name not in namespace:
            namespace.update(_build_models())
    return namespace[name]
