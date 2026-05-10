<!-- RULE START: ARCH-COMP-001 -->
## Rule ARCH-COMP-001

**Domain**: Architecture
**Severity**: High
**Scope**: Component
**Mandatory**: false

### Trigger
Class hierarchy depth exceeds 2 levels of project code. Language/framework base classes (`ABC`, `Protocol`, `BaseModel`, `AbstractController`, `AbstractPlugin`) are excluded from the count.

### Statement
Class inheritance depth must not exceed 2 levels of project code. Deeper hierarchies must be refactored to use composition via constructor injection.

### Violation
```python
class SpecificValidator(BaseValidator(AbstractValidator)):
    # 3 levels of project code -- too deep
    ...
```

### Pass
```python
class SpecificValidator:
    def __init__(self, strategy: ValidationStrategy):
        self._strategy = strategy

    def validate(self, data: dict) -> bool:
        return self._strategy.validate(data)
```

### Enforcement
Code review. Check class hierarchy depth during PR review.

### Rationale
Deep inheritance hierarchies create tight coupling, make behavior hard to trace, and resist testing. Composition via injection produces the same polymorphism with explicit, traceable dependencies.

<!-- RULE END: ARCH-COMP-001 -->
---

<!-- RULE START: ARCH-DI-001 -->
## Rule ARCH-DI-001

**Domain**: Architecture
**Severity**: Critical
**Scope**: Entity
**Mandatory**: false

### Trigger
When a class constructor or method body contains `new SomeClass(` where SomeClass is a service, repository, handler, or factory -- not a DTO, value object, or exception.

### Statement
Dependencies must be received via constructor injection typed to an interface. Direct instantiation (`new`) is permitted only for DTOs, value objects, exceptions, and test doubles.

### Violation
```php
class OrderProcessor
{
    public function process(int $orderId): void
    {
        $repo = new OrderRepository($this->connection);
        $order = $repo->getById($orderId);
    }
}
```

### Pass
```php
class OrderProcessor
{
    public function __construct(
        private readonly OrderRepositoryInterface $orderRepository
    ) {}

    public function process(int $orderId): void
    {
        $order = $this->orderRepository->getById($orderId);
    }
}
```

### Enforcement
Magento Coding Standard PHPCS (ENF-POST-007) flags direct ObjectManager usage. PHPStan custom rule flags `new` on injectable types.

### Rationale
Direct instantiation hides dependencies, breaks testability, and bypasses DI container configuration (preferences, plugins, proxies).

<!-- RULE END: ARCH-DI-001 -->
---

<!-- RULE START: ARCH-EXT-001 -->
## Rule ARCH-EXT-001

**Domain**: Architecture
**Severity**: High
**Scope**: Entity
**Mandatory**: false

### Trigger
When a task requires changing behavior of a vendor/core class, and the proposed change involves directly editing the vendor file or copying it into the project.

### Statement
Behavior changes to vendor or core classes must use the framework's extension mechanism (plugin, preference, event observer, layout override). Direct modification of vendor files or copy-paste of vendor classes into the project is forbidden.

### Violation
```php
// Directly editing vendor file or copying it
// vendor/magento/module-sales/Model/Order.php -- modified line 234
public function canCancel()
{
    // CUSTOM: added check for custom status
    if ($this->getStatus() === 'custom_hold') {
        return false;
    }
    return parent::canCancel();
}
```

### Pass
```php
// Plugin on the concrete class
class CanCancelPlugin
{
    public function afterCanCancel(Order $subject, bool $result): bool
    {
        if ($subject->getStatus() === 'custom_hold') {
            return false;
        }
        return $result;
    }
}
```

### Enforcement
Static analysis (ENF-POST-007) -- Magento Coding Standard flags direct core modifications. Code review.

### Rationale
Direct core modifications are lost on composer update. Extension-based changes survive upgrades and make customizations discoverable.

<!-- RULE END: ARCH-EXT-001 -->
---

<!-- RULE START: ARCH-ORG-001 -->
## Rule ARCH-ORG-001

**Domain**: Architecture
**Severity**: High
**Scope**: Component
**Mandatory**: false

### Trigger
When creating or modifying a class that contains logic belonging to a different architectural layer (e.g., SQL queries in a controller, HTML in a service class, business logic in a resource model).

### Statement
Each class must belong to exactly one architectural layer: presentation (controllers, templates, view models), business logic (services, handlers, processors), or data access (repositories, resource models). A class must not contain logic from a different layer.

### Violation
```php
// Controller contains SQL query -- presentation layer doing data access
class OrderController extends Action
{
    public function execute()
    {
        $connection = $this->resourceConnection->getConnection();
        $orders = $connection->fetchAll(
            "SELECT * FROM sales_order WHERE customer_id = :id",
            [':id' => $this->getRequest()->getParam('customer_id')]
        );
        return $this->resultJsonFactory->create()->setData($orders);
    }
}
```

### Pass
```php
// Controller delegates to service, service delegates to repository
class OrderController extends Action
{
    public function __construct(
        private readonly OrderServiceInterface $orderService
    ) {}

    public function execute()
    {
        $customerId = (int) $this->getRequest()->getParam('customer_id');
        $orders = $this->orderService->getByCustomerId($customerId);
        return $this->resultJsonFactory->create()->setData($orders);
    }
}
```

### Enforcement
Code review.

### Rationale
Mixed layers create classes that are untestable, unreusable, and fragile. A controller with SQL queries cannot be unit tested without a database, and its query logic cannot be reused by a CLI command or queue consumer.

<!-- RULE END: ARCH-ORG-001 -->
---

<!-- RULE START: ARCH-TYPE-001 -->
## Rule ARCH-TYPE-001

**Domain**: Architecture
**Severity**: High
**Scope**: Entity
**Mandatory**: false

### Trigger
Any public function (not prefixed with `_` in Python, not `private`/`protected` in PHP/TS) lacks complete parameter and return type annotations.

### Statement
All public functions must have complete type annotations on every parameter and the return value. Language-specific enforcement tools validate correctness.

### Violation
```python
def search(query, limit):
    ...
```

### Pass
```python
def search(query: str, limit: int) -> list[ScoredResult]:
    ...
```

### Enforcement
- Python: `mypy --strict` or `pyright` - PHP: PHPStan level 8 (see also PHP-TYPE-001 for docblock-specific guidance) - TypeScript: `tsc --strict`

### Rationale
Public interfaces are contracts. Unannotated parameters force callers to read implementation to understand expected types. Type annotations enable static analysis, IDE autocompletion, and catch type errors before runtime.

<!-- RULE END: ARCH-TYPE-001 -->
