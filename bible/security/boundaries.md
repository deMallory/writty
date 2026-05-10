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
---

<!-- RULE START: SEC-UNI-004 -->
## Rule SEC-UNI-004

**Domain**: Security
**Severity**: Critical
**Scope**: Entity
**Mandatory**: false

### Trigger
When a string literal in source code matches patterns for API keys, tokens, passwords, or secrets (long alphanumeric strings, `sk_live_*`, `AKIA*`, `password =`, bearer tokens), or when `env.php`/`.env` values appear as hardcoded defaults in committed config files.

### Statement
API keys, tokens, passwords, and secrets are never hardcoded in source files. Read from environment variables or a secrets manager. Config files that may be committed must never contain secrets, even as defaults.

### Violation
```php
private const API_KEY = 'sk_live_EXAMPLE_DO_NOT_USE_1234567890';

public function callPaymentGateway(): void
{
    $this->client->setApiKey(self::API_KEY);
}
```

### Pass
```php
public function __construct(
    private readonly DeploymentConfig $deploymentConfig
) {}

public function callPaymentGateway(): void
{
    $apiKey = $this->deploymentConfig->get('payment/gateway/api_key');
    if (!$apiKey) {
        throw new LocalizedException(__('Payment gateway API key not configured.'));
    }
    $this->client->setApiKey($apiKey);
}
```

### Enforcement
Static analysis (ENF-POST-007) -- PHPCS secret detection sniff. Git pre-commit hook secret scanning.

### Rationale
Hardcoded secrets in source code end up in git history, CI logs, error messages, and any system that processes the codebase. Once committed, a secret is effectively public and must be rotated.

<!-- RULE END: SEC-UNI-004 -->
