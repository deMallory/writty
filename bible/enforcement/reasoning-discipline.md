<!-- RULE START: ENF-CTX-003 -->
## Rule ENF-CTX-003

**Domain**: enforcement
**Category**: CAT-CODE-AIENF-001
**Severity**: High
**Scope**: Entity
**Mandatory**: true
**Mechanical_Enforcement_Path**: bin/run-analysis.sh (PHPCS lint)
**Applicability_Scope**: write
**Trigger_Keywords**: Model::load, service contract, repository pattern, factory pattern, active record

### Trigger
When generated code uses patterns that appear frequently in training data but conflict with the project's rules -- specifically: factory patterns over repositories, Model::load() over service contracts, string inference over persistence verification.

### Statement
Any pattern from training data that conflicts with the Bible's rules is a violation. The project's rules override training data patterns.

### Violation
```php
// Training-data bias -- factory/load pattern appears in millions of Magento examples
$product = $this->productFactory->create()->load($productId);
// Violates FW-M2-002
```

### Pass
```php
// Project rule takes precedence
$product = $this->productRepository->getById($productId);
```

### Enforcement
Magento Coding Standard PHPCS (ENF-POST-007). FW-M2-002 catches factory/load patterns.

### Rationale
AI models are statistically biased toward deprecated patterns that appear frequently in older codebases. Explicit resistance prevents regression to outdated practices.

<!-- RULE END: ENF-CTX-003 -->
---

<!-- RULE START: ENF-GATE-006 -->
## Rule ENF-GATE-006

**Domain**: enforcement
**Category**: CAT-CODE-AIENF-001
**Severity**: High
**Scope**: Slice
**Mandatory**: true
**Mechanical_Enforcement_Path**: .claude/hooks/validate-handoff.sh
**Applicability_Scope**: write
**Trigger_Keywords**: handoff, handoffs

### Trigger
When writing a sub-agent / phase handoff file (`.claude/handoffs/*`) for dependency-ordered slice execution.

### Statement
A handoff file must be valid JSON and contain the required keys. A malformed or incomplete handoff is rejected: downstream slices depend on a well-formed handoff, so a broken one is blocked at the gate rather than silently consumed.

### Violation
```
.claude/handoffs/slice-2.json:
{ "summary": "did the thing"      <- truncated / invalid JSON, missing required keys
```

### Pass
```
.claude/handoffs/slice-2.json parses as JSON and contains every required key
(the downstream slice can consume it deterministically).
```

### Enforcement
.claude/hooks/validate-handoff.sh (PostToolUse on the handoff file) parses the JSON and checks required keys; on failure it emits an ENF-GATE-006 violation and blocks.

### Rationale
A dependency-ordered pipeline is only as reliable as the handoff between slices. Validating shape at the gate turns a late, confusing downstream failure into an immediate, local one.

Related rules: ENF-POST-006.

<!-- RULE END: ENF-GATE-006 -->
---

<!-- RULE START: ENF-GATE-007 -->
## Rule ENF-GATE-007

**Domain**: enforcement
**Category**: CAT-CODE-AIENF-001
**Severity**: Critical
**Scope**: Slice
**Mandatory**: true
**Mechanical_Enforcement_Path**: bin/lib/writ-session.py:1125-1370 (can_write test-skeleton gate)

### Trigger
In Work mode, after the planning phase has been approved (phase-a gate cleared) and before any implementation code is written.

### Statement
Test skeletons with specific assertions must be generated, written to disk via the Write tool, and approved before any implementation code. Implementation delivered without pre-approved test skeletons is a violation.

### Violation
```php
// Weak assertions that prove nothing:
$this->assertTrue($result);
$this->assertNotNull($response);

// Or empty stubs:
public function testRelease(): void
{
    // TODO: implement
}

// Or tests shown in chat but not written to disk
```

### Pass
```php
// Specific assertions that serve as executable specifications:
public function testReleaseChangesStatusToReleased(): void
{
    // ... setup ...
    $this->handler->release($reservationId);
    $this->assertEquals('released', $reservation->getStatus());
}

public function testReleaseOnAlreadyReleasedThrows(): void
{
    $this->expectException(AlreadyReleasedException::class);
    $this->handler->release($alreadyReleasedId);
}

public function testReleaseWithDbFailureReturnsSafeDefault(): void
{
    $this->repository->method('getById')->willThrowException(new \RuntimeException());
    $this->expectException(CouldNotSaveException::class);
    $this->handler->release($reservationId);
}
```

### Enforcement
Mechanically enforced by bin/lib/writ-session.py:1125-1370 (the test-skeletons gate in _can_write_check). Implementation writes are denied with [ENF-GATE-TEST] until the gate clears.

### Rationale
Tests generated after implementation become afterthought -- they validate what was built, not what was approved. Test-first makes it structurally harder to drift.

Related rules: ENF-PROC-TDD-001.

<!-- RULE END: ENF-GATE-007 -->
---

<!-- RULE START: ENF-POST-003 -->
## Rule ENF-POST-003

**Domain**: enforcement
**Category**: CAT-CODE-AIENF-001
**Severity**: Critical
**Scope**: Entity
**Mandatory**: true
**Mechanical_Enforcement_Path**: bin/run-analysis.sh (PHPStan level 8)
**Applicability_Scope**: write
**Trigger_Keywords**: implements interface, abstract method, method signature, interface contract

### Trigger
After generating a class that implements an interface, or after generating an interface and its implementation.

### Statement
Parameter order, parameter types, and return types in the interface must exactly match the implementation and all call sites.

### Violation
```php
// Interface:
public function release(int $itemId, string $sku): bool;

// Implementation -- param order SWAPPED:
public function release(string $sku, int $itemId): bool;
```

### Pass
```php
// Interface:
public function release(int $itemId, string $sku): bool;

// Implementation -- matches exactly:
public function release(int $itemId, string $sku): bool;
```

### Enforcement
PHPStan level 8 (ENF-POST-007) catches method signature mismatches.

### Rationale
Interface-implementation mismatches cause subtle runtime errors that surface only when a specific execution path is hit, especially with dependency injection.

<!-- RULE END: ENF-POST-003 -->
---

<!-- RULE START: ENF-POST-004 -->
## Rule ENF-POST-004

**Domain**: enforcement
**Category**: CAT-CODE-AIENF-001
**Severity**: Critical
**Scope**: Component
**Mandatory**: false

### Trigger
When writing tests for code that depends on declared domain invariants (data integrity rules, business rules with explicit constraints).

### Statement
Every declared domain invariant must have corresponding test coverage. The AI must refuse to mark implementation as complete if invariants lack tests.

### Violation
```
Phase B declared 3 invariants:
1. Coupon must exist in DB ← test exists ✓
2. Rule must be active ← NO test
3. Usage limit not exceeded ← NO test
// 2 of 3 invariants untested -- violation.
```

### Pass
```
Phase B declared 3 invariants -- all covered:
1. Coupon must exist: testNonExistentCouponReturnsFalse() ✓
2. Rule must be active: testInactiveRuleCouponReturnsFalse() ✓
3. Usage limit: testCouponAtUsageLimitReturnsFalse() + testCouponBelowLimitReturnsTrue() ✓
```

### Enforcement
Self-enforced via design review. The test-skeletons gate (ENF-GATE-007) requires test files exist; reviewers should verify those tests actually exercise declared invariants, not just call the happy path.

### Rationale
Happy-path-only tests create false confidence. Without a hard gate tying tests to declared invariants, the AI consistently under-tests edge cases.

<!-- RULE END: ENF-POST-004 -->
---

<!-- RULE START: ENF-POST-005 -->
## Rule ENF-POST-005

**Domain**: enforcement
**Category**: CAT-CODE-AIENF-001
**Severity**: High
**Scope**: Entity
**Mandatory**: false

### Trigger
When the implementation contains threshold-based logic (item count, subtotal, quantity, date comparisons) and tests exist for that logic.

### Statement
For any threshold, tests must cover: exactly at the threshold (must NOT trigger), one unit above (must trigger), and well above (must trigger).

### Violation
```php
// Threshold: minimum 5 items for bulk discount
// Tests only cover "clearly above" and "clearly below":
testBulkDiscountWith3Items()  // below -- pass
testBulkDiscountWith10Items() // above -- pass
// Missing: exactly 5 (boundary) and exactly 6 (one above)
```

### Pass
```php
testBulkDiscountWith4Items()  // below threshold -- no discount
testBulkDiscountWith5Items()  // AT threshold -- no discount (boundary)
testBulkDiscountWith6Items()  // one above -- discount applied
testBulkDiscountWith20Items() // well above -- discount applied
```

### Enforcement
Code review of test files. Reviewers should verify boundary tests for threshold logic (at-threshold, one-above, well-above).

### Rationale
Off-by-one errors at boundaries are among the most common bugs in threshold-based logic.

Related rules: ENF-POST-004, TEST-EDGE-002.

<!-- RULE END: ENF-POST-005 -->
---

<!-- RULE START: ENF-POST-006 -->
## Rule ENF-POST-006

**Domain**: enforcement
**Category**: CAT-CODE-AIENF-001
**Severity**: High
**Scope**: Slice
**Mandatory**: true
**Mechanical_Enforcement_Path**: .claude/hooks/validate-handoff.sh
**Applicability_Scope**: write
**Trigger_Keywords**: handoff, handoffs

### Trigger
Post-generation verification, before a handoff file is finalized.

### Statement
A handoff must carry no unresolved "I cannot verify" items. Every claim is verified, explicitly flagged for human review, or removed before handoff -- an unverifiable assertion must never be passed downstream as if settled.

### Violation
```
.claude/handoffs/slice-3.json:
{ "findings": ["I cannot verify the migration ran"] }   <- unresolved, passed downstream
```

### Pass
```
{ "findings": ["migration 0042 applied (verified: SELECT confirms column exists)"],
  "needs_human_review": [] }
```

### Enforcement
.claude/hooks/validate-handoff.sh scans the handoff for unresolved "I cannot verify" strings and emits an ENF-POST-006 violation until each is resolved or flagged.

### Rationale
"I cannot verify" is honest in-flight, but a handoff is a commitment. Carrying an unverified claim forward launders a guess into an apparent fact for the next slice.

Related rules: ENF-GATE-006, ENF-OPS-001, ENF-PROC-VERIFY-001.

<!-- RULE END: ENF-POST-006 -->
---

<!-- RULE START: ENF-POST-007 -->
## Rule ENF-POST-007

**Domain**: enforcement
**Category**: CAT-CODE-AIENF-001
**Severity**: Critical
**Scope**: Slice
**Mandatory**: true
**Mechanical_Enforcement_Path**: bin/run-analysis.sh (PHPStan level 8)
**Applicability_Scope**: write
**Trigger_Keywords**: PHPStan, static analysis, phpcs, mypy

### Trigger
After generating code, before marking a slice as complete.

### Statement
Generated code must be validated by static analysis tools. The AI's own reasoning is necessary but not sufficient. PHPStan at level 8 is the minimum for PHP.

### Violation
```
plan.md contains:
"## Pending tasks
- ENF-POST-007: Static analysis -- to be run post-deployment"
// Static analysis deferred -- NEVER acceptable.
```

### Pass
```
"Static analysis results:
PHPStan level 8: 0 errors
PHPCS Magento Coding Standard: 0 errors
All files validated."
```

### Enforcement
bin/run-analysis.sh runs PHPStan level 8 on PHP files via the validate-file.sh PostToolUse hook. validate-rules.sh records pass/fail to the session cache. Self-enforced halt on errors.

### Rationale
Static analysis tools are an independent verifier with no reasoning bias. PHPStan catches entire categories of bugs that the AI consistently misses because it "knows what it meant."

<!-- RULE END: ENF-POST-007 -->
---

<!-- RULE START: ENF-PRE-001 -->
## Rule ENF-PRE-001

**Domain**: enforcement
**Category**: CAT-CODE-AIENF-001
**Severity**: Critical
**Scope**: Component
**Mandatory**: false

### Trigger
When the task involves writing a plugin, observer, or event listener in Magento 2 or any framework with context-dependent dispatch.

### Statement
Before writing any plugin, observer, or event listener, the AI must produce a written call-path declaration answering: what is the entry point per execution context, does the same class handle all contexts, will the plugin intercept all required contexts, and which contexts are missed.

### Violation
```
AI output:
"I'll create an after plugin on CartRepositoryInterface::save() to log quote saves."
// No execution context analysis. Does this cover REST? GraphQL? Admin? CLI?
// No mention of which concrete classes implement the interface.
```

### Pass
```
AI output:
"Call-path declaration:
- Frontend (session): QuoteRepository::save() -- plugin intercepts ✓
- REST (POST /V1/carts): QuoteRepository::save() -- plugin intercepts ✓
- GraphQL (setPaymentMethodOnCart): QuoteRepository::save() -- plugin intercepts ✓
- Admin: AdminQuoteRepository::save() -- DIFFERENT class, plugin does NOT intercept ✗
- CLI: Not applicable -- no CLI quote save path
Gap: Admin quote saves are not covered. Acceptable because requirement is customer-facing only."
```

### Enforcement
Self-enforced via design review. When writing a Magento plugin/observer/event listener, reviewers should verify the AI considered each execution context (REST, GraphQL, admin, CLI) the dispatch will reach.

### Rationale
Plugins and observers that appear correct in one context often fail silently in others. A written call-path declaration forces the AI to reason about coverage before committing to an implementation.

Related rules: ENF-PRE-003, ENF-PRE-004, FW-M2-004.

<!-- RULE END: ENF-PRE-001 -->
---

<!-- RULE START: ENF-PRE-002 -->
## Rule ENF-PRE-002

**Domain**: enforcement
**Category**: CAT-CODE-AIENF-001
**Severity**: Critical
**Scope**: Component
**Mandatory**: false

### Trigger
When writing any validation method that determines whether a domain entity is legitimate, eligible, or active.

### Statement
Before writing validation logic, the AI must declare: what makes the entity legitimate at the domain level, whether legitimacy is structural (format) or persistence-based (exists in DB), and if persistence-based, which repository or service contract verifies existence.

### Violation
```
AI output:
"Here's the validation method:"
public function isValid(string $couponCode): bool {
    return str_starts_with($couponCode, 'PROMO_');
}
// No invariant declaration. Is format sufficient? Or must the coupon exist in DB?
```

### Pass
```
AI output:
"Domain invariant declaration:
Coupon legitimacy is persistence-based -- a valid coupon must exist in the sales_rule_coupon
table AND its parent rule must be active. Format alone (prefix, length) is insufficient.
Repository: CouponRepositoryInterface::getByCode() + RuleRepositoryInterface::getById().
Boundary: coupon exists but rule is inactive → invalid."
```

### Enforcement
Self-enforced via design review. Reviewers should verify validation methods declare whether legitimacy is format-based or persistence-based, and if persistence-based, which repository contract verifies existence.

### Rationale
Validation logic that infers legitimacy from format alone (string matching, prefix checking) instead of persistence verification is a recurring source of false positives and missed edge cases.

<!-- RULE END: ENF-PRE-002 -->
---

<!-- RULE START: ENF-PRE-003 -->
## Rule ENF-PRE-003

**Domain**: enforcement
**Category**: CAT-CODE-AIENF-001
**Severity**: Critical
**Scope**: Entity
**Mandatory**: false

### Trigger
When writing a plugin declaration (`<plugin>` or `<type>` with plugin in `di.xml`).

### Statement
Before writing any plugin declaration, the AI must justify: why this specific class (not the interface, not a parent), why this hook type (before/around/after), what state is available at this execution point, and whether the logic depends on data only reliable after a specific side effect.

### Violation
```
AI output:
"I'll add an around plugin on ShippingInformationManagement::saveAddressInformation
to check the discount amount."
// Why around instead of after? What state is available inside around?
// Does the discount depend on collectTotals running first?
```

### Pass
```
AI output:
"Seam justification:
- Target: ShippingInformationManagement (concrete) -- interface would intercept internal calls
- Hook: after -- we need post-collectTotals state. Using before would read stale totals (FW-M2-003).
  Using around is unnecessary since we don't need to modify the return value or prevent execution.
- State available after proceed(): quote is persisted, collectTotals has run, shipping rates computed.
- Timing dependency: discount amount depends on collectTotals. Confirmed: saveAddressInformation
  calls collectTotals before returning."
```

### Enforcement
Self-enforced via design review. Plugin declarations should justify class choice (interface vs concrete vs parent), hook type (before/around/after), and state availability at the chosen seam.

### Rationale
Incorrect plugin seam selection causes silent failures that are extremely difficult to diagnose. Explicit justification prevents defaulting to the most obvious interception point without verifying it is correct.

<!-- RULE END: ENF-PRE-003 -->
---

<!-- RULE START: ENF-PRE-004 -->
## Rule ENF-PRE-004

**Domain**: enforcement
**Category**: CAT-CODE-AIENF-001
**Severity**: Critical
**Scope**: Entity
**Mandatory**: false

### Trigger
When injecting any class as a constructor dependency into a class that is reachable via REST, GraphQL, or CLI -- especially if the dependency assumes UI context (session, message manager, layout).

### Statement
Before injecting any dependency, verify it is safe in all execution contexts where the class will be invoked. MessageManager, session, or UI-dependent classes injected into service-layer classes are violations unless explicitly justified.

### Violation
```php
// Service used by REST endpoints -- MessageManager requires session context
class OrderService
{
    public function __construct(
        private readonly OrderRepositoryInterface $orderRepository,
        private readonly ManagerInterface $messageManager // UNSAFE in REST/GraphQL
    ) {}
}
```

### Pass
```php
// All deps are API-safe
class OrderService
{
    public function __construct(
        private readonly OrderRepositoryInterface $orderRepository,
        private readonly LoggerInterface $logger // Safe in all contexts
    ) {}
}
// API safety check: OrderRepositoryInterface (API-safe), LoggerInterface (API-safe).
// No session/UI deps.
```

### Enforcement
Self-enforced via code review. Static analysis (custom PHPStan rule) can flag MessageManager/session/layout dependencies in service-layer classes.

### Rationale
Dependencies that assume UI context cause fatal errors or undefined behavior in headless execution contexts (REST, GraphQL, CLI). This is a common source of production incidents.

Related rules: ENF-PRE-001.

<!-- RULE END: ENF-PRE-004 -->
---

<!-- RULE START: ENF-TEST-001 -->
## Rule ENF-TEST-001

**Domain**: enforcement
**Category**: CAT-CODE-AIENF-001
**Severity**: Critical
**Scope**: Slice
**Mandatory**: true
**Mechanical_Enforcement_Path**: .claude/hooks/writ-run-pending-tests.sh

### Trigger
At session Stop, when test files written or modified during the session have not been run to a passing result.

### Statement
Tests written in a session must actually pass before the work is claimed complete. Pending or failing tests block completion: a written-but-unrun test is not evidence, and a failing test is a defect, not a footnote.

### Violation
```
"Implemented the feature and added tests."   <- tests never executed, or executed and failing
```

### Pass
```
"pytest tests/test_feature.py: 7 passed in 0.4s"   <- the session's tests run green before completion.
```

### Enforcement
.claude/hooks/writ-run-pending-tests.sh runs the session's pending tests at Stop and emits an ENF-TEST-001 violation summary on any failure.

### Rationale
A test that was written but never run is a claim, not a check. ENF-PROC-VERIFY-001 forbids completion claims without fresh evidence; this is its mechanical counterpart for session-authored tests.

<!-- RULE END: ENF-TEST-001 -->
