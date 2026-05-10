<!-- RULE START: SEC-UNI-003 -->
## Rule SEC-UNI-003

**Domain**: Security
**Severity**: High
**Scope**: Entity
**Mandatory**: false

### Trigger
When an API endpoint returns entity data to a caller and the response includes the full entity object or uses `toArray()`/`getData()`/`jsonSerialize()` without field filtering.

### Statement
API responses must explicitly select which fields to include. Never return the full entity. Internal IDs, credentials, PII, and internal state are excluded unless the endpoint specifically requires them and the caller has rights.

### Violation
```php
public function getCustomer(int $id): array
{
    $customer = $this->customerRepository->getById($id);
    return $customer->__toArray();
    // Exposes: password_hash, rp_token, rp_token_created_at, failures_num, lock_expires
}
```

### Pass
```php
public function getCustomer(int $id): CustomerResponseInterface
{
    $customer = $this->customerRepository->getById($id);
    return $this->responseFactory->create([
        'name'  => $customer->getFirstname() . ' ' . $customer->getLastname(),
        'email' => $customer->getEmail(),
    ]);
}
```

### Enforcement
ENF-SEC-002 (data exposure minimization).

### Rationale
API responses that return entire entity objects "for convenience" create attack surfaces. Every exposed field is a potential information leak. Minimizing response data reduces the blast radius of any future authorization bypass.

<!-- RULE END: SEC-UNI-003 -->
