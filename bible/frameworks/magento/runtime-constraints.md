<!-- RULE START: FW-M2-RT-001 -->
## Rule FW-M2-RT-001

**Domain**: Frameworks / Magento 2
**Severity**: Critical
**Scope**: Entity
**Mandatory**: false

### Trigger
When writing post-order-placement code (observer, consumer, cron) that checks product availability or stock status for an already-placed order.

### Statement
When MSI allows an order to be placed, salability has been authoritatively decided. Post-placement code must NOT re-evaluate salability. Processing all items from a placed order is always correct.

### Violation
```php
// Observer on sales_order_save_after RE-CHECKS availability
public function execute(Observer $observer): void
{
    $order = $observer->getEvent()->getOrder();
    foreach ($order->getItems() as $item) {
        $stockStatus = $this->stockRegistry->getStockStatusBySku($item->getSku());
        if (!$stockStatus->getIsInStock()) {
            $this->skipItem($item); // skips valid order items!
        }
    }
}
```

### Pass
```php
// Observer trusts the placement decision -- processes ALL items
public function execute(Observer $observer): void
{
    $order = $observer->getEvent()->getOrder();
    foreach ($order->getItems() as $item) {
        $this->processItem($item);
    }
}
```

### Enforcement
ENF-SYS-002 (temporal truth source declaration).

### Rationale
"Respect MSI" means "trust MSI's placement decision," not "re-evaluate MSI after the fact." Re-checking salability post-placement produces false negatives when stock levels change between placement and processing, causing valid orders to be silently skipped.

<!-- RULE END: FW-M2-RT-001 -->
---

<!-- RULE START: FW-M2-RT-002 -->
## Rule FW-M2-RT-002

**Domain**: Frameworks / Magento 2
**Severity**: Critical
**Scope**: Component
**Mandatory**: false

### Trigger
When writing code that reacts to or depends on Magento order state changes (observers on `sales_order_save_after`, `sales_order_place_after`, order processing consumers).

### Statement
Features that depend on order state must explicitly declare which states and transitions they handle and which they ignore. Silent assumptions about state transitions are a violation.

### Violation
```
// Phase A output -- no state handling declared:
"We observe sales_order_save_after and process the order."
// Which states? What happens on cancel? On hold? On partial refund?
```

### Pass
```
// Phase A output -- explicit state handling:
"Observer fires on sales_order_save_after.
Handles: new → processing (creates reservation).
Handles: processing → canceled (releases reservation).
Ignores: processing → complete (no reservation action needed).
Ignores: partial refund (state stays 'processing', no reservation change).
Ignores: holded (no reservation action -- hold is temporary)."
```

### Enforcement
ENF-SYS-003 (state transition atomicity).

### Rationale
Magento's order state machine has non-obvious behaviors. Explicit declaration prevents the AI from assuming a simplified state model that breaks on edge cases like partial refunds or custom states.

<!-- RULE END: FW-M2-RT-002 -->
---

<!-- RULE START: FW-M2-RT-003 -->
## Rule FW-M2-RT-003

**Domain**: Frameworks / Magento 2
**Severity**: High
**Scope**: Component
**Mandatory**: false

### Trigger
When a value classified as "deployment-variable policy" by ENF-SYS-004 is hardcoded in a Magento 2 module instead of being sourced from admin configuration.

### Statement
Store-specific policy values must be declared in `etc/adminhtml/system.xml`, defaulted in `etc/config.xml`, read via `ScopeConfigInterface` with proper scope, and encapsulated in a dedicated Config class.

### Violation
```php
// Hardcoded policy -- different stores cannot customize
private const SKIP_STATES = ['canceled', 'holded'];

public function shouldProcess(OrderInterface $order): bool
{
    return !in_array($order->getState(), self::SKIP_STATES, true);
}
```

### Pass
```php
// Policy read from scoped config via dedicated Config class
class ReservationConfig
{
    public function __construct(
        private readonly ScopeConfigInterface $scopeConfig
    ) {}

    public function getSkipStates(): array
    {
        $value = $this->scopeConfig->getValue(
            'custom_reservation/general/skip_states',
            ScopeInterface::SCOPE_STORE
        );
        return $value ? explode(',', $value) : [];
    }
}
```

### Enforcement
ENF-SYS-004 (policy vs mechanism).

### Rationale
Magento's multi-store architecture requires per-store configuration. `ScopeConfigInterface` with proper scope is the only mechanism that correctly handles default -> website -> store fallback. Inline reads without scope are unreliable in multi-website setups.

<!-- RULE END: FW-M2-RT-003 -->
---

<!-- RULE START: FW-M2-RT-004 -->
## Rule FW-M2-RT-004

**Domain**: Frameworks / Magento 2
**Severity**: Critical
**Scope**: Entity
**Mandatory**: false

### Trigger
When writing a REST endpoint (`webapi.xml`), GraphQL resolver, or admin controller in Magento 2.

### Statement
Every endpoint must use the framework-specific authorization mechanism for its type. REST uses `<resource>` in `webapi.xml`. GraphQL resolvers must check `$context->getUserType()` and verify ownership. Admin controllers must override `_isAllowed()`.

### Violation
```php
// GraphQL resolver with no auth check -- any caller gets any data
public function resolve($field, $context, $info, $value, $args): array
{
    return $this->orderRepository->getById($args['order_id'])->getData();
}
```

### Pass
```php
// GraphQL resolver with proper auth + ownership
public function resolve($field, $context, $info, $value, $args): array
{
    $userId = (int) $context->getUserId();
    $userType = $context->getUserType();

    if ($userType === UserContextInterface::USER_TYPE_ADMIN
        || $userType === UserContextInterface::USER_TYPE_INTEGRATION) {
        // Admin/integration: unrestricted
    } elseif (!$userId || $userType !== UserContextInterface::USER_TYPE_CUSTOMER) {
        throw new GraphQlAuthorizationException(__('Not authorized.'));
    } else {
        // Customer: verify ownership
        $order = $this->orderRepository->getById($args['order_id']);
        if ((int) $order->getCustomerId() !== $userId) {
            throw new GraphQlAuthorizationException(
                __('Not authorized for this resource.')
            );
        }
    }

    return $this->formatOrder(
        $this->orderRepository->getById($args['order_id'])
    );
}
```

### Enforcement
ENF-SEC-001 (access boundary declaration). ENF-GATE-007 test skeletons must include unauthorized + ownership violation + valid caller tests.

### Rationale
Magento has four distinct caller types (admin, customer, integration, guest), each with different authorization mechanisms. The framework does NOT apply authorization automatically for GraphQL -- resolvers must check explicitly.

<!-- RULE END: FW-M2-RT-004 -->
---

<!-- RULE START: FW-M2-RT-005 -->
## Rule FW-M2-RT-005

**Domain**: Frameworks / Magento 2
**Severity**: High
**Scope**: Component
**Mandatory**: false

### Trigger
When building a feature that uses Magento's message queue framework (any of: `communication.xml`, `queue_publisher.xml`, `queue_topology.xml`, `queue_consumer.xml`).

### Statement
Queue-based features must declare all four XML configuration files plus a DLQ exchange. Missing any one of the four files causes silent failures.

### Violation
```xml
<!-- Only primary queue -- no DLQ. Failed messages silently dropped. -->
<exchange name="vendor.module.exchange" type="topic" connection="amqp">
    <binding id="vendor.module.binding"
             topic="vendor.module.process"
             destinationType="queue"
             destination="vendor.module.queue"/>
</exchange>
```

### Pass
**1. `etc/communication.xml`** -- topic and schema:
```xml
<topic name="vendor.module.process"
       request="Vendor\Module\Api\Data\MessageInterface"/>
```

**2. `etc/queue_publisher.xml`** -- publisher binding:
```xml
<publisher topic="vendor.module.process">
    <connection name="amqp" exchange="vendor.module.exchange"/>
</publisher>
```

**3. `etc/queue_topology.xml`** -- exchange, bindings, DLQ:
```xml
<exchange name="vendor.module.dlx" type="topic" connection="amqp">
    <binding id="vendor.module.dlq.binding"
             topic="vendor.module.process"
             destinationType="queue"
             destination="vendor.module.dlq"/>
</exchange>
<exchange name="vendor.module.exchange" type="topic" connection="amqp">
    <binding id="vendor.module.binding"
             topic="vendor.module.process"
             destinationType="queue"
             destination="vendor.module.queue">
        <arguments>
            <argument name="x-dead-letter-exchange" xsi:type="string">vendor.module.dlx</argument>
            <argument name="x-delivery-limit" xsi:type="number">3</argument>
            <argument name="x-message-ttl" xsi:type="number">30000</argument>
        </arguments>
    </binding>
</exchange>
```

**4. `etc/queue_consumer.xml`** -- consumer handler:
```xml
<consumer name="vendor.module.consumer"
          queue="vendor.module.queue"
          handler="Vendor\Module\Model\Consumer\Handler::process"
          connection="amqp"
          maxMessages="1000"/>
```

### Enforcement
Self-enforced via code review. Static analysis (xmllint plus a custom check for the four XML files) catches missing files. ENF-OPS-002 covers the equivalent runtime invariant.

### Rationale
Magento's queue framework splits configuration across four XML files. Missing any one causes silent failures: messages published but never consumed, consumers registered but never bound, or failed messages dropped without DLQ routing.

<!-- RULE END: FW-M2-RT-005 -->
---

<!-- RULE START: FW-M2-RT-006 -->
## Rule FW-M2-RT-006

**Domain**: Frameworks / Magento 2
**Severity**: High
**Scope**: Component
**Mandatory**: false

### Trigger
When writing code that queries stock/inventory data and the Magento installation uses MSI (Multi-Source Inventory) with multiple websites.

### Statement
Features that interact with inventory must declare which stock is being referenced (default vs MSI), how stock is resolved (StockResolverInterface vs legacy StockRegistryInterface), and whether the feature works in multi-website/multi-stock setups.

### Violation
```php
// Uses legacy single-stock API -- wrong for multi-website MSI setups
$stockStatus = $this->stockRegistry->getStockStatusBySku($sku);
$isInStock = $stockStatus->getIsInStock();
// Returns default stock only -- incorrect for Website B mapped to Stock 2
```

### Pass
```php
// Resolves stock per website via MSI
$websiteCode = $this->storeManager->getWebsite()->getCode();
$stockId = $this->stockResolver->execute(
    SalesChannelInterface::TYPE_WEBSITE,
    $websiteCode
)->getStockId();
$salableQty = $this->getProductSalableQty->execute($sku, $stockId);
```

### Enforcement
ENF-SYS-002 (temporal truth source -- which stock authority?).

### Rationale
MSI decouples stock from websites. A product can be salable on Website A (Stock 1) but not on Website B (Stock 2). Code assuming a single global stock produces incorrect results in multi-website, multi-stock configurations.

<!-- RULE END: FW-M2-RT-006 -->
