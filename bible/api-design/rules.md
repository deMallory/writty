<!-- RULE START: API-BREAKING-001 -->
## Rule API-BREAKING-001

**Domain**: api-design
**Severity**: High
**Scope**: Component
**Mandatory**: false

### Trigger
When modifying an existing API endpoint or schema.

### Statement
Breaking changes (removed field, renamed field, changed type, removed endpoint, narrowed accepted input) are versioned. Silent contract changes are violations: the old version stays usable until clients migrate.

### Violation
```
# /v1/users used to return {'name': '...'}; today returns {'first_name', 'last_name'}; clients break silently.
```

### Pass
```
# /v1/users still returns {'name'} (computed from first/last);
# /v2/users returns {'first_name', 'last_name'}.
# v1 deprecated; sunset date communicated.
```

### Enforcement
Code review. API diff tools (openapi-diff) detect breaking changes in CI.

### Rationale
Silent breakage is invisible to the team that ships and disastrous to the team that consumes. Versioning makes the contract visible.

<!-- RULE END: API-BREAKING-001 -->
---

<!-- RULE START: API-CONTRACT-001 -->
## Rule API-CONTRACT-001

**Domain**: api-design
**Severity**: High
**Scope**: Component
**Mandatory**: false

### Trigger
When designing or modifying an API endpoint.

### Statement
API request/response schemas are documented via OpenAPI, JSON Schema, GraphQL SDL, or framework-native equivalent. The documentation is generated from the source of truth (Pydantic models, TypeScript types, etc.), not hand-written.

### Violation
```
# API doc is a wiki page maintained separately from code; drifts immediately.
```

### Pass
```
# FastAPI generates /docs from Pydantic models. Spec is always in sync.
```

### Enforcement
CI gate: generated spec is committed; CI verifies it matches code.

### Rationale
Hand-written docs drift. Generated docs stay in sync because they are the code.

<!-- RULE END: API-CONTRACT-001 -->
---

<!-- RULE START: API-ERROR-001 -->
## Rule API-ERROR-001

**Domain**: api-design
**Severity**: High
**Scope**: Component
**Mandatory**: false

### Trigger
When returning error responses from API endpoints.

### Statement
Error responses follow a consistent schema: error code (machine-readable), message (human-readable), and field-level details where applicable. The schema is documented and applied across every endpoint.

### Violation
```python
# Some endpoints return 'error': 'msg'; others return 'message': 'msg'; others return a string body.
```

### Pass
```python
class ErrorResponse(BaseModel):
    error: str            # machine-readable code
    message: str          # human-readable description
    details: list[FieldError] | None = None
# All handlers return ErrorResponse on failure.
```

### Enforcement
Code review. Pydantic-based response models enforce the shape.

### Rationale
Consistent error schemas let one client error-handler work everywhere. Inconsistent schemas force per-endpoint parsing.

<!-- RULE END: API-ERROR-001 -->
---

<!-- RULE START: API-ERROR-002 -->
## Rule API-ERROR-002

**Domain**: api-design
**Severity**: Medium
**Scope**: Component
**Mandatory**: false

### Trigger
When writing error messages returned to API consumers.

### Statement
Error messages are actionable: they tell the caller what to fix, not just what failed. 'Invalid input' is a violation; 'Field `email` must be a valid email address' is the structure.

### Violation
```python
return {'error': 'Bad request'}, 400
```

### Pass
```python
return {'error': 'INVALID_FIELD', 'message': 'Field `quantity` must be a positive integer; received -5'}, 400
```

### Enforcement
Code review.

### Rationale
Actionable errors halve the time-to-fix for integration partners. Bare messages force them to grep the source.

<!-- RULE END: API-ERROR-002 -->
---

<!-- RULE START: API-IDEMPOTENT-001 -->
## Rule API-IDEMPOTENT-001

**Domain**: api-design
**Severity**: Medium
**Scope**: Component
**Mandatory**: false

### Trigger
When implementing PUT and DELETE endpoints.

### Statement
PUT and DELETE are idempotent: calling the same endpoint twice produces the same final state. PUT replaces; DELETE removes (deleting an already-deleted resource is not an error). Repeated calls do not produce duplicate side effects.

### Violation
```python
@app.delete('/users/<id>')
def delete_user(id):
    user = User.query.get_or_404(id)  # 404 on second call -> not idempotent
    user.delete()
    return '', 204
```

### Pass
```python
@app.delete('/users/<id>')
def delete_user(id):
    user = User.query.get(id)
    if user:
        user.delete()
    return '', 204  # 204 whether or not the user existed
```

### Enforcement
Code review.

### Rationale
Network retries are universal. Idempotent PUT/DELETE makes retries safe; non-idempotent versions risk duplicate-state bugs.

<!-- RULE END: API-IDEMPOTENT-001 -->
---

<!-- RULE START: API-PAGINATION-001 -->
## Rule API-PAGINATION-001

**Domain**: api-design
**Severity**: High
**Scope**: Component
**Mandatory**: false

### Trigger
When implementing list endpoints.

### Statement
List endpoints are paginated with a consistent scheme across the API: cursor-based (preferred for large/changing sets) or offset-based with total count. The pagination metadata (next, prev, total) is included in the response envelope.

### Violation
```python
@app.get('/orders')
def list_orders():
    return Order.query.all()  # unbounded
```

### Pass
```python
@app.get('/orders')
def list_orders(cursor: str | None = None, limit: int = 25):
    items, next_cursor = paginate(Order.query, cursor, limit)
    return {'items': items, 'next_cursor': next_cursor}
```

### Enforcement
Code review.

### Rationale
Pagination contains the API's worst-case response size. Consistent schemes let one client library work across every endpoint.

<!-- RULE END: API-PAGINATION-001 -->
---

<!-- RULE START: API-PAGINATION-002 -->
## Rule API-PAGINATION-002

**Domain**: api-design
**Severity**: Medium
**Scope**: Component
**Mandatory**: false

### Trigger
When parameterizing page-size on list endpoints.

### Statement
Default page size is small (10-25). Maximum page size is enforced server-side. Clients cannot bypass the limit by passing a larger `per_page`.

### Violation
```python
per_page = int(request.args.get('per_page', 100))  # client can pass 1000000
```

### Pass
```python
per_page = min(int(request.args.get('per_page', 25)), 200)
```

### Enforcement
Code review.

### Rationale
Server-side caps prevent a single request from exhausting capacity. The default keeps responses fast for the common case.

<!-- RULE END: API-PAGINATION-002 -->
---

<!-- RULE START: API-REST-001 -->
## Rule API-REST-001

**Domain**: api-design
**Severity**: Medium
**Scope**: Component
**Mandatory**: false

### Trigger
When defining HTTP endpoints in a REST-style API.

### Statement
HTTP methods match semantics: GET for reads (idempotent, no side effects), POST for creates, PUT/PATCH for updates, DELETE for deletes. A GET that mutates state is a violation.

### Violation
```python
@app.get('/users/<id>/delete')
def delete_user(id): User.query.get(id).delete()
```

### Pass
```python
@app.delete('/users/<id>')
def delete_user(id): User.query.get(id).delete()
```

### Enforcement
Code review.

### Rationale
Method semantics drive correctness for caches, retries, and CSRF protections. A GET that deletes can be triggered by a link preview.

<!-- RULE END: API-REST-001 -->
---

<!-- RULE START: API-REST-002 -->
## Rule API-REST-002

**Domain**: api-design
**Severity**: Medium
**Scope**: Component
**Mandatory**: false

### Trigger
When defining URL paths for REST endpoints.

### Statement
Resource URLs are nouns. `/users`, `/orders/123`, `/orders/123/cancel`. Verb-style URLs (`/getUsers`, `/deleteOrder`) are violations except for explicit action endpoints (`/orders/123/cancel` is acceptable because it's an action on a noun).

### Violation
```
GET /api/getUsers
POST /api/deleteOrder?id=123
```

### Pass
```
GET /api/users
DELETE /api/orders/123
```

### Enforcement
Code review.

### Rationale
Noun-based URLs let the method carry the verb. The URL identifies the resource; the method says what to do with it.

<!-- RULE END: API-REST-002 -->
---

<!-- RULE START: API-STATUS-001 -->
## Rule API-STATUS-001

**Domain**: api-design
**Severity**: High
**Scope**: Component
**Mandatory**: false

### Trigger
When returning responses from API endpoints.

### Statement
Response status codes match the outcome: 201 for created, 204 for no-content, 400 for client error, 401 unauth, 403 forbidden, 404 not found, 409 conflict, 422 validation, 5xx for server errors. Returning 200 for failures or 500 for validation is a violation.

### Violation
```python
return {'error': 'not found'}, 200
```

### Pass
```python
return {'error': 'not found'}, 404
```

### Enforcement
Code review.

### Rationale
Status codes are the integration contract for clients, monitors, and load balancers. Mismatched codes break retries, alerts, and circuit breakers.

<!-- RULE END: API-STATUS-001 -->
---

<!-- RULE START: API-STATUS-002 -->
## Rule API-STATUS-002

**Domain**: api-design
**Severity**: Medium
**Scope**: Component
**Mandatory**: false

### Trigger
When deciding the status code for a handled error.

### Statement
5xx codes are never caused by invalid user input. Bad input produces 4xx (typically 400 or 422). 5xx is reserved for server-side faults the user could not have caused (DB down, dependency failure, unhandled exception).

### Violation
```python
if not is_valid(payload):
    return error('invalid'), 500  # 4xx-class problem, but tagged as server error
```

### Pass
```python
if not is_valid(payload):
    return error('invalid'), 422
```

### Enforcement
Code review. Monitoring should track 5xx separately from 4xx.

### Rationale
5xx tagging triggers paging and dashboard alerts. Misclassifying 4xx as 5xx floods the incident channel with non-incidents.

<!-- RULE END: API-STATUS-002 -->
---

<!-- RULE START: API-VERSION-001 -->
## Rule API-VERSION-001

**Domain**: api-design
**Severity**: Medium
**Scope**: Component
**Mandatory**: false

### Trigger
When designing an API that may change over time.

### Statement
API versioning strategy is defined and enforced: URL path (`/v1/`, `/v2/`), header (`Accept: application/vnd.api.v2+json`), or query param. Mixing strategies or omitting versioning is a violation; a documented choice is consistently applied.

### Violation
```python
# /api/users returns one shape today, another after a refactor; no version mechanism.
```

### Pass
```python
# /api/v1/users frozen; /api/v2/users for new shape.
```

### Enforcement
Code review.

### Rationale
Versioning lets the API evolve without breaking existing clients. Unversioned APIs make every change a coordinated client upgrade.

<!-- RULE END: API-VERSION-001 -->
