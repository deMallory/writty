<!-- RULE START: PERF-ASYNC-001 -->
## Rule PERF-ASYNC-001

**Domain**: performance
**Severity**: High
**Scope**: Component
**Mandatory**: false

### Trigger
When implementing I/O-bound operations in a runtime that supports async (Python asyncio, Node, Tokio, Kotlin coroutines).

### Statement
I/O-bound operations use async / non-blocking calls, not synchronous blocking. The event loop is not stalled waiting for HTTP, DB, or file I/O.

### Violation
```python
async def handle():
    response = requests.get(url)  # sync HTTP in async fn
    return response.json()
```

### Pass
```python
async def handle():
    response = await httpx.AsyncClient().get(url)
    return response.json()
```

### Enforcement
Code review. Linter rules (asyncio-blocker check, eslint async-no-floating-promises).

### Rationale
Sync I/O in an async loop stalls every other concurrent request on that worker. Async preserves the concurrency model.

<!-- RULE END: PERF-ASYNC-001 -->
---

<!-- RULE START: PERF-BATCH-001 -->
## Rule PERF-BATCH-001

**Domain**: performance
**Severity**: Medium
**Scope**: Component
**Mandatory**: false

### Trigger
When making multiple independent I/O calls within a request handler.

### Statement
Independent I/O calls run in parallel. `Promise.all`, `asyncio.gather`, `tokio::join!`, goroutine + WaitGroup. Serial awaiting of independent calls is a violation.

### Violation
```javascript
const user = await fetchUser(id);
const orders = await fetchOrders(id);
const notifications = await fetchNotifications(id);
// 3 sequential round-trips
```

### Pass
```javascript
const [user, orders, notifications] = await Promise.all([
    fetchUser(id),
    fetchOrders(id),
    fetchNotifications(id),
]);
```

### Enforcement
Code review.

### Rationale
Sequential awaiting is N*latency when the work is parallelizable. Parallel I/O is max(latency).

<!-- RULE END: PERF-BATCH-001 -->
---

<!-- RULE START: PERF-BUNDLE-001 -->
## Rule PERF-BUNDLE-001

**Domain**: performance
**Severity**: Medium
**Scope**: Component
**Mandatory**: false

### Trigger
When serving JavaScript or CSS to web clients.

### Statement
Frontend assets are bundled and minified for production. Unminified, un-bundled, or unhashed source files are not served in production. Build tooling (webpack, vite, rollup, esbuild) produces the bundle; CI gates the asset checks.

### Violation
```
# Production index.html includes <script src='main.js'> with 30 separate <script> tags.
```

### Pass
```
# Production index.html includes <script src='main.a2c4f8.min.js'> (one bundle).
```

### Enforcement
CI gate (asset-size budget; lighthouse score).

### Rationale
Unbundled assets multiply HTTP round-trips and shipping bytes. Bundling and minification are zero-effort wins at deploy time.

<!-- RULE END: PERF-BUNDLE-001 -->
---

<!-- RULE START: PERF-CACHE-001 -->
## Rule PERF-CACHE-001

**Domain**: performance
**Severity**: High
**Scope**: Component
**Mandatory**: false

### Trigger
When caching the result of a function or query that varies by user, tenant, locale, or other parameter.

### Statement
Cache keys include every parameter that affects the cached value. A cache key that omits user_id is a violation: it lets one user's response be returned to another user.

### Violation
```python
@cache.memoize()
def get_recommendations():
    return personalize_for(current_user())  # current_user changes; key doesn't
```

### Pass
```python
@cache.memoize(make_name=lambda f: f'{f.__name__}:{current_user().id}')
def get_recommendations():
    return personalize_for(current_user())
```

### Enforcement
Code review.

### Rationale
Stale cross-user cache hits are at best a wrong-data bug and at worst a data-leak vulnerability. Complete cache keys close the gap.

<!-- RULE END: PERF-CACHE-001 -->
---

<!-- RULE START: PERF-CACHE-002 -->
## Rule PERF-CACHE-002

**Domain**: performance
**Severity**: High
**Scope**: Component
**Mandatory**: false

### Trigger
When setting a cache entry.

### Statement
Cache entries have an explicit TTL. Indefinite caching without an invalidation strategy is a violation. The TTL is short enough that stale data is bounded; the invalidation strategy is short enough that fresh data is bounded.

### Violation
```python
cache.set(key, value)  # default behavior may be 'forever'
```

### Pass
```python
cache.set(key, value, ex=300)  # 5-minute TTL; documented invalidation on write
```

### Enforcement
Code review.

### Rationale
Indefinite cache becomes a parallel database that drifts. TTL provides a freshness ceiling even when explicit invalidation fails.

<!-- RULE END: PERF-CACHE-002 -->
---

<!-- RULE START: PERF-CACHE-003 -->
## Rule PERF-CACHE-003

**Domain**: performance
**Severity**: Medium
**Scope**: Component
**Mandatory**: false

### Trigger
When writing data that has a cached representation.

### Statement
Cache invalidation on write is explicit. The write path explicitly invalidates or refreshes the affected cache entries. 'It will expire eventually' is not a strategy.

### Violation
```python
def update_user(user_id, **fields):
    db.update(User, id=user_id, **fields)
    # cache key 'user:<id>' still serves the old value for the next TTL window
```

### Pass
```python
def update_user(user_id, **fields):
    db.update(User, id=user_id, **fields)
    cache.delete(f'user:{user_id}')
```

### Enforcement
Code review.

### Rationale
TTL-only invalidation leaves staleness windows that produce visible bugs (user updates name, sees old name). Explicit invalidation closes the window.

<!-- RULE END: PERF-CACHE-003 -->
---

<!-- RULE START: PERF-CACHE-004 -->
## Rule PERF-CACHE-004

**Domain**: performance
**Severity**: Medium
**Scope**: Component
**Mandatory**: false

### Trigger
When implementing caches that may be hit by many concurrent requests after an entry expires.

### Statement
Cache stampede is mitigated: when a popular cache entry expires, many concurrent callers must not all hit the underlying store at once. Mechanisms: short locks on regenerate, probabilistic early expiration, background refresh.

### Violation
```python
def get(key):
    if cache.has(key):
        return cache.get(key)
    value = expensive_compute()  # 1000 concurrent callers all do this
    cache.set(key, value, ex=300)
    return value
```

### Pass
```python
@cached(early_expiration_fraction=0.1)  # 10% of callers refresh ahead of TTL
def get(key):
    return expensive_compute()
```

### Enforcement
Code review. Cache libraries (cachetools, django-cacheops) implement stampede protection.

### Rationale
A stampeded cache turns the protected resource into the bottleneck precisely when it most needs protection.

<!-- RULE END: PERF-CACHE-004 -->
---

<!-- RULE START: PERF-IMAGE-001 -->
## Rule PERF-IMAGE-001

**Domain**: performance
**Severity**: Low
**Scope**: Component
**Mandatory**: false

### Trigger
When serving images to web clients.

### Statement
Images are served in modern formats (WebP, AVIF) when supported, sized appropriately for the rendered display, and lazy-loaded for off-screen content. Original-resolution PNGs in image elements rendered at 200x200 are violations.

### Violation
```html
<img src='/avatars/user.png' width=200 height=200>
<!-- backend serves 4000x4000 PNG -->
```

### Pass
```html
<picture>
  <source srcset='/avatars/user-200.avif' type='image/avif'>
  <source srcset='/avatars/user-200.webp' type='image/webp'>
  <img src='/avatars/user-200.png' width=200 height=200 loading='lazy'>
</picture>
```

### Enforcement
Image-optimization pipeline (next/image, Cloudinary, ImgIX).

### Rationale
Image bytes dominate frontend payload. Modern formats and right-sizing cut payload by 50-80%; lazy loading defers off-screen cost.

<!-- RULE END: PERF-IMAGE-001 -->
---

<!-- RULE START: PERF-MEM-001 -->
## Rule PERF-MEM-001

**Domain**: performance
**Severity**: High
**Scope**: Component
**Mandatory**: false

### Trigger
When processing collections that may grow with input size: rows from a query, lines from a file, items from an API.

### Statement
Large collections are processed via streaming/iteration, not loaded entirely into memory. Generator expressions, iterator protocols, server-side cursors, chunked reads. Loading the full result set when the consumer needs one row at a time is a violation.

### Violation
```python
rows = db.execute('SELECT * FROM events').fetchall()  # 10M rows in memory
for r in rows: process(r)
```

### Pass
```python
for r in db.execute('SELECT * FROM events').yield_per(1000):
    process(r)
```

### Enforcement
Code review.

### Rationale
In-memory loading scales with the data size; streaming scales with the working-set size. The difference is the difference between OOM and steady operation.

<!-- RULE END: PERF-MEM-001 -->
---

<!-- RULE START: PERF-MEM-002 -->
## Rule PERF-MEM-002

**Domain**: performance
**Severity**: Medium
**Scope**: Component
**Mandatory**: false

### Trigger
When writing long-running processes (workers, daemons, web servers, ML training loops).

### Statement
Object references are released after use. Long-running processes do not retain unbounded structures (caches without eviction, growing dicts, accumulating lists). Memory-leak patterns are reviewed and bounded.

### Violation
```python
WORK_LOG = []  # appended forever; never released
def process(item):
    WORK_LOG.append(item)
    do_work(item)
```

### Pass
```python
from collections import deque
WORK_LOG = deque(maxlen=1000)  # bounded
def process(item):
    WORK_LOG.append(item)
    do_work(item)
```

### Enforcement
Memory profiling. Code review.

### Rationale
Memory leaks turn long-running processes into delayed crashes. Bounded structures keep memory predictable.

<!-- RULE END: PERF-MEM-002 -->
---

<!-- RULE START: PERF-QUERY-001 -->
## Rule PERF-QUERY-001

**Domain**: performance
**Severity**: Critical
**Scope**: Component
**Mandatory**: true
**Mechanical_Enforcement_Path**: bin/run-analysis.sh::analyze_performance_n_plus_one

### Trigger
When iterating over a collection and accessing a related entity inside the loop body.

### Statement
N+1 database query patterns are forbidden. When loading a list of N parents and then accessing each parent's children inside the loop, use joins, eager loading (Django select_related/prefetch_related, SQLAlchemy joinedload, Eloquent with()), or batch fetching. One query per item in a loop is a violation.

### Violation
```python
orders = Order.query.all()
for order in orders:
    print(order.customer.name)  # N+1: one customer query per order
```

### Pass
```python
orders = Order.query.options(joinedload(Order.customer)).all()
for order in orders:
    print(order.customer.name)  # single JOINed query
```

### Enforcement
Mechanically enforced by bin/run-analysis.sh::analyze_performance_n_plus_one: regex flags loop bodies that contain ORM access (`.filter`, `.get`, `.query`, `.find`, `.where`, `.first`, `.fetch`, `.where(...).first`) where the loop variable is referenced in the query. Heuristic; reviewer judgment closes false positives.

### Rationale
N+1 is the single most common database performance bug. A list page with 100 items can issue 100+ extra queries, scaling with traffic. Eager loading or batch fetching is the structural defense.

<!-- RULE END: PERF-QUERY-001 -->
---

<!-- RULE START: PERF-QUERY-002 -->
## Rule PERF-QUERY-002

**Domain**: performance
**Severity**: High
**Scope**: Component
**Mandatory**: false

### Trigger
When writing database queries that filter (WHERE) or join (JOIN) on a column.

### Statement
Columns used in WHERE clauses or JOIN conditions for non-trivial table sizes must have indexes. Full-table scans on production-sized tables are violations. The migration that introduces the query is accompanied by the migration that creates the index.

### Violation
```python
# WHERE customer_id = ? with no index on orders.customer_id; full scan on 50M rows.
Order.query.filter_by(customer_id=cid).all()
```

### Pass
```python
# Migration: CREATE INDEX idx_orders_customer_id ON orders(customer_id);
Order.query.filter_by(customer_id=cid).all()
```

### Enforcement
Schema review during migration PRs. Query plans (EXPLAIN) for new queries.

### Rationale
Unindexed queries are O(N) on table size; indexed queries are O(log N). The difference becomes catastrophic as data grows.

<!-- RULE END: PERF-QUERY-002 -->
---

<!-- RULE START: PERF-QUERY-003 -->
## Rule PERF-QUERY-003

**Domain**: performance
**Severity**: Medium
**Scope**: Component
**Mandatory**: false

### Trigger
When writing SELECT queries against any table.

### Statement
Queries specify the columns needed, not `SELECT *`. Wide rows transferred over the network when the consumer needs three fields wastes bandwidth, memory, and ORM hydration time.

### Violation
```python
Order.query.all()  # full row hydration including 30-column BLOB
```

### Pass
```python
Order.query.with_entities(Order.id, Order.status, Order.total).all()
```

### Enforcement
Code review.

### Rationale
Wide selects compound at scale: 50KB rows fetched 1000 times is 50MB of unused data on the wire. Narrow selects are free wins.

<!-- RULE END: PERF-QUERY-003 -->
---

<!-- RULE START: PERF-QUERY-004 -->
## Rule PERF-QUERY-004

**Domain**: performance
**Severity**: Medium
**Scope**: Component
**Mandatory**: false

### Trigger
When implementing list endpoints that return collections.

### Statement
List endpoints require pagination with a maximum page size. Unbounded result sets are violations. Pagination is parameterized (limit/offset, cursor, or page/per_page); the default page size is small (10-25); the maximum is bounded (100-200).

### Violation
```python
@app.get('/api/orders')
def list_orders():
    return Order.query.all()  # could be 10 million rows
```

### Pass
```python
@app.get('/api/orders')
def list_orders(page: int = 1, per_page: int = 25):
    per_page = min(per_page, 200)
    return paginate(Order.query, page, per_page)
```

### Enforcement
Code review.

### Rationale
An unbounded list endpoint is a database DoS waiting to happen. Bounded pagination caps the worst case at the API layer.

<!-- RULE END: PERF-QUERY-004 -->
