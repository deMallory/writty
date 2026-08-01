<!-- RULE START: ENF-OPS-001 -->
## Rule ENF-OPS-001

**Domain**: Operations
**Severity**: Critical
**Scope**: Component
**Mandatory**: false

### Trigger
When the AI makes any claim about performance, throughput, scalability, or reliability in design docs, code comments, or plan.md (e.g., "handles 1000 reservations/minute", "scales horizontally", "resilient to failures").

### Statement
Every operational claim must include supporting evidence for each assertion. A claim without evidence must be downgraded to "untested estimate" or removed entirely.

### Violation
```
## Performance
Throughput: 1000 reservations/minute
The system is resilient to failures and scales horizontally.
```

### Pass
```
## Performance
Throughput: ~1000 records/minute (estimated)
Evidence:
- Batch INSERT ON DUPLICATE KEY UPDATE: 1 SQL statement per batch (not per item)
- Indexes: btree on (item_id, status) -- used by ON DUPLICATE KEY
- Complexity: O(n) where n = items per batch (typically 1-20)
- Retry: 3 attempts with 30s TTL, then dead-letter queue
- Consumer: maxMessages=1000, single consumer instance, AMQP connection
- Unproven: actual throughput requires load testing against production-like data volume
```

### Enforcement
Self-enforced via design review. Operational claims should be flagged in code review and matched against test or benchmark evidence. Static analysis cannot verify performance claims; reviewers must.

### Rationale
Performance claims create expectations that influence architecture decisions, capacity planning, and SLA commitments. Unsubstantiated claims are worse than no claims -- they create false confidence that leads to production incidents when actual load exceeds imagined capacity.

<!-- RULE END: ENF-OPS-001 -->
---

<!-- RULE START: ENF-OPS-002 -->
## Rule ENF-OPS-002

**Domain**: Operations
**Severity**: High
**Scope**: Component
**Mandatory**: false

### Trigger
When implementing any feature that uses message queues (publishing messages, consuming messages, or configuring queue infrastructure).

### Statement
Queue-based features must declare complete infrastructure (primary queue, DLQ, retry policy, consumer config, monitoring) AND complete consumer behavior guarantees (idempotency, duplicate handling, retry failure escalation).

### Violation
```xml
<!-- Primary queue only -- no DLQ, no retry policy -->
<consumer name="vendor.module.consumer"
          queue="vendor.module.queue"
          handler="Vendor\Module\Model\Consumer::process"
          connection="amqp"/>
```
```php
// Consumer with no idempotency guard -- duplicate messages cause double processing
public function process(MessageInterface $message): void
{
    $this->inventoryService->deduct($message->getSku(), $message->getQty());
}
```

### Pass
```xml
<!-- Complete: primary queue + DLQ + retry + consumer config -->
<exchange name="vendor.module.exchange" type="topic" connection="amqp">
    <binding id="vendor.module.binding" topic="vendor.module.process"
             destinationType="queue" destination="vendor.module.queue">
        <arguments>
            <argument name="x-dead-letter-exchange" xsi:type="string">vendor.module.dlx</argument>
            <argument name="x-delivery-limit" xsi:type="number">3</argument>
        </arguments>
    </binding>
</exchange>
<exchange name="vendor.module.dlx" type="topic" connection="amqp">
    <binding id="vendor.module.dlq.binding" topic="vendor.module.process"
             destinationType="queue" destination="vendor.module.dlq"/>
</exchange>
```
```php
// Consumer with idempotency guard
public function process(MessageInterface $message): void
{
    $affected = $this->connection->insertOnDuplicate(
        $this->resource->getTableName('vendor_processing_log'),
        ['message_id' => $message->getId(), 'status' => 'processing'],
        [] // no update on duplicate -- silently skips re-delivery
    );
    if ($affected === 0) {
        $this->logger->info('Duplicate message skipped', ['id' => $message->getId()]);
        return;
    }
    $this->inventoryService->deduct($message->getSku(), $message->getQty());
}
```

### Enforcement
Self-enforced via design review. Queue infrastructure (DLQ, retry policy, consumer config, idempotency guard) should be verified during code review for every queue-using feature. Framework guidance: see bible/frameworks/magento/runtime-constraints.md for Magento 2 queue patterns.

### Rationale
In production, queue consumers crash, connections drop, and messages get redelivered. Without a DLQ, failed messages are retried indefinitely or silently dropped. Complete queue infrastructure is the minimum viable configuration for any production queue.

<!-- RULE END: ENF-OPS-002 -->
