"""Wave-3 Cycle C: collapse the 12 duplicated per-class field validators on
Rule and _MethodologyNodeBase into 5 shared module-level functions
(`_validate_domain_value`, `_validate_scope_value`, `_validate_authority_value`,
`_validate_graduated_via_value`, `_validate_non_empty_text_value`), bound via
`field_validator(...)(fn)` -- the same pattern the existing
`_validate_provenance_value` already uses for Abstraction/Category.

HERMETIC: pure Pydantic model construction. No Neo4j, no daemon, no I/O.

RED now (HEAD): the 5 shared functions do not exist yet; the old per-class
`@field_validator @classmethod def validate_*` / `_validate_*` methods are
still in place.
GREEN after the collapse: the shared functions exist and both Rule and
_MethodologyNodeBase (and its subclasses, e.g. Skill) bind their field
validators to them, with unchanged validation BEHAVIOR.

Classes 1-2 are structure guards (RED now, GREEN after the collapse).
Classes 3-4 are the behavioral net: they exercise TODAY's per-class
validators and must stay GREEN across the collapse (behavior parity).
"""
from __future__ import annotations

from datetime import date

import pytest
from pydantic import ValidationError

import writ.graph.schema as schema
from writ.graph.schema import Rule, Severity, Skill, _MethodologyNodeBase


# --- Class 1: the 5 shared functions must exist at module level --------------


class TestSharedValidatorFunctionsExist:
    """The collapse adds 5 new shared module-level validator functions next to
    the existing `_validate_provenance_value`. This is the primary RED signal:
    on HEAD none of the 5 exist yet."""

    SHARED_VALIDATOR_NAMES = (
        "_validate_domain_value",
        "_validate_scope_value",
        "_validate_authority_value",
        "_validate_graduated_via_value",
        "_validate_non_empty_text_value",
    )

    @pytest.mark.parametrize("name", SHARED_VALIDATOR_NAMES)
    def test_shared_validator_function_exists_and_is_callable(self, name: str) -> None:
        assert hasattr(schema, name), f"writ.graph.schema.{name} does not exist yet"
        assert callable(getattr(schema, name)), f"writ.graph.schema.{name} is not callable"

    def test_preexisting_provenance_validator_still_present(self) -> None:
        """The pre-existing shared fn (already used by Abstraction/Category) must
        survive the collapse unchanged -- Rule and _MethodologyNodeBase should
        adopt it too rather than duplicate their own."""
        assert hasattr(schema, "_validate_provenance_value")
        assert callable(schema._validate_provenance_value)


# --- Class 2: the old per-class validator methods are gone -------------------


class TestValidatorMethodsCollapsed:
    """The 12 old per-class `@field_validator @classmethod def` validators are
    removed in favor of the 5 shared functions bound via `field_validator(...)(fn)`
    assignment (mirroring Abstraction._validate_provenance today).

    Rule currently binds these under the UN-prefixed public name (`validate_domain`
    etc.) as a locally-defined classmethod -- so simple key absence from
    Rule.__dict__ is a clean RED-now/GREEN-after signal.

    _MethodologyNodeBase already uses the underscore-prefixed attribute names
    (`_validate_domain` etc.), and the collapse is expected to keep those same
    attribute names (only rebinding them to the shared function) -- so key
    presence/absence can't discriminate before/after. Instead this checks WHERE
    the bound function was actually defined via `__func__.__qualname__`: today
    it's a `def` inside the class body (qualname == "_MethodologyNodeBase.<name>");
    after the collapse it's the shared module-level function (qualname has no
    class prefix).
    """

    RULE_SHARED_VALIDATOR_NAMES = (
        "validate_domain",
        "validate_scope",
        "validate_authority",
        "validate_provenance",
        "validate_graduated_via",
        "validate_non_empty_text",
    )

    BASE_SHARED_VALIDATOR_ATTRS = (
        "_validate_domain",
        "_validate_scope",
        "_validate_authority",
        "_validate_provenance",
        "_validate_graduated_via",
        "_validate_non_empty_text",
    )

    @staticmethod
    def _bound_func_qualname(model_cls: type, attr_name: str) -> str:
        obj = model_cls.__dict__.get(attr_name)
        assert obj is not None, f"{model_cls.__name__}.{attr_name} is missing entirely"
        func = getattr(obj, "__func__", obj)
        return func.__qualname__

    @pytest.mark.parametrize("name", RULE_SHARED_VALIDATOR_NAMES)
    def test_rule_no_longer_defines_public_validator_method(self, name: str) -> None:
        assert name not in Rule.__dict__, (
            f"Rule.{name} is still a locally-defined per-class validator method; "
            "expected the collapse to remove it in favor of the shared "
            "module-level validator function"
        )

    @pytest.mark.parametrize("attr_name", BASE_SHARED_VALIDATOR_ATTRS)
    def test_base_validator_bound_to_shared_module_function(self, attr_name: str) -> None:
        qualname = self._bound_func_qualname(_MethodologyNodeBase, attr_name)
        assert not qualname.startswith("_MethodologyNodeBase."), (
            f"_MethodologyNodeBase.{attr_name} is still bound to a locally-defined "
            f"classmethod (qualname={qualname!r}); expected it rebound to the shared "
            "module-level validator function"
        )


# --- Class 3: Rule's validators -- behavioral net, GREEN today and after -----


def _valid_rule_kwargs() -> dict:
    """Minimal valid values for every required Rule field."""
    return {
        "rule_id": "TEST-VALCOL-001",
        "domain": "testing",
        "severity": Severity.MEDIUM,
        "scope": "file",
        "trigger": "When touching the shared validator collapse.",
        "statement": "Shared validators must reject the same values as before.",
        "violation": "A per-class validator diverges from the shared function.",
        "pass_example": "All five shared validators behave identically pre/post collapse.",
        "enforcement": "This test suite.",
        "rationale": "Behavior parity is the entire point of the collapse.",
        "last_validated": date(2026, 7, 14),
    }


class TestRuleValidatorsRejectAndAccept:
    """Exercises Rule's validators as they behave TODAY (per-class methods).
    Must stay GREEN after the collapse (shared functions), proving behavior
    parity."""

    def test_valid_rule_constructs(self) -> None:
        rule = Rule(**_valid_rule_kwargs())
        assert rule.rule_id == "TEST-VALCOL-001"

    def test_empty_domain_rejected(self) -> None:
        kwargs = _valid_rule_kwargs()
        kwargs["domain"] = ""
        with pytest.raises(ValidationError) as excinfo:
            Rule(**kwargs)
        assert "domain must not be empty" in str(excinfo.value)

    def test_bad_scope_rejected(self) -> None:
        kwargs = _valid_rule_kwargs()
        kwargs["scope"] = "BadScope"
        with pytest.raises(ValidationError) as excinfo:
            Rule(**kwargs)
        assert (
            "must be lowercase, start with a letter, and match [a-z][a-z0-9_-]*"
            in str(excinfo.value)
        )

    def test_bad_authority_rejected(self) -> None:
        kwargs = _valid_rule_kwargs()
        kwargs["authority"] = "bogus"
        with pytest.raises(ValidationError) as excinfo:
            Rule(**kwargs)
        assert "must be one of" in str(excinfo.value)

    def test_bad_provenance_rejected(self) -> None:
        kwargs = _valid_rule_kwargs()
        kwargs["provenance"] = "bogus"
        with pytest.raises(ValidationError) as excinfo:
            Rule(**kwargs)
        assert "provenance 'bogus' must be one of" in str(excinfo.value)

    def test_bad_graduated_via_rejected(self) -> None:
        kwargs = _valid_rule_kwargs()
        kwargs["graduated_via"] = "bogus"
        with pytest.raises(ValidationError) as excinfo:
            Rule(**kwargs)
        assert "(or unset)" in str(excinfo.value)

    def test_graduated_via_none_accepted(self) -> None:
        kwargs = _valid_rule_kwargs()
        kwargs["graduated_via"] = None
        rule = Rule(**kwargs)
        assert rule.graduated_via is None

    @pytest.mark.parametrize(
        "field", ["trigger", "statement", "violation", "pass_example", "enforcement", "rationale"]
    )
    def test_whitespace_only_text_fields_rejected(self, field: str) -> None:
        kwargs = _valid_rule_kwargs()
        kwargs[field] = "   "
        with pytest.raises(ValidationError) as excinfo:
            Rule(**kwargs)
        assert "field must not be empty or whitespace-only" in str(excinfo.value)


# --- Class 4: Skill inherits _MethodologyNodeBase's validators ---------------


def _valid_skill_kwargs() -> dict:
    """Minimal valid values for every required Skill field (mirrors
    test_phase6a_node_models.base_kwargs() plus the Skill-specific skill_id)."""
    return {
        "domain": "testing",
        "severity": Severity.MEDIUM,
        "scope": "file",
        "trigger": "When touching the shared validator collapse.",
        "statement": "Shared validators must reject the same values as before.",
        "rationale": "Behavior parity is the entire point of the collapse.",
        "last_validated": date(2026, 7, 14),
        "skill_id": "SKL-TEST-VALCOL-001",
    }


class TestSkillSubclassInheritsValidators:
    """Skill inherits _MethodologyNodeBase's field validators without redefining
    them. Exercises the inherited behavior as it stands TODAY (per-class methods
    on _MethodologyNodeBase); must stay GREEN after the collapse (shared
    functions), proving the subclass inheritance path is unaffected."""

    def test_valid_skill_constructs(self) -> None:
        skill = Skill(**_valid_skill_kwargs())
        assert skill.skill_id == "SKL-TEST-VALCOL-001"

    def test_empty_domain_rejected(self) -> None:
        kwargs = _valid_skill_kwargs()
        kwargs["domain"] = ""
        with pytest.raises(ValidationError) as excinfo:
            Skill(**kwargs)
        assert "domain must not be empty" in str(excinfo.value)

    def test_bad_scope_rejected(self) -> None:
        kwargs = _valid_skill_kwargs()
        kwargs["scope"] = "BadScope"
        with pytest.raises(ValidationError) as excinfo:
            Skill(**kwargs)
        assert (
            "must be lowercase, start with a letter, and match [a-z][a-z0-9_-]*"
            in str(excinfo.value)
        )

    def test_bad_authority_rejected(self) -> None:
        kwargs = _valid_skill_kwargs()
        kwargs["authority"] = "bogus"
        with pytest.raises(ValidationError) as excinfo:
            Skill(**kwargs)
        assert "must be one of" in str(excinfo.value)

    def test_bad_provenance_rejected(self) -> None:
        kwargs = _valid_skill_kwargs()
        kwargs["provenance"] = "bogus"
        with pytest.raises(ValidationError) as excinfo:
            Skill(**kwargs)
        assert "provenance 'bogus' must be one of" in str(excinfo.value)

    def test_bad_graduated_via_rejected(self) -> None:
        kwargs = _valid_skill_kwargs()
        kwargs["graduated_via"] = "bogus"
        with pytest.raises(ValidationError) as excinfo:
            Skill(**kwargs)
        assert "(or unset)" in str(excinfo.value)

    def test_graduated_via_none_accepted(self) -> None:
        kwargs = _valid_skill_kwargs()
        kwargs["graduated_via"] = None
        skill = Skill(**kwargs)
        assert skill.graduated_via is None

    @pytest.mark.parametrize("field", ["trigger", "statement", "rationale"])
    def test_whitespace_only_text_fields_rejected(self, field: str) -> None:
        # Skill's non-empty-text validator covers only trigger/statement/rationale
        # (the fields _MethodologyNodeBase declares) -- Rule-only fields like
        # violation/pass_example/enforcement do not exist on Skill.
        kwargs = _valid_skill_kwargs()
        kwargs[field] = "   "
        with pytest.raises(ValidationError) as excinfo:
            Skill(**kwargs)
        assert "field must not be empty or whitespace-only" in str(excinfo.value)
