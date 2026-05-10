<!-- RULE START: SCALE-CONFIG-001 -->
## Rule SCALE-CONFIG-001

**Domain**: scaling
**Severity**: Medium
**Scope**: Component
**Mandatory**: false

### Trigger
When introducing configurable behavior.

### Statement
Configuration supports environment-based overrides without code changes. Defaults live in code; per-environment values come from env vars, config files, or a secrets manager. New deployment targets do not require code edits.

### Violation
```python
API_URL = 'https://api.prod.example.com'  # hardcoded
```

### Pass
```python
API_URL = os.environ.get('API_URL', 'https://api.example.com')
```

### Enforcement
Code review.

### Rationale
Hardcoded environment values force a build per environment and produce drift between staging and prod. Config-driven behavior eliminates the rebuild.

<!-- RULE END: SCALE-CONFIG-001 -->
---

<!-- RULE START: SCALE-DB-001 -->
## Rule SCALE-DB-001

**Domain**: scaling
**Severity**: High
**Scope**: Component
**Mandatory**: false

### Trigger
When establishing database connections from application code.

### Statement
Database connections are pooled with size limits. Per-request connection creation is forbidden; the pool is initialized at startup. Pool size is bounded so that the application cannot exhaust the database's connection limit.

### Violation
```python
def get_user(id):
    conn = psycopg2.connect(DATABASE_URL)  # new connection per call
    ...
    conn.close()
```

### Pass
```python
pool = ConnectionPool(DATABASE_URL, min_size=2, max_size=10)
def get_user(id):
    with pool.connection() as conn:
        ...
```

### Enforcement
Code review.

### Rationale
Per-request connections are slow (handshake overhead), exhaust the DB's connection limit at peak, and fail under load. Pooling is the structural defense.

<!-- RULE END: SCALE-DB-001 -->
---

<!-- RULE START: SCALE-DB-002 -->
## Rule SCALE-DB-002

**Domain**: scaling
**Severity**: Medium
**Scope**: Component
**Mandatory**: false

### Trigger
When implementing read-heavy queries against a database that supports replication.

### Statement
Read replicas serve read-heavy queries where eventual consistency is acceptable (analytics, dashboards, list pages). Writes go to the primary; reads route to the closest healthy replica.

### Violation
```python
# Every query, read or write, hits the primary.
User.query.all()
```

### Pass
```python
user = User.query.all()  # reads to replica
user.update(...)  # writes to primary
```

### Enforcement
Code review. ORM router config (Django DATABASES + DATABASE_ROUTERS, SQLAlchemy multiple binds).

### Rationale
Reads dominate most workloads. Routing them to replicas offloads the primary and lets read capacity scale independently.

<!-- RULE END: SCALE-DB-002 -->
---

<!-- RULE START: SCALE-HEALTH-001 -->
## Rule SCALE-HEALTH-001

**Domain**: scaling
**Severity**: High
**Scope**: Component
**Mandatory**: false

### Trigger
When implementing health-check endpoints for orchestration systems (Kubernetes, ECS, load balancers).

### Statement
Health-check endpoints verify actual service readiness: DB connection, critical downstream dependencies, ability to serve a request. A 200 OK that doesn't check downstream dependencies is a violation.

### Violation
```python
@app.get('/health')
def health():
    return 'ok'  # serves OK even when DB is down
```

### Pass
```python
@app.get('/health')
def health():
    db.execute('SELECT 1')
    redis.ping()
    return 'ok'
```

### Enforcement
Code review.

### Rationale
A trivial health check turns 'service ready' into 'process running' -- the load balancer keeps sending traffic to a worker that cannot serve.

<!-- RULE END: SCALE-HEALTH-001 -->
---

<!-- RULE START: SCALE-HEALTH-002 -->
## Rule SCALE-HEALTH-002

**Domain**: scaling
**Severity**: Medium
**Scope**: Component
**Mandatory**: false

### Trigger
When implementing health endpoints alongside Kubernetes-style readiness/liveness probes.

### Statement
Readiness (`/ready`) and liveness (`/live`) probes are distinct. Ready = can serve traffic now (deps healthy, warmup done). Live = process is responsive but not necessarily ready. A liveness failure restarts the pod; a readiness failure removes it from rotation.

### Violation
```python
# Single /health endpoint used for both probes.
```

### Pass
```python
@app.get('/live')
def live(): return 'ok'
@app.get('/ready')
def ready():
    db.execute('SELECT 1')
    return 'ok'
```

### Enforcement
Code review.

### Rationale
Conflating ready and live causes spurious pod restarts (DB blip restarts every replica) or zombie rotation (process is hung but health says ok). Separation matches Kubernetes semantics.

<!-- RULE END: SCALE-HEALTH-002 -->
---

<!-- RULE START: SCALE-MIGRATE-001 -->
## Rule SCALE-MIGRATE-001

**Domain**: scaling
**Severity**: High
**Scope**: Component
**Mandatory**: false

### Trigger
When deploying schema changes alongside rolling code deploys.

### Statement
Database migrations are backwards-compatible across the deployment window: old code can run against the new schema until the deploy completes. Destructive changes (drop column, rename column) are split into multiple deploys: 1) deploy code that stops using the column; 2) drop in a later deploy.

### Violation
```python
# Single deploy: drop_column('users', 'legacy_email') + new code that uses 'email'.
# Old pods still query 'legacy_email' during rollout -> errors.
```

### Pass
```python
# Deploy 1: new code reads/writes 'email'; migration adds 'email'.
# Deploy 2 (later): migration drops 'legacy_email' once confirmed unused.
```

### Enforcement
Code review.

### Rationale
Forward-only migrations break rolling deploys: half the pods see the new schema, half the old. Phased migrations preserve the invariant that any code version works.

<!-- RULE END: SCALE-MIGRATE-001 -->
---

<!-- RULE START: SCALE-QUEUE-001 -->
## Rule SCALE-QUEUE-001

**Domain**: scaling
**Severity**: High
**Scope**: Component
**Mandatory**: false

### Trigger
When implementing operations that take longer than the request timeout: video transcoding, large reports, batch emails, ML inference, external-API fan-out.

### Statement
Long-running operations are dispatched to a background queue (Celery, Sidekiq, RQ, BullMQ, SQS+worker), not executed inside the request cycle. The request returns a job ID; status is polled or pushed.

### Violation
```python
@app.post('/reports')
def generate_report():
    report = generate_huge_report()  # 60 seconds; request times out
    return report
```

### Pass
```python
@app.post('/reports')
def generate_report():
    job = queue.enqueue('generate_huge_report', user_id=current_user.id)
    return {'job_id': job.id}, 202
```

### Enforcement
Code review.

### Rationale
Long-running synchronous work blocks the worker, hits client timeouts, and risks loss on deploy. Background queues decouple submission from completion.

<!-- RULE END: SCALE-QUEUE-001 -->
---

<!-- RULE START: SCALE-QUEUE-002 -->
## Rule SCALE-QUEUE-002

**Domain**: scaling
**Severity**: Medium
**Scope**: Component
**Mandatory**: false

### Trigger
When implementing background-queue consumers.

### Statement
Queue consumers are idempotent: receiving the same message twice does not corrupt state. Messages may be redelivered (worker crash mid-job, broker retry). Use idempotency keys, conditional writes, or upserts to absorb duplicates.

### Violation
```python
@worker.task
def charge_user(user_id, amount):
    stripe.charge(user_id, amount)  # duplicate delivery = double charge
```

### Pass
```python
@worker.task
def charge_user(user_id, amount, idempotency_key):
    if PaymentLog.exists(idempotency_key):
        return  # already processed
    stripe.charge(user_id, amount, idempotency_key=idempotency_key)
    PaymentLog.create(idempotency_key)
```

### Enforcement
Code review.

### Rationale
Message redelivery is normal in distributed queues. Idempotent consumers handle it; non-idempotent consumers produce silent data corruption.

<!-- RULE END: SCALE-QUEUE-002 -->
---

<!-- RULE START: SCALE-STATELESS-001 -->
## Rule SCALE-STATELESS-001

**Domain**: scaling
**Severity**: High
**Scope**: Component
**Mandatory**: true
**Mechanical_Enforcement_Path**: bin/run-analysis.sh::analyze_scaling_stateless

### Trigger
When implementing application processes that handle multiple requests (web servers, API handlers, queue workers).

### Statement
Application processes are stateless. Session data, user state, in-progress workflows, and any data that must survive across requests is stored in an external store (Redis, database, cache service), not in process memory. Module-level mutable globals that hold per-user state are violations.

### Violation
```python
USER_CARTS = {}  # module-level dict; lost on restart; not shared across workers
@app.post('/cart/add')
def add(item_id):
    USER_CARTS.setdefault(current_user.id, []).append(item_id)
```

### Pass
```python
@app.post('/cart/add')
def add(item_id):
    cart = redis_client.get(f'cart:{current_user.id}') or []
    cart.append(item_id)
    redis_client.set(f'cart:{current_user.id}', cart, ex=3600)
```

### Enforcement
Code review. Look for module-level mutable dicts/lists that grow with users.

### Rationale
Stateless processes scale horizontally: any worker can serve any request. Stateful processes pin the user to one machine, lose state on restart, and fail to scale beyond one node.

<!-- RULE END: SCALE-STATELESS-001 -->
---

<!-- RULE START: SCALE-STATELESS-002 -->
## Rule SCALE-STATELESS-002

**Domain**: scaling
**Severity**: Medium
**Scope**: Component
**Mandatory**: false

### Trigger
When persisting user-uploaded files or generated artifacts.

### Statement
File storage uses object storage (S3, GCS, Azure Blob, MinIO), not the local filesystem. Files written to local disk are not durable across deploys and are not shared across workers.

### Violation
```python
@app.post('/avatar')
def upload(file):
    file.save('/var/uploads/' + file.filename)
```

### Pass
```python
@app.post('/avatar')
def upload(file):
    s3_client.put_object(Bucket='avatars', Key=f'{user.id}/{file.filename}', Body=file.read())
```

### Enforcement
Code review.

### Rationale
Local filesystem storage is invisible to other workers and disappears on container restart. Object storage is the structural fix.

<!-- RULE END: SCALE-STATELESS-002 -->
