"""writ.analysis resolves its pydantic models lazily (PEP 562), and the SubagentStop hook relies on it.

Importing the package, or any of its stdlib-only submodules (token_audit, token_tree, jsonl),
must not import pydantic: a hook interpreter may not have it. The models must still resolve
through `from writ.analysis import ...` and attribute access, as the same class object every time.
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
STOP_HOOK = REPO / "hooks" / "scripts" / "writ-subagent-stop.sh"
MODEL_NAMES = ("AnalyzeRequest", "Finding", "AnalyzeResponse")


def _run(code: str, env: dict | None = None) -> subprocess.CompletedProcess:
    base = {**os.environ, "PYTHONPATH": str(REPO)}
    if env:
        base.update(env)
    return subprocess.run([sys.executable, "-c", code], cwd=str(REPO), env=base,
                          capture_output=True, text=True, timeout=60)


class TestNoPydanticOnStdlibImports:
    @pytest.mark.parametrize("module", [
        "writ.analysis",
        "writ.analysis.token_audit",
        "writ.analysis.token_tree",
        "writ.analysis.jsonl",
    ])
    def test_import_leaves_pydantic_unloaded(self, module) -> None:
        proc = _run(
            "import sys, importlib\n"
            f"importlib.import_module({module!r})\n"
            "import writ.analysis as pkg\n"
            "print('pydantic' in sys.modules)\n"
            f"print(any(n in vars(pkg) for n in {MODEL_NAMES!r}))\n"
        )
        assert proc.returncode == 0, proc.stderr
        assert proc.stdout.split() == ["False", "False"]

    def test_token_audit_imports_where_pydantic_is_unavailable(self, tmp_path) -> None:
        # HOME under tmp hides user site-packages, which is where pydantic lives for a
        # user-installed toolchain; the hook's sandboxed tests run the same way.
        proc = _run(
            "import sys\n"
            "sys.modules['pydantic'] = None\n"
            "from writ.analysis.token_audit import SUMMARY_ERROR, usage_summary_event\n"
            "print('ok')\n",
            env={"HOME": str(tmp_path)},
        )
        assert proc.returncode == 0, proc.stderr
        assert proc.stdout.strip() == "ok"

    def test_model_access_without_pydantic_raises_import_error(self) -> None:
        proc = _run(
            "import sys\n"
            "sys.modules['pydantic'] = None\n"
            "try:\n"
            "    from writ.analysis import Finding\n"
            "except ImportError:\n"
            "    print('import-error')\n",
        )
        assert proc.returncode == 0, proc.stderr
        assert proc.stdout.strip() == "import-error"


class TestModelsStillResolve:
    def test_from_import_returns_pydantic_models(self) -> None:
        from pydantic import BaseModel

        from writ.analysis import AnalyzeRequest, AnalyzeResponse, Finding

        for cls in (AnalyzeRequest, AnalyzeResponse, Finding):
            assert issubclass(cls, BaseModel)

    def test_every_access_returns_the_same_class_object(self) -> None:
        import importlib

        import writ.analysis as pkg
        from writ.analysis import AnalyzeRequest, AnalyzeResponse, Finding

        first = {"AnalyzeRequest": AnalyzeRequest, "AnalyzeResponse": AnalyzeResponse,
                 "Finding": Finding}
        for name in MODEL_NAMES:
            assert getattr(pkg, name) is first[name]
            assert getattr(importlib.import_module("writ.analysis"), name) is first[name]
            assert vars(pkg)[name] is first[name]

    def test_consumers_share_the_same_finding_class(self) -> None:
        from writ.analysis import AnalyzeResponse, Finding, analyzer, instrumentation, llm, patterns

        assert patterns.Finding is Finding
        assert llm.Finding is Finding
        assert instrumentation.Finding is Finding
        assert analyzer.Finding is Finding
        assert analyzer.AnalyzeResponse is AnalyzeResponse

    def test_models_keep_their_public_identity(self) -> None:
        import writ.analysis as pkg

        for name in MODEL_NAMES:
            cls = getattr(pkg, name)
            assert cls.__name__ == name
            assert cls.__qualname__ == name
            assert cls.__module__ == "writ.analysis"

    def test_models_validate_as_before(self) -> None:
        from writ.analysis import AnalyzeRequest, AnalyzeResponse, Finding

        req = AnalyzeRequest(code="x = 1", file_path="a.py", phase="review", context="")
        assert req.phase == "review"

        f = Finding(rule_id="R-1", source="pattern", status="violated", line=3,
                    confidence="high")
        assert f.evidence == "" and f.suggestion == ""
        resp = AnalyzeResponse(verdict="fail", findings=[f])
        assert isinstance(resp.findings[0], Finding)
        assert resp.findings[0].rule_id == "R-1"
        assert resp.analysis_method == "pattern"
        assert resp.rules_checked == [] and resp.retrieval_scores == {}

        rebuilt = AnalyzeResponse.model_validate(resp.model_dump())
        assert isinstance(rebuilt.findings[0], Finding)
        assert rebuilt == resp

        with pytest.raises(Exception):
            Finding(source="pattern", status="pass")

    def test_unknown_attribute_raises_attribute_error(self) -> None:
        import writ.analysis as pkg

        with pytest.raises(AttributeError, match="no_such_name"):
            pkg.no_such_name  # noqa: B018
        assert not hasattr(pkg, "no_such_name")


def _usage_block() -> str:
    text = STOP_HOOK.read_text()
    start = text.index("# DURABLE USAGE SUMMARY")
    end = text.index("# Read the agent's session cache", start)
    return text[start:end]


class TestSubagentStopUsageBlock:
    def test_block_no_longer_stubs_the_analysis_package(self) -> None:
        block = _usage_block()
        assert "sys.modules" not in block
        assert "ModuleType" not in block
        assert "from writ.analysis.token_audit import" in block

    def test_block_is_guarded_on_a_non_empty_agent_id(self) -> None:
        block = _usage_block()
        code = "\n".join(line for line in block.splitlines() if not line.lstrip().startswith("#"))
        guard = re.search(r'if \[ -n "\$AGENT_ID" \]; then\n(.*?)\nfi\b', code, re.S)
        assert guard, "subagent_usage block is not wrapped in an AGENT_ID guard"
        assert "usage_summary_event" in guard.group(1)
        assert "|| true" in guard.group(1)
