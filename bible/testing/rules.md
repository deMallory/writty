<!-- RULE START: TEST-ASSERT-001 -->
## Rule TEST-ASSERT-001

**Domain**: testing
**Severity**: High
**Scope**: Component
**Mandatory**: false

### Trigger
When writing a test function.

### Statement
Every test has at least one assertion. Tests that exercise code without asserting an outcome are smoke tests at best and false-positive guarantees at worst.

### Violation
```python
def test_create_order():
    create_order(payload)  # no assert
```

### Pass
```python
def test_create_order():
    order = create_order(payload)
    assert order.id is not None
    assert order.status == 'pending'
```

### Enforcement
Linter rule (pytest-style assertion check; pylint custom rule).

### Rationale
An assertion-free test silently passes regardless of what the code does. The bug it claims to cover is invisible.

<!-- RULE END: TEST-ASSERT-001 -->
---

<!-- RULE START: TEST-ASSERT-002 -->
## Rule TEST-ASSERT-002

**Domain**: testing
**Severity**: Medium
**Scope**: Component
**Mandatory**: false

### Trigger
When writing test assertions.

### Statement
Assertions are specific. `assertEqual(actual, 5)` beats `assertTrue(actual == 5)`; `assertGreater(x, y)` beats `assertTrue(x > y)`. Specific assertions produce specific failure messages.

### Violation
```python
assert result == expected, 'failed'
```

### Pass
```python
assert result == expected
# pytest auto-diffs the values on failure; specific matchers (.contains, .matches) give richer messages.
```

### Enforcement
Code review.

### Rationale
Specific assertions print diffs on failure: actual vs expected. Boolean assertions print only 'False is not True', which says nothing.

<!-- RULE END: TEST-ASSERT-002 -->
---

<!-- RULE START: TEST-CI-001 -->
## Rule TEST-CI-001

**Domain**: testing
**Severity**: Medium
**Scope**: Component
**Mandatory**: false

### Trigger
When merging code.

### Statement
All tests pass in CI before merge. 'Known failing' tests are not left in the suite; flaky tests are quarantined with a tracked ticket and fixed or removed, not silently skipped.

### Violation
```
# 3 tests marked @pytest.mark.skip('flaky') with no ticket reference.
```

### Pass
```
# 3 tests removed and tracked as PR-1234 to repair or replace.
# Skips that remain reference active tickets and have an owner.
```

### Enforcement
CI gate. Code review.

### Rationale
A green-with-skips suite is a yellow signal that gets ignored. Either the test is meaningful (fix it) or it is not (remove it).

<!-- RULE END: TEST-CI-001 -->
---

<!-- RULE START: TEST-COVERAGE-001 -->
## Rule TEST-COVERAGE-001

**Domain**: testing
**Severity**: Medium
**Scope**: Component
**Mandatory**: false

### Trigger
When measuring test coverage.

### Statement
Critical business logic paths have at least 80% branch coverage. Coverage targets apply where the code's correctness matters (billing, auth, data integrity); UI and trivial accessors are exempted.

### Violation
```
# pricing module: 23% line coverage; no branch coverage tracking.
```

### Pass
```
# pricing module: 92% line coverage, 87% branch coverage.
# Coverage report is a CI artifact; threshold is enforced.
```

### Enforcement
Coverage tool (pytest-cov, jest --coverage, istanbul, JaCoCo) with CI gate.

### Rationale
Coverage targets create a baseline that prevents tests from being silently abandoned. 80% branch is enough to catch most regression; chasing 100% wastes effort on trivial code.

<!-- RULE END: TEST-COVERAGE-001 -->
---

<!-- RULE START: TEST-EDGE-001 -->
## Rule TEST-EDGE-001

**Domain**: testing
**Severity**: High
**Scope**: Component
**Mandatory**: false

### Trigger
When testing a public function.

### Statement
Error paths are tested alongside the happy path: invalid input, missing data, permission denied, timeout, downstream failure. The test suite proves the code handles failure as well as success.

### Violation
```python
def test_charge_card_success(): ...
# No test for declined-card, network-failure, or invalid-amount.
```

### Pass
```python
def test_charge_card_success(): ...
def test_charge_card_raises_on_decline(): ...
def test_charge_card_retries_on_transient_network_error(): ...
def test_charge_card_rejects_negative_amount(): ...
```

### Enforcement
Code review. Coverage tools that report branch coverage.

### Rationale
Happy-path-only test suites prove the code works when nothing goes wrong, which is the easiest case. Error paths are where most production bugs live.

<!-- RULE END: TEST-EDGE-001 -->
---

<!-- RULE START: TEST-EDGE-002 -->
## Rule TEST-EDGE-002

**Domain**: testing
**Severity**: Medium
**Scope**: Component
**Mandatory**: false

### Trigger
When testing a function that operates on collections, numeric values, or string inputs.

### Statement
Boundary values are tested: empty collection, zero, one, max int, max length, empty string, None/null. Off-by-one bugs and overflow bugs live at the boundaries.

### Violation
```python
def test_sum_items():
    assert sum_items([1, 2, 3]) == 6
# No empty-list, no overflow case.
```

### Pass
```python
def test_sum_items_empty(): assert sum_items([]) == 0
def test_sum_items_single(): assert sum_items([5]) == 5
def test_sum_items_large(): assert sum_items([10**9] * 100) == 10**11
```

### Enforcement
Code review.

### Rationale
Boundary bugs are the canonical source of off-by-one errors and overflow surprises. Explicit boundary tests are the structural defense.

<!-- RULE END: TEST-EDGE-002 -->
---

<!-- RULE START: TEST-EDGE-003 -->
## Rule TEST-EDGE-003

**Domain**: testing
**Severity**: Medium
**Scope**: Component
**Mandatory**: false

### Trigger
When implementing concurrent code (locks, async coroutines, shared state, queues).

### Statement
Concurrent access paths are tested where applicable: race conditions, lock contention, deadlocks. The test suite includes scenarios that exercise multiple parallel callers.

### Violation
```python
# concurrent_writes(file) tested only single-caller.
```

### Pass
```python
async def test_concurrent_writes_serialize():
    await asyncio.gather(*[concurrent_writes(file, i) for i in range(50)])
    assert correctly_ordered(file.read())
```

### Enforcement
Code review.

### Rationale
Concurrency bugs only surface under contention. A single-threaded test of concurrent code proves nothing about correctness under load.

<!-- RULE END: TEST-EDGE-003 -->
---

<!-- RULE START: TEST-EXIST-001 -->
## Rule TEST-EXIST-001

**Domain**: testing
**Severity**: High
**Scope**: Component
**Mandatory**: false

### Trigger
When adding or modifying a public function, method, or class.

### Statement
Every public function or method has at least one test. New public APIs are not committed without a test covering at least the happy path.

### Violation
```python
# orders.py adds a new public method:
def cancel_order(order_id): ...
# No test in tests/test_orders.py.
```

### Pass
```python
# tests/test_orders.py:
def test_cancel_order_marks_status():
    order = make_order(status='paid')
    cancel_order(order.id)
    assert reload(order).status == 'cancelled'
```

### Enforcement
Code review. Coverage tools report public-function coverage.

### Rationale
Untested public APIs are unverified APIs: every caller is the first to find the bug. The test is the executable contract.

<!-- RULE END: TEST-EXIST-001 -->
---

<!-- RULE START: TEST-EXIST-002 -->
## Rule TEST-EXIST-002

**Domain**: testing
**Severity**: High
**Scope**: Component
**Mandatory**: false

### Trigger
When adding or modifying an API endpoint (REST, GraphQL, RPC).

### Statement
Every API endpoint has at least one integration test that exercises it end-to-end (request -> response). Unit tests on the handler function are not a substitute.

### Violation
```python
# /api/orders POST added; only the service function is unit-tested.
```

### Pass
```python
def test_create_order_endpoint(client):
    resp = client.post('/api/orders', json={...})
    assert resp.status_code == 201
    assert resp.json['id']
```

### Enforcement
Code review.

### Rationale
Integration tests catch the bugs that unit tests cannot: middleware ordering, request parsing, response shape, status codes, content negotiation.

<!-- RULE END: TEST-EXIST-002 -->
---

<!-- RULE START: TEST-FIXTURE-001 -->
## Rule TEST-FIXTURE-001

**Domain**: testing
**Severity**: Medium
**Scope**: Component
**Mandatory**: false

### Trigger
When writing test setup code.

### Statement
Test fixtures or factories are used for object setup. Constructing the same domain object inline across many tests is a violation; factory functions (factory_boy, FactoryBot, pytest fixtures) own the construction logic.

### Violation
```python
def test_a():
    user = User(name='Alice', email='alice@example.com', age=30, ...)  # 20 fields
    ...
def test_b():
    user = User(name='Bob', email='bob@example.com', age=25, ...)
```

### Pass
```python
@pytest.fixture
def user_factory():
    def make(**overrides):
        defaults = {'name': 'Alice', 'email': 'alice@example.com', ...}
        return User(**{**defaults, **overrides})
    return make

def test_a(user_factory):
    user = user_factory()
def test_b(user_factory):
    user = user_factory(name='Bob')
```

### Enforcement
Code review.

### Rationale
Inline-constructed objects drift across tests; one new required field updates twenty tests. Factories centralize the construction.

<!-- RULE END: TEST-FIXTURE-001 -->
---

<!-- RULE START: TEST-FIXTURE-002 -->
## Rule TEST-FIXTURE-002

**Domain**: testing
**Severity**: Medium
**Scope**: Component
**Mandatory**: false

### Trigger
When writing test setup code.

### Statement
Fixtures are minimal: each test sets up only what it actually needs. Kitchen-sink setup that creates 10 related objects when the test only uses 2 is a violation. The test reads as 'given these inputs, expect this outcome' without noise.

### Violation
```python
def test_cancel_order():
    customer = create_customer()
    addresses = [create_address(customer) for _ in range(3)]
    payment_methods = [create_payment_method(customer) for _ in range(2)]
    order = create_order(customer)
    cancel_order(order.id)
    assert order.status == 'cancelled'
```

### Pass
```python
def test_cancel_order():
    order = create_order(status='pending')
    cancel_order(order.id)
    assert reload(order).status == 'cancelled'
```

### Enforcement
Code review.

### Rationale
Bloated setup obscures intent and slows the suite. Minimal fixtures keep the test legible and fast.

<!-- RULE END: TEST-FIXTURE-002 -->
---

<!-- RULE START: TEST-ISOLATE-001 -->
## Rule TEST-ISOLATE-001

**Domain**: testing
**Severity**: High
**Scope**: Component
**Mandatory**: false

### Trigger
When writing tests that share modules, fixtures, or process-level state.

### Statement
Tests do not depend on execution order. State is set up per-test and torn down per-test. Cross-test mutable state (module globals modified by one test, read by another) is a violation.

### Violation
```python
CACHE = {}
def test_first_writes_to_cache():
    CACHE['key'] = 'value'
def test_second_reads_cache():
    assert CACHE['key'] == 'value'  # depends on test order
```

### Pass
```python
def test_writes_and_reads_cache():
    cache = {}
    cache['key'] = 'value'
    assert cache['key'] == 'value'
```

### Enforcement
Test framework config (pytest's randomize order plugin catches this). Code review.

### Rationale
Order-dependent tests pass in CI and fail in parallel runs (or vice versa). The flake is structural and the fix is per-test isolation.

<!-- RULE END: TEST-ISOLATE-001 -->
---

<!-- RULE START: TEST-ISOLATE-002 -->
## Rule TEST-ISOLATE-002

**Domain**: testing
**Severity**: High
**Scope**: Component
**Mandatory**: false

### Trigger
When writing tests that exercise code with external dependencies (HTTP APIs, third-party services, payment gateways).

### Statement
Tests do not make real network calls. External dependencies are mocked, stubbed, or replaced with a local fake (VCR, MSW, responses, requests-mock). Tests do not hit a real Stripe sandbox, Slack webhook, or third-party API.

### Violation
```python
def test_charge_card():
    response = stripe.Charge.create(amount=1000)  # real API call
    assert response.status == 'succeeded'
```

### Pass
```python
def test_charge_card(stripe_mock):
    stripe_mock.expect_charge(amount=1000).returns(succeeded_response)
    result = payment_service.charge(amount=1000)
    assert result.status == 'succeeded'
```

### Enforcement
Code review. Network-blocking pytest fixtures (pytest-socket).

### Rationale
Tests that hit real services are slow, flaky, and side-effect-laden. Mocking is the structural defense.

<!-- RULE END: TEST-ISOLATE-002 -->
---

<!-- RULE START: TEST-ISOLATE-003 -->
## Rule TEST-ISOLATE-003

**Domain**: testing
**Severity**: Medium
**Scope**: Component
**Mandatory**: false

### Trigger
When writing tests that read or write a database.

### Statement
Test database state is reset between tests: transaction rollback after each test, fixture reload, or a fresh ephemeral database. Tests do not leak rows that affect other tests.

### Violation
```python
def test_create_user_first():
    User.create(email='alice@example.com')
def test_create_user_again():
    User.create(email='alice@example.com')  # IntegrityError from prior test
```

### Pass
```python
@pytest.fixture
def db():
    with engine.begin() as conn:
        yield conn
        conn.rollback()
```

### Enforcement
Test framework config. Pytest fixtures with transactional scope.

### Rationale
Leaked state between tests is the canonical source of order-dependent flakiness. Per-test isolation removes the entire class of bug.

<!-- RULE END: TEST-ISOLATE-003 -->
---

<!-- RULE START: TEST-MOCK-001 -->
## Rule TEST-MOCK-001

**Domain**: testing
**Severity**: Medium
**Scope**: Component
**Mandatory**: false

### Trigger
When using mocks in tests.

### Statement
Mocks verify behavior: that the mock was called with specific arguments, the right number of times, in the right order. Mocks that exist purely to suppress a dependency without assertions on the call are weak tests.

### Violation
```python
def test_send_welcome():
    send_welcome(user)
    # mailer is mocked but never inspected
```

### Pass
```python
def test_send_welcome(mailer_mock):
    send_welcome(user)
    mailer_mock.send.assert_called_once_with(
        to=user.email, template='welcome', context={'name': user.name},
    )
```

### Enforcement
Code review.

### Rationale
A mock without behavior assertions only proves 'no exception thrown'. Behavior assertions prove the integration with the mocked collaborator.

<!-- RULE END: TEST-MOCK-001 -->
---

<!-- RULE START: TEST-MOCK-002 -->
## Rule TEST-MOCK-002

**Domain**: testing
**Severity**: Medium
**Scope**: Component
**Mandatory**: false

### Trigger
When stubbing return values for mocked dependencies.

### Statement
Mock return values match the actual API/service response shape. A mock that returns `{'ok': True}` when the real service returns `{'data': {...}, 'status': 'success'}` produces tests that pass while real integration fails.

### Violation
```python
stripe_mock.charge.return_value = True
```

### Pass
```python
stripe_mock.charge.return_value = StripeChargeResponse(
    id='ch_test', status='succeeded', amount=1000, currency='usd',
    customer='cus_test', metadata={},
)
```

### Enforcement
Code review. Contract tests verify mock shapes against real responses.

### Rationale
Drift between mock and reality lets tests pass while production breaks. Realistic mocks keep the gap closed.

<!-- RULE END: TEST-MOCK-002 -->
---

<!-- RULE START: TEST-NAME-001 -->
## Rule TEST-NAME-001

**Domain**: testing
**Severity**: Medium
**Scope**: Component
**Mandatory**: false

### Trigger
When naming a test function.

### Statement
Test names describe the scenario and the expected outcome. `test_method_name` is insufficient; `test_method_name_returns_X_when_Y` or BDD-style `should_X_when_Y` is the structure.

### Violation
```python
def test_cancel(): ...
def test_cancel_2(): ...
```

### Pass
```python
def test_cancel_marks_status_cancelled_for_paid_orders(): ...
def test_cancel_raises_when_order_already_shipped(): ...
```

### Enforcement
Code review.

### Rationale
Failing test names are read in CI output, in incident timelines, in stack traces. Descriptive names diagnose the failure without opening the test file.

<!-- RULE END: TEST-NAME-001 -->
---

<!-- RULE START: TEST-PERF-001 -->
## Rule TEST-PERF-001

**Domain**: testing
**Severity**: Low
**Scope**: Component
**Mandatory**: false

### Trigger
When implementing performance-sensitive code (hot paths, query pipelines, retrieval, ranking, real-time loops).

### Statement
Performance-sensitive paths have benchmark tests with a documented baseline. The baseline is checked in CI (or nightly) and regressions exceeding a threshold fail the build.

### Violation
```
# Latency-critical retrieval pipeline has no perf assertion.
```

### Pass
```python
@pytest.mark.benchmark
def test_query_latency(benchmark, pipeline):
    result = benchmark(pipeline.query, 'sql injection')
    assert benchmark.stats.median < 0.050  # 50ms baseline
```

### Enforcement
Benchmark framework (pytest-benchmark, criterion, JMH).

### Rationale
Performance regressions slip in silently as features land. Benchmarks turn 'feels slow' into a measurable, gateable signal.

<!-- RULE END: TEST-PERF-001 -->
---

<!-- RULE START: TEST-REGRESSION-001 -->
## Rule TEST-REGRESSION-001

**Domain**: testing
**Severity**: High
**Scope**: Component
**Mandatory**: false

### Trigger
When fixing a bug.

### Statement
Every bug fix is accompanied by a regression test that reproduces the bug. The test fails before the fix and passes after. The bug ticket / commit message references the test.

### Violation
```
# Commit: 'fix: null pointer in /api/orders'
# No accompanying test.
```

### Pass
```
# Commit:
# fix: null pointer in /api/orders when shipping address missing
# test_create_order_handles_missing_shipping_address verifies fix
```

### Enforcement
Code review. Bug-tracker template requires a 'test added' field.

### Rationale
Bug fixes without regression tests guarantee the bug returns. The test is the structural defense against re-introduction.

<!-- RULE END: TEST-REGRESSION-001 -->
---

<!-- RULE START: TEST-SNAPSHOT-001 -->
## Rule TEST-SNAPSHOT-001

**Domain**: testing
**Severity**: Low
**Scope**: Component
**Mandatory**: false

### Trigger
When using snapshot testing (Jest snapshots, React Testing Library snapshots, Storybook visual snapshots).

### Statement
Snapshot updates are explicitly reviewed; blind snapshot regeneration (-u flag in commits without review) is forbidden. The PR description explains why the snapshot changed.

### Violation
```
# CI runs `jest -u` automatically and commits.
```

### Pass
```
# Developer runs jest -u locally, inspects diff, includes it in the PR.
# Reviewer specifically reviews the snapshot diff.
```

### Enforcement
Pre-commit hook. PR template requires snapshot diff acknowledgment.

### Rationale
Blind snapshot updates erode the value of the test: it becomes a record of what the code does, not a check that it does the right thing.

<!-- RULE END: TEST-SNAPSHOT-001 -->
