<!-- RULE START: TEST-INT-001 -->
## Rule TEST-INT-001

**Domain**: Testing
**Severity**: Medium
**Scope**: Component
**Mandatory**: false

### Trigger
When ENF-SYS-005 identifies behaviors that cannot be proven with mocks (DB unique constraints, transaction isolation, queue redelivery, actual multi-step state transitions).

### Statement
Integration tests must exist for every behavior declared as "unprovable by mocks" in the Tests must use a real database connection and verify actual constraint enforcement.

### Violation
```php
// "Testing" a unique constraint with a mock -- proves nothing
public function testDuplicateIsRejected(): void
{
    $this->connection->expects($this->once())
        ->method('insertOnDuplicate')
        ->willReturn(1);

    $this->handler->process($message);
    // Mock returns whatever you tell it -- no DB constraint verified
}
```

### Pass
```php
// Integration test with real DB -- proves the constraint actually works
public function testDuplicateMessageIsRejectedByUniqueConstraint(): void
{
    $this->handler->process($this->createMessage('msg-001', 'SKU-A'));
    $this->handler->process($this->createMessage('msg-001', 'SKU-A'));

    $count = $this->connection->fetchOne(
        "SELECT COUNT(*) FROM vendor_processing_log WHERE message_id = 'msg-001'"
    );
    $this->assertEquals(1, $count); // DB constraint prevents duplicate
}
```

### Enforcement
Self-enforced via design review. Reviewers should verify integration tests exist for concurrency claims. Related: ENF-SYS-005 (integration reality check), ENF-SYS-003 (atomicity guards).

### Rationale
Unit tests with mocked repositories prove logic flow, not system behavior. A mocked `insertOnDuplicate` proves nothing about whether the actual DB unique constraint prevents duplicates. Integration tests are the only way to validate concurrency claims.

<!-- RULE END: TEST-INT-001 -->
---

<!-- RULE START: TEST-ISO-001 -->
## Rule TEST-ISO-001

**Domain**: Testing
**Severity**: High
**Scope**: Entity
**Mandatory**: false

### Trigger
When writing a unit test that interacts with external state (database, filesystem, network, shared static variables) or depends on another test's execution.

### Statement
Each unit test must set up its own state via mocks/stubs, must not depend on execution order, and must produce the same result on every run. No shared mutable state between tests.

### Violation
```php
class OrderTest extends TestCase
{
    private static array $orders = [];

    public function testCreateOrder(): void
    {
        self::$orders[] = new Order(1);
        $this->assertCount(1, self::$orders);
    }

    public function testDeleteOrder(): void
    {
        array_pop(self::$orders); // depends on testCreateOrder running first
        $this->assertCount(0, self::$orders);
    }
}
```

### Pass
```php
class OrderTest extends TestCase
{
    public function testCreateOrder(): void
    {
        $repository = $this->createMock(OrderRepositoryInterface::class);
        $repository->method('getById')->willReturn($this->createOrder(1));
        $service = new OrderService($repository);

        $order = $service->get(1);
        $this->assertEquals(1, $order->getEntityId());
    }

    public function testDeleteOrder(): void
    {
        $repository = $this->createMock(OrderRepositoryInterface::class);
        $repository->method('delete')->willReturn(true);
        $service = new OrderService($repository);

        $this->assertTrue($service->delete(1));
    }
}
```

### Enforcement
Static analysis (ENF-POST-007).

### Rationale
Isolated tests are faster, more reliable, and pinpoint failures precisely. Tests that depend on shared state or execution order produce intermittent failures that erode confidence in the test suite.

<!-- RULE END: TEST-ISO-001 -->
---

<!-- RULE START: TEST-TDD-001 -->
## Rule TEST-TDD-001

**Domain**: Testing
**Severity**: High
**Scope**: Slice
**Mandatory**: false

### Trigger
When generating implementation code for a new class or modifying a public method signature.

### Statement
Test skeletons with specific assertions must exist and be approved before the implementation they test. Every public method must have at least one test covering its primary behavior.

### Violation
```
// Implementation written first, then tests added that just confirm what was built:
public function testRelease(): void
{
    $result = $this->handler->release($id);
    $this->assertTrue($result); // meaningless -- asserts nothing about behavior
}
```

### Pass
```php
// Test skeleton written and approved BEFORE release() is implemented:
public function testReleaseChangesStatusToReleased(): void
{
    $reservation = $this->createReservation(status: 'reserved');
    $this->handler->release($reservation->getId());

    $updated = $this->reservationRepository->getById($reservation->getId());
    $this->assertEquals('released', $updated->getStatus());
}

public function testReleaseOnAlreadyReleasedThrows(): void
{
    $reservation = $this->createReservation(status: 'released');
    $this->expectException(AlreadyReleasedException::class);
    $this->handler->release($reservation->getId());
}
```

### Enforcement
ENF-GATE-007 (test-first gate) -- test skeletons must be approved before implementation slice. ENF-POST-004 (tests must cover domain invariants).

### Rationale
Tests written after implementation become confirmation of what was built, not specification of what should be built. Test-first forces clear interface design before implementation details.

<!-- RULE END: TEST-TDD-001 -->
