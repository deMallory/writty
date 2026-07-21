"""Guard for the Wave 3 doctor.py CheckResult-factory dedup.

writ/session/doctor.py hand-repeated the `CheckResult(name=.., status=.., detail=..,
fixable=.., fix=..)` construction shape at 32 sites. The dedup introduces three factories
`_ok/_warn/_fail(name, detail, *, fixable=False, fix=None)` that fix `status` and default
the non-fixable case, and rewrites every site to call them.

RED today: the factories do not exist (imports fail) and 32 inline `CheckResult(` calls remain.
"""
from __future__ import annotations

from pathlib import Path

from writ.session.doctor import (  # RED today: factories absent
    STATUS_FAIL,
    STATUS_OK,
    STATUS_WARN,
    CheckResult,
    _fail,
    _ok,
    _warn,
)

DOCTOR = Path(__file__).resolve().parent.parent / "writ" / "session" / "doctor.py"


class TestFactories:
    def test_ok_sets_status_ok_and_defaults(self) -> None:
        r = _ok("n", "d")
        assert isinstance(r, CheckResult)
        assert r.status == STATUS_OK
        assert r.name == "n"
        assert r.detail == "d"
        assert r.fixable is False
        assert r.fix is None

    def test_warn_sets_status_warn(self) -> None:
        assert _warn("n", "d").status == STATUS_WARN

    def test_fail_sets_status_fail(self) -> None:
        assert _fail("n", "d").status == STATUS_FAIL

    def test_factories_pass_through_fixable_and_fix(self) -> None:
        def cb() -> None:
            return None

        r = _fail("n", "d", fixable=True, fix=cb)
        assert r.fixable is True
        assert r.fix is cb


class TestNoInlineConstructionRemains:
    def test_checkresult_constructed_only_inside_factories(self) -> None:
        src = DOCTOR.read_text()
        # After the dedup, `CheckResult(` is constructed only in the 3 factory bodies.
        n = src.count("CheckResult(")
        assert n == 3, f"expected 3 CheckResult( calls (one per factory); found {n}"

    def test_factories_are_used(self) -> None:
        src = DOCTOR.read_text()
        for fac in ("_ok(", "_warn(", "_fail("):
            assert fac in src, f"{fac} must be used by the check functions"
