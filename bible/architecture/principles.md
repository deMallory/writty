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
---

<!-- RULE START: ARCH-TYPE-001 -->
## Rule ARCH-TYPE-001

**Domain**: Architecture
**Severity**: High
**Scope**: Entity
**Mandatory**: false

### Trigger
Any public function (not prefixed with `_` in Python, not `private`/`protected` in PHP/TS) lacks complete parameter and return type annotations.

### Statement
All public functions must have complete type annotations on every parameter and the return value. Language-specific enforcement tools validate correctness.

### Violation
```python
def search(query, limit):
    ...
```

### Pass
```python
def search(query: str, limit: int) -> list[ScoredResult]:
    ...
```

### Enforcement
- Python: `mypy --strict` or `pyright` - PHP: PHPStan level 8 (see also PHP-TYPE-001 for docblock-specific guidance) - TypeScript: `tsc --strict`

### Rationale
Public interfaces are contracts. Unannotated parameters force callers to read implementation to understand expected types. Type annotations enable static analysis, IDE autocompletion, and catch type errors before runtime.

<!-- RULE END: ARCH-TYPE-001 -->
