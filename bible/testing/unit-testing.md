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
