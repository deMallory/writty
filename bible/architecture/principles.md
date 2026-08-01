<!-- RULE START: ARCH-COMP-001 -->
## Rule ARCH-COMP-001

**Domain**: Architecture
**Severity**: High
**Scope**: Component
**Mandatory**: false

### Trigger
Class hierarchy depth exceeds 2 levels of project code. Language/framework base classes (`ABC`, `Protocol`, `BaseModel`, `AbstractController`, `AbstractPlugin`) are excluded from the count.

### Statement
Class inheritance depth must not exceed 2 levels of project code. Deeper hierarchies must be refactored to use composition via constructor injection.

### Violation
```python
class SpecificValidator(BaseValidator(AbstractValidator)):
    # 3 levels of project code -- too deep
    ...
```

### Pass
```python
class SpecificValidator:
    def __init__(self, strategy: ValidationStrategy):
        self._strategy = strategy

    def validate(self, data: dict) -> bool:
        return self._strategy.validate(data)
```

### Enforcement
Code review. Check class hierarchy depth during PR review.

### Rationale
Deep inheritance hierarchies create tight coupling, make behavior hard to trace, and resist testing. Composition via injection produces the same polymorphism with explicit, traceable dependencies.

<!-- RULE END: ARCH-COMP-001 -->
