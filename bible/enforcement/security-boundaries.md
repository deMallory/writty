<!-- RULE START: ENF-SEC-001 -->
## Rule ENF-SEC-001

**Domain**: Security
**Severity**: Critical
**Scope**: Slice
**Mandatory**: true
**Mechanical_Enforcement_Path**: bin/run-analysis.sh:78 (PHPStan ownership check)

### Trigger
When generating code for any externally accessible endpoint (REST route, GraphQL resolver, admin controller, storefront controller, CLI command).

### Statement
Every endpoint must have a written Access Boundary Declaration presented and approved before implementation code is produced. The declaration must answer four questions: who can call it, how the caller is authenticated, what data ownership rules apply, and what happens when unauthorized.

### Violation
```
// Phase A output for a GraphQL resolver:
"The reservations query returns reservation data for a given order ID."
// No mention of who can call it, how ownership is verified, or what happens for unauthorized callers.
```

### Pass
```
// Phase A output for a GraphQL resolver:
"reservations(order_id:) Access Boundary:
  Who: Admin (unrestricted), Customer (own orders only), Anonymous (denied)
  Auth: Caller identity + type checked in resolver via $context->getUserType()
  Ownership: Authenticated user ID must match order.customer_id
  Unauthorized: GraphQlAuthorizationException"
```

### Enforcement
ENF-GATE-007 test skeletons must include unauthorized caller test, ownership violation test, and valid caller test. > **Framework-specific guidance**: See `bible/frameworks/magento/runtime-constraints.md` for Magento 2 patterns (`webapi.xml`, `$context->getUserId()`, `_isAllowed()`, `GraphQlAuthorizationException`).

### Rationale
The most common security gap in AI-generated code is omission -- endpoints that work correctly but never ask "who should be allowed to call this?" Forcing the declaration before implementation makes security a first-class design constraint, not an afterthought.

<!-- RULE END: ENF-SEC-001 -->
---

<!-- RULE START: ENF-SEC-002 -->
## Rule ENF-SEC-002

**Domain**: Security
**Severity**: High
**Scope**: Entity
**Mandatory**: false

### Trigger
When an API endpoint (REST or GraphQL) returns entity data to a caller, and the response includes the full entity object or uses `toArray()`/`getData()`/`jsonSerialize()` without field filtering.

### Statement
API responses must explicitly select which fields to return. Never return the full entity. Internal IDs, credentials, PII, and internal state are excluded unless the endpoint specifically requires them and the caller has rights.

### Violation
```php
public function getById(int $orderId): array
{
    $order = $this->orderRepository->getById($orderId);
    return $order->getData(); // exposes internal_note, remote_ip, customer_taxvat, etc.
}
```

### Pass
```php
public function getById(int $orderId): OrderResponseInterface
{
    $order = $this->orderRepository->getById($orderId);
    return $this->responseFactory->create([
        'order_id'    => $order->getEntityId(),
        'status'      => $order->getStatus(),
        'grand_total' => $order->getGrandTotal(),
        'created_at'  => $order->getCreatedAt(),
    ]);
}
```

### Enforcement
Self-enforced via code review. Static analysis (PHPStan rule for getData() or jsonSerialize() in API context) catches the most common patterns. ENF-SEC-001 specifies which fields consumers need.

### Rationale
API responses that return entire entity objects "for convenience" create attack surfaces. Every exposed field is a potential information leak. Minimizing response data reduces the blast radius of any future authorization bypass.

<!-- RULE END: ENF-SEC-002 -->
