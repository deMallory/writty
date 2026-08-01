<!-- RULE START: ENF-SYS-002 -->
## Rule ENF-SYS-002

**Domain**: System Dynamics
**Severity**: Critical
**Scope**: Entity
**Mandatory**: false

### Trigger
When writing validation, check, or decision logic that depends on a fact established by a prior system event (e.g., "is this product salable?", "has this order been paid?", "is this coupon valid?") -- specifically when the code runs AFTER the authoritative event.

### Statement
For any decision depending on a prior state transition, declare: the authoritative decision point, the temporal position of the current check, whether re-evaluation is valid, and the staleness risk. Re-checking a fact that was already authoritatively decided by a prior event is a violation if re-evaluation could contradict the original decision.

### Violation
```php
// Post-order-placement observer RE-CHECKS product availability
// Order placement already validated this through MSI
public function execute(Observer $observer): void
{
    $order = $observer->getEvent()->getOrder();
    foreach ($order->getItems() as $item) {
        $stock = $this->stockRegistry->getStockStatusBySku($item->getSku());
        if (!$stock->getIsInStock()) {
            $this->skipProcessing($item); // skips valid items!
        }
    }
}
```

### Pass
```php
// Post-order-placement observer TRUSTS the placement decision
public function execute(Observer $observer): void
{
    $order = $observer->getEvent()->getOrder();
    // Temporal truth: salability was decided at order placement.
    // Re-evaluation invalid -- stock may have changed, but this order was authorized.
    foreach ($order->getItems() as $item) {
        $this->processItem($item);
    }
}
```

### Enforcement
Self-enforced via design review. Code review should flag any re-evaluation of facts established by upstream authoritative events (post-order salability checks, post-payment authorization checks, etc.).

### Rationale
"Respect the upstream authority" means "trust the decision," not "re-evaluate it." Temporal truth source confusion is a recurring pattern where the AI adds defensive checks that actually introduce logic flaws -- re-checking availability after placement can reject valid orders.

<!-- RULE END: ENF-SYS-002 -->
---

<!-- RULE START: ENF-SYS-003 -->
## Rule ENF-SYS-003

**Domain**: System Dynamics
**Severity**: Critical
**Scope**: Entity
**Mandatory**: false

### Trigger
When writing code that changes a status/state column in a database (e.g., `reserved` to `released`, `pending` to `processing`, `active` to `expired`) where more than one actor could attempt the same transition.

### Statement
Every state transition must declare a state machine (legal states and transitions), transition guards, an atomicity strategy, and contention handling. Bare read-then-write without a concurrency guard is always a violation.

### Violation
```php
// Read-then-write with no concurrency guard
$reservation = $this->reservationRepository->getById($id);
if ($reservation->getStatus() === 'reserved') {
    $reservation->setStatus('released');
    $this->reservationRepository->save($reservation);
}
// Two consumers can both read 'reserved', both set 'released', both succeed
// Second save silently overwrites -- potential duplicate side effects
```

### Pass
```php
// Atomic CAS -- second actor gets affected_rows=0
$affected = $connection->update(
    $this->resource->getTableName('vendor_reservation'),
    ['status' => self::STATUS_RELEASED, 'released_at' => $now],
    ['entity_id = ?' => $id, 'status = ?' => self::STATUS_RESERVED]
);
if ($affected === 0) {
    throw new AlreadyReleasedException(
        __('Reservation %1 is no longer in reserved state.', $id)
    );
}
```

### Enforcement
Self-enforced via design review. Code review must verify that every state-transition write includes an atomicity guard: optimistic concurrency control (CAS in WHERE clause), advisory lock, or transaction with SELECT FOR UPDATE. Look for read-then-write patterns without a WHERE clause matching the prior state.

### Rationale
Naive read-then-write patterns are the #1 source of race conditions in queue-driven systems. Two consumers can both read the same status, both decide to transition, and both succeed -- causing duplicate side effects. The guard is not optional.

<!-- RULE END: ENF-SYS-003 -->
---

<!-- RULE START: ENF-SYS-005 -->
## Rule ENF-SYS-005

**Domain**: System Dynamics
**Severity**: Critical
**Scope**: Component
**Mandatory**: false

### Trigger
When the implementation claims concurrency safety, idempotency, or atomicity, and the only tests validating those claims use mocked database operations.

### Statement
For any feature involving concurrent actors, state transitions, or DB constraints, declare which behaviors cannot be proven with mocks and which require integration tests against a real database. Claiming production-readiness for concurrent/async features with only mocked tests is a violation.

### Violation
```php
// "Testing" a unique constraint with a mock -- proves nothing
public function testDuplicateMessageIsRejected(): void
{
    $this->connection->expects($this->once())
        ->method('insertOnDuplicate')
        ->willReturn(1);

    $result = $this->handler->process($message);
    $this->assertTrue($result); // mock always returns what you told it to
}
```

### Pass
```php
// Integration test with real DB -- proves the constraint actually works
public function testDuplicateMessageIsRejectedByDbConstraint(): void
{
    // First insert succeeds
    $this->handler->process($this->createMessage('msg-001', 'SKU-A'));

    // Second insert with same message_id is a no-op
    $this->handler->process($this->createMessage('msg-001', 'SKU-A'));

    // Verify only one record exists
    $count = $this->connection->fetchOne(
        "SELECT COUNT(*) FROM vendor_processing_log WHERE message_id = 'msg-001'"
    );
    $this->assertEquals(1, $count);
}
```

### Enforcement
Self-enforced via design review. Reviewers should verify that concurrency claims are backed by integration tests against a real database, not just mocked unit tests. ENF-SYS-003 (atomicity guards) and TEST-INT-001 (integration test discipline) are the related principles.

### Rationale
Unit tests with mocked repositories prove logic flow, not system behavior. A mocked `insertOnDuplicate` proves nothing about whether the actual DB unique constraint prevents duplicates. Integration tests are the only way to validate concurrency claims.

<!-- RULE END: ENF-SYS-005 -->
---

<!-- RULE START: ENF-SYS-006 -->
## Rule ENF-SYS-006

**Domain**: System Dynamics
**Severity**: Critical
**Scope**: Component
**Mandatory**: false

### Trigger
When implementing or reviewing a state machine declaration: every status constant must have at least one assignment (incoming transition) and at least one read (used by guards or exits), unless explicitly the initial or terminal state.

### Statement
Every declared state must have at least one incoming code path (except initial state), at least one outgoing code path (except terminal state), and at least one assignment in generated code. A constant with no assignment anywhere in the codebase is a dead declaration.

### Violation
```php
// State machine declares four states
private const STATUS_RESERVED = 'reserved';
private const STATUS_RELEASED = 'released';
private const STATUS_EXPIRED  = 'expired';  // DEAD -- nothing ever sets this
private const STATUS_FAILED   = 'failed';   // DEAD -- nothing ever sets this

// Only two transitions exist in code:
// reserved → released (in releaseReservation())
// Nothing transitions TO expired or failed
```

### Pass
```php
private const STATUS_RESERVED = 'reserved';
private const STATUS_RELEASED = 'released';
private const STATUS_EXPIRED  = 'expired';
private const STATUS_FAILED   = 'failed';

// All states have incoming transitions:
// → reserved: createReservation() sets STATUS_RESERVED
// → released: releaseReservation() sets STATUS_RELEASED WHERE status='reserved'
// → expired: expireStalReservations() cron sets STATUS_EXPIRED WHERE status='reserved' AND created_at < :ttl
// → failed: handleProcessingError() sets STATUS_FAILED WHERE status='reserved'
```

### Enforcement
Self-enforced via design review. Static analysis (grep for status constants assigned vs declared) can flag obvious dead-state cases. Reviewers should verify every declared state has at least one incoming code path.

### Rationale
STATUS_RELEASED in PartialCaptureInventory: constant declared, tests written, but nothing ever SET the status to released. Structurally present, functionally dead. This rule requires verifying not just that states are declared but that they are reachable.

<!-- RULE END: ENF-SYS-006 -->
