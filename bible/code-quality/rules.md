<!-- RULE START: CLEAN-ASSERT-001 -->
## Rule CLEAN-ASSERT-001

**Domain**: code-quality
**Severity**: Medium
**Scope**: Component
**Mandatory**: false

### Trigger
When using `assert` statements (or equivalent: console.assert, debug_assert).

### Statement
Assertions are reserved for invariants -- conditions that the developer believes can never be false. Assertions are not for input validation, control flow, or error handling. Production builds may strip assertions; security-critical or business-critical checks must use explicit raise/throw.

### Violation
```python
def transfer(amount, balance):
    assert amount <= balance, 'overdraft'  # user can cause this!
    debit(amount)
```

### Pass
```python
def transfer(amount, balance):
    if amount > balance:
        raise InsufficientFundsError(balance, amount)
    debit(amount)
    # Invariant after debit -- assertion-appropriate:
    assert new_balance(balance, amount) >= 0
```

### Enforcement
Code review.

### Rationale
Stripped assertions in production silently let the bad path proceed. Real validation belongs in real checks; assertions are for developer-facing 'this should be impossible' guards.

<!-- RULE END: CLEAN-ASSERT-001 -->
---

<!-- RULE START: CLEAN-BOOL-001 -->
## Rule CLEAN-BOOL-001

**Domain**: code-quality
**Severity**: Medium
**Scope**: Component
**Mandatory**: false

### Trigger
When writing conditional expressions.

### Statement
Boolean comparisons to True/False literal are forbidden. Use the value directly: `if active:` not `if active == True:`. Negation: `if not active:` not `if active == False:`.

### Violation
```python
if user.is_admin == True and user.is_active == True:
    grant()
```

### Pass
```python
if user.is_admin and user.is_active:
    grant()
```

### Enforcement
Linter rules (pylint comparison-with-callable / eqeq, eslint eqeqeq).

### Rationale
Explicit comparison with a literal adds noise without adding precision. The truthy/falsy interpretation is the convention.

<!-- RULE END: CLEAN-BOOL-001 -->
---

<!-- RULE START: CLEAN-COMMENT-001 -->
## Rule CLEAN-COMMENT-001

**Domain**: code-quality
**Severity**: Medium
**Scope**: Component
**Mandatory**: false

### Trigger
When writing inline comments adjacent to code.

### Statement
Comments explain WHY the code is the way it is (constraint, hidden invariant, surprising business rule, workaround for a known bug). Comments that restate WHAT the next line does in natural language are deleted or rewritten to add intent.

### Violation
```python
# Add tax to total
total = subtotal + (subtotal * tax_rate)
```

### Pass
```python
# Tax computed on subtotal, not on shipping. Per AR-203: shipping is
# already tax-inclusive from the carrier quote.
total = subtotal + (subtotal * tax_rate)
```

### Enforcement
Code review.

### Rationale
Restating-the-code comments rot the moment the code changes. WHY-comments stay useful because the constraint outlives the syntax.

<!-- RULE END: CLEAN-COMMENT-001 -->
---

<!-- RULE START: CLEAN-COMMENT-002 -->
## Rule CLEAN-COMMENT-002

**Domain**: code-quality
**Severity**: Medium
**Scope**: Component
**Mandatory**: false

### Trigger
When opening a pull request or committing.

### Statement
Commented-out code is never committed. Version control is the history; comments are not. Removed code is removed entirely; if it might be needed later, that future-self can recover it from git.

### Violation
```python
# old logic, leaving in case we revert:
# total = subtotal * 1.08
total = subtotal * tax_rate
```

### Pass
```python
total = subtotal * tax_rate
```

### Enforcement
Pre-commit hook can flag large commented-out blocks. Code review.

### Rationale
Commented-out code is dead weight that confuses readers and bloats diffs. Git remembers; the file does not need to.

<!-- RULE END: CLEAN-COMMENT-002 -->
---

<!-- RULE START: CLEAN-COUPLING-001 -->
## Rule CLEAN-COUPLING-001

**Domain**: code-quality
**Severity**: High
**Scope**: Component
**Mandatory**: false

### Trigger
When importing or constructing dependencies inside a module.

### Statement
Modules depend on abstractions (interfaces, protocols, base classes), not concrete implementations. Direct construction of concrete classes inside business logic is a violation; dependencies are injected.

### Violation
```python
class OrderService:
    def __init__(self):
        self.stripe = StripeClient()  # hard-coded concrete
```

### Pass
```python
class OrderService:
    def __init__(self, payments: PaymentGateway):
        self.payments = payments
```

### Enforcement
Code review.

### Rationale
Hard-coded dependencies make code untestable and untransferable. Abstractions let the module work against any conforming implementation.

<!-- RULE END: CLEAN-COUPLING-001 -->
---

<!-- RULE START: CLEAN-COUPLING-002 -->
## Rule CLEAN-COUPLING-002

**Domain**: code-quality
**Severity**: Medium
**Scope**: Component
**Mandatory**: false

### Trigger
When organizing module dependencies.

### Statement
Circular imports or circular module dependencies are forbidden. A reaches B and B reaches A indicates the responsibilities are tangled; extract the shared concept to a third module or invert the dependency.

### Violation
```python
# users.py imports orders.py; orders.py imports users.py
```

### Pass
```python
# users.py, orders.py both import shared/types.py
# orders.py imports users.py (one direction only)
```

### Enforcement
Linter rules (ruff cyclic-import, eslint import/no-cycle).

### Rationale
Cycles make the dependency graph un-orderable and the modules un-testable in isolation.

<!-- RULE END: CLEAN-COUPLING-002 -->
---

<!-- RULE START: CLEAN-DEAD-001 -->
## Rule CLEAN-DEAD-001

**Domain**: code-quality
**Severity**: Medium
**Scope**: Component
**Mandatory**: false

### Trigger
When committing changes that leave imports, variables, functions, or branches unused.

### Statement
No unreachable code, unused imports, unused variables, or unused functions in committed code. The linter is configured to flag these as errors.

### Violation
```python
import os, sys  # sys never referenced

def compute(x):
    y = x * 2  # never used
    return x + 1
```

### Pass
```python
import os

def compute(x):
    return x + 1
```

### Enforcement
Linter rules (ruff F401/F841, eslint no-unused-vars/no-unreachable, gosec deadcode). CI gate.

### Rationale
Dead code distracts readers and rots over time. Removing it is free.

<!-- RULE END: CLEAN-DEAD-001 -->
---

<!-- RULE START: CLEAN-ERR-001 -->
## Rule CLEAN-ERR-001

**Domain**: code-quality
**Severity**: High
**Scope**: Component
**Mandatory**: false

### Trigger
When writing try/except, try/catch, try/rescue, or any exception-handling block.

### Statement
No empty catch blocks. Caught exceptions are either re-raised (preserving cause), logged with full context, or converted to a domain-specific error type. Swallowing exceptions silently is forbidden.

### Violation
```python
try:
    charge_card(order)
except Exception:
    pass  # whatever, move on
```

### Pass
```python
try:
    charge_card(order)
except StripeError as e:
    logger.exception('charge failed', extra={'order_id': order.id})
    raise PaymentFailed(order.id) from e
```

### Enforcement
Linter rules (eslint no-empty, ruff S110, pylint bare-except, PHPCS Generic.CodeAnalysis.EmptyStatement).

### Rationale
Silent exception swallowing turns a stack-trace-in-monitoring into a mystery failure that surfaces minutes or hours later. Logging or re-raising preserves the signal.

<!-- RULE END: CLEAN-ERR-001 -->
---

<!-- RULE START: CLEAN-ERR-002 -->
## Rule CLEAN-ERR-002

**Domain**: code-quality
**Severity**: High
**Scope**: Component
**Mandatory**: false

### Trigger
When writing exception-handling blocks.

### Statement
Exception types caught are specific. `except Exception`, `catch(Exception)`, `rescue` without a class are forbidden except at top-level boundary handlers (uncaught-error middleware, job runner). Specific catches signal which conditions the code is prepared to handle.

### Violation
```python
try:
    user = User.query.get(id)
except Exception:  # masks programming errors as 'user not found'
    return None
```

### Pass
```python
try:
    user = User.query.get(id)
except NoResultFound:
    return None
```

### Enforcement
Linter rules.

### Rationale
Bare `except` catches AttributeError, KeyError, NameError, KeyboardInterrupt -- everything. Specific catches keep programming bugs visible.

<!-- RULE END: CLEAN-ERR-002 -->
---

<!-- RULE START: CLEAN-ERR-003 -->
## Rule CLEAN-ERR-003

**Domain**: code-quality
**Severity**: Medium
**Scope**: Component
**Mandatory**: false

### Trigger
When raising or constructing exception/error objects.

### Statement
Error messages include context: what was being attempted, the input value (when safe to log), and any relevant identifier. Bare messages like 'Invalid' or 'Failed' are violations.

### Violation
```python
raise ValueError('Invalid')
```

### Pass
```python
raise ValueError(f'Invalid order status "{status}" for order {order_id}: expected one of {VALID_STATUSES}')
```

### Enforcement
Code review.

### Rationale
Context-rich errors are the on-call engineer's first line of defense. Bare messages force a code dive to figure out what went wrong.

<!-- RULE END: CLEAN-ERR-003 -->
---

<!-- RULE START: CLEAN-FORMAT-001 -->
## Rule CLEAN-FORMAT-001

**Domain**: code-quality
**Severity**: Low
**Scope**: Component
**Mandatory**: false

### Trigger
When committing or reviewing source code.

### Statement
Formatting is enforced by a configured formatter (Prettier, Black, rustfmt, gofmt, ktfmt). Style-only review comments are forbidden; the formatter wins. Disagreements about formatting are settled by changing the formatter config, not by per-PR debate.

### Violation
```
# PR review: 'add a space after the comma here'
```

### Pass
```
# pre-commit: prettier --write . / black . / rustfmt **/*.rs
```

### Enforcement
Pre-commit hook. CI gate.

### Rationale
Formatter wars consume engineering time without product value. Delegate the entire decision to a tool and move on.

<!-- RULE END: CLEAN-FORMAT-001 -->
---

<!-- RULE START: CLEAN-FUNC-001 -->
## Rule CLEAN-FUNC-001

**Domain**: code-quality
**Severity**: High
**Scope**: Component
**Mandatory**: false

### Trigger
When writing a function that both returns a value and changes state.

### Statement
Functions do one thing. Command-Query Separation: a function either returns a computed value (query) or mutates state (command), never both. Functions that mutate-and-return are split.

### Violation
```python
def get_order(id):
    order = Order.fetch(id)
    order.viewed_at = now()
    order.save()
    return order
```

### Pass
```python
def get_order(id):
    return Order.fetch(id)

def mark_order_viewed(order):
    order.viewed_at = now()
    order.save()
```

### Enforcement
Code review.

### Rationale
CQS makes side effects visible at the call site. A 'getter' that mutates is a landmine: every caller now has hidden persistence semantics it must reason about.

<!-- RULE END: CLEAN-FUNC-001 -->
---

<!-- RULE START: CLEAN-FUNC-002 -->
## Rule CLEAN-FUNC-002

**Domain**: code-quality
**Severity**: Medium
**Scope**: Component
**Mandatory**: false

### Trigger
When writing or modifying any function or method.

### Statement
Functions stay at or below 50 lines of logic (excluding declarations, comments, and blank lines). Longer functions are decomposed into named sub-functions that read as a top-down narrative.

### Violation
```python
def process_order(order):
    # 180 lines of validation, pricing, payment, fulfillment, email,
    # audit log, analytics, inventory reservation, ...
    ...
```

### Pass
```python
def process_order(order):
    validate(order)
    price = price_order(order)
    payment = charge_customer(order.customer, price)
    fulfill(order)
    notify_customer(order)
```

### Enforcement
Linter rules (eslint complexity/max-lines-per-function, pylint too-many-statements). Code review.

### Rationale
Long functions hide the shape of the work. Decomposed code reads like a table of contents at the entry point and lets the reader drill in only where needed.

<!-- RULE END: CLEAN-FUNC-002 -->
---

<!-- RULE START: CLEAN-FUNC-003 -->
## Rule CLEAN-FUNC-003

**Domain**: code-quality
**Severity**: Medium
**Scope**: Component
**Mandatory**: false

### Trigger
When defining or modifying a function signature.

### Statement
Functions accept at most 4 positional parameters. Beyond that, an options/config object (Pydantic model, dataclass, dict) is passed. Long argument lists indicate the function is doing too much or that several arguments belong together as a named concept.

### Violation
```python
def ship_order(order_id, address_line1, address_line2, city, state, zip, country, carrier, service_level, signature_required):
    ...
```

### Pass
```python
@dataclass
class ShippingAddress:
    line1: str; line2: str | None; city: str; state: str; zip: str; country: str

def ship_order(order_id, address: ShippingAddress, options: ShippingOptions):
    ...
```

### Enforcement
Code review.

### Rationale
Long parameter lists are positional-coupling hazards: callers easily mis-order arguments, and adding a new parameter ripples through every call site.

<!-- RULE END: CLEAN-FUNC-003 -->
---

<!-- RULE START: CLEAN-FUNC-004 -->
## Rule CLEAN-FUNC-004

**Domain**: code-quality
**Severity**: Medium
**Scope**: Component
**Mandatory**: false

### Trigger
When adding a boolean parameter that switches function behavior.

### Statement
Flag arguments that switch function behavior are forbidden. Split the function into two named functions, one per branch. Distinct behavior belongs to distinct names.

### Violation
```python
def render_user(user, is_public=True):
    if is_public:
        return public_view(user)
    return private_view(user)
```

### Pass
```python
def render_user_public(user):
    return public_view(user)

def render_user_private(user):
    return private_view(user)
```

### Enforcement
Code review.

### Rationale
Flag arguments hide that the function is two functions in disguise. Named alternatives make the choice explicit at the call site.

<!-- RULE END: CLEAN-FUNC-004 -->
---

<!-- RULE START: CLEAN-LOG-001 -->
## Rule CLEAN-LOG-001

**Domain**: code-quality
**Severity**: Medium
**Scope**: Component
**Mandatory**: false

### Trigger
When emitting log output from application code.

### Statement
Logs use structured logging (JSON or key-value) with severity levels. `print()`, `System.out.println`, `console.log` for application logs are violations. Use the configured logger with appropriate level.

### Violation
```python
print(f'user {user_id} logged in')
```

### Pass
```python
logger.info('user logged in', extra={'user_id': user_id})
```

### Enforcement
Linter rule (ruff T201 for `print`, eslint no-console). Code review.

### Rationale
Structured logs are queryable, filterable, and routable. print()-style logs require regex parsing and lose context when handlers change.

<!-- RULE END: CLEAN-LOG-001 -->
---

<!-- RULE START: CLEAN-LOG-002 -->
## Rule CLEAN-LOG-002

**Domain**: code-quality
**Severity**: Medium
**Scope**: Component
**Mandatory**: false

### Trigger
When emitting logs from request-handling code.

### Statement
Log messages include a correlation/request ID propagated from the inbound request. The ID is set at the entry point (middleware) and attached to every log line for the request, including downstream calls.

### Violation
```python
logger.info('processing order', extra={'order_id': order.id})
# no correlation_id; impossible to join with other services
```

### Pass
```python
logger.info('processing order', extra={
    'order_id': order.id,
    'correlation_id': request.headers.get('X-Correlation-ID'),
})
```

### Enforcement
Middleware that injects the correlation ID into the logger's contextvars. Code review.

### Rationale
Distributed systems are only debuggable when logs across services share an identifier. The correlation ID is the join key for an incident.

<!-- RULE END: CLEAN-LOG-002 -->
---

<!-- RULE START: CLEAN-MAGIC-001 -->
## Rule CLEAN-MAGIC-001

**Domain**: code-quality
**Severity**: High
**Scope**: Component
**Mandatory**: false

### Trigger
When using a numeric or string literal in code that has business meaning beyond its raw value.

### Statement
Magic literals are extracted to named constants with domain context. Numbers like 86400, 1000, 3, strings like 'admin', 'success' are replaced with named constants. Tax rates, fee thresholds, retry counts, status codes all carry names.

### Violation
```python
if elapsed > 86400:  # what does 86400 mean?
    archive(record)
```

### Pass
```python
ONE_DAY_SECONDS = 86400  # archive policy: records >= 1 day old
if elapsed > ONE_DAY_SECONDS:
    archive(record)
```

### Enforcement
Linter rules. Code review.

### Rationale
A named constant explains the value at the use site and at its definition. Magic literals force the reader to derive the meaning by triangulating with adjacent code.

<!-- RULE END: CLEAN-MAGIC-001 -->
---

<!-- RULE START: CLEAN-NAME-001 -->
## Rule CLEAN-NAME-001

**Domain**: code-quality
**Severity**: Medium
**Scope**: Component
**Mandatory**: false

### Trigger
When naming a function, variable, class, type, constant, module, or file.

### Statement
Identifiers use descriptive, domain-meaningful names. Single-letter names are reserved for loop counters (i, j, k) and short lambda parameters. Abbreviations are reserved for established conventions (id, url, http).

### Violation
```python
def p(x, y):
    return x * 1.08 if y else x
```

### Pass
```python
def apply_tax(amount, taxable):
    return amount * TAX_RATE if taxable else amount
```

### Enforcement
Code review.

### Rationale
Names are the readers' shortest path to intent. Cryptic names force re-deriving meaning from context every time the code is read.

<!-- RULE END: CLEAN-NAME-001 -->
---

<!-- RULE START: CLEAN-NAME-002 -->
## Rule CLEAN-NAME-002

**Domain**: code-quality
**Severity**: Medium
**Scope**: Component
**Mandatory**: false

### Trigger
When naming a boolean variable, function returning bool, or property of bool type.

### Statement
Boolean names start with is/has/can/should/needs or read as a predicate (active, enabled). Names that imply nouns (`status`, `flag`) for booleans are violations.

### Violation
```python
status = user_paid_invoice  # bool
flag = True
```

### Pass
```python
is_invoice_paid = user_paid_invoice
has_active_subscription = subscription.active
```

### Enforcement
Code review.

### Rationale
Predicate names let the reader scan the condition as English. `if user.active:` reads correctly; `if user.status:` could mean anything.

<!-- RULE END: CLEAN-NAME-002 -->
---

<!-- RULE START: CLEAN-NEST-001 -->
## Rule CLEAN-NEST-001

**Domain**: code-quality
**Severity**: High
**Scope**: Component
**Mandatory**: false

### Trigger
When the body of a function or method exceeds 3 levels of nesting (loops, conditionals, try/with).

### Statement
Maximum nesting depth is 3 levels. Deeper code is extracted via early returns, guard clauses, or helper functions. Pyramids of doom are violations.

### Violation
```python
def process(item):
    if item:
        if item.active:
            for child in item.children:
                if child.valid:
                    if child.amount > 0:
                        do_work(child)
```

### Pass
```python
def process(item):
    if not item or not item.active:
        return
    for child in item.children:
        process_child(child)

def process_child(child):
    if not child.valid or child.amount <= 0:
        return
    do_work(child)
```

### Enforcement
Linter rules (eslint complexity/max-depth, pylint too-many-nested-blocks). Code review.

### Rationale
Deeply nested code forces the reader to track too many simultaneous conditions. Early-returns flatten the structure into the happy path.

<!-- RULE END: CLEAN-NEST-001 -->
---

<!-- RULE START: CLEAN-RETURN-001 -->
## Rule CLEAN-RETURN-001

**Domain**: code-quality
**Severity**: Medium
**Scope**: Component
**Mandatory**: false

### Trigger
When writing a function that may return different types depending on a branch.

### Statement
Functions return a single, predictable type. A function whose return type varies (string-or-None-or-list) is split or refactored to return an explicit result/optional type. Sentinel return values (`return False on error, return the_value on success`) are forbidden.

### Violation
```python
def find_user(id):
    user = db.get(id)
    if not user:
        return False  # sentinel; caller must distinguish from user=0
    return user
```

### Pass
```python
def find_user(id) -> User | None:
    return db.get(id)
# or, with a Result type:
def find_user(id) -> Result[User, NotFoundError]:
    ...
```

### Enforcement
Type checker (mypy strict, pyright). Code review.

### Rationale
Multiple return types push the caller into ad-hoc type checks at every call site. Single-type returns let the type system carry the contract.

<!-- RULE END: CLEAN-RETURN-001 -->
---

<!-- RULE START: CLEAN-SIDE-001 -->
## Rule CLEAN-SIDE-001

**Domain**: code-quality
**Severity**: High
**Scope**: Component
**Mandatory**: false

### Trigger
When writing or naming a function.

### Statement
Functions named as getters, computers, builders, or formatters (`get_*`, `compute_*`, `build_*`, `to_*`, `as_*`, `format_*`) have no side effects: no I/O, no mutation of arguments, no state changes. Naming and behavior agree.

### Violation
```python
def get_total(order):
    order.viewed_at = now()  # mutates argument
    db.session.commit()      # I/O
    return order.amount
```

### Pass
```python
def get_total(order):
    return order.amount
```

### Enforcement
Code review.

### Rationale
When name and behavior disagree, the caller's mental model is wrong. Side-effect-free getters are safe to call anywhere; side-effecting getters create implicit dependencies.

<!-- RULE END: CLEAN-SIDE-001 -->
---

<!-- RULE START: CLEAN-TERNARY-001 -->
## Rule CLEAN-TERNARY-001

**Domain**: code-quality
**Severity**: Low
**Scope**: Component
**Mandatory**: false

### Trigger
When writing conditional expressions.

### Statement
Nested ternaries are forbidden. `a if c else (b if d else e)` is rewritten as an if/elif/else block. Single-level ternary is acceptable when both branches are short.

### Violation
```python
result = ('admin' if user.is_admin else
          ('staff' if user.is_staff else
          ('vip' if user.is_vip else 'user')))
```

### Pass
```python
if user.is_admin:
    result = 'admin'
elif user.is_staff:
    result = 'staff'
elif user.is_vip:
    result = 'vip'
else:
    result = 'user'
```

### Enforcement
Code review.

### Rationale
Nested ternaries collapse intent into a riddle. Block form is verbose but legible.

<!-- RULE END: CLEAN-TERNARY-001 -->
---

<!-- RULE START: CLEAN-TODO-001 -->
## Rule CLEAN-TODO-001

**Domain**: code-quality
**Severity**: Low
**Scope**: Component
**Mandatory**: false

### Trigger
When writing a TODO, FIXME, HACK, or XXX comment.

### Statement
TODO comments include a tracking reference (issue/ticket number) or an author + date. Bare 'TODO' without context becomes orphaned forever.

### Violation
```python
# TODO: handle null case
```

### Pass
```python
# TODO(ORD-1421): handle the null-billing-address case after the
# customer-import refactor lands.
```

### Enforcement
Linter rule, code review.

### Rationale
Untracked TODOs accumulate into a graveyard that no one cleans. Tracking forces the comment to either become work or be deleted.

<!-- RULE END: CLEAN-TODO-001 -->
---

<!-- RULE START: DRY-CONFIG-001 -->
## Rule DRY-CONFIG-001

**Domain**: code-quality
**Severity**: High
**Scope**: Component
**Mandatory**: false

### Trigger
When defining configuration values: feature flags, thresholds, environment URLs, retry counts, timeouts, fee rates.

### Statement
Each configuration value has exactly one source of truth (env var, config file, constants module, feature-flag service). Multiple definitions across files are violations; the single definition is the canonical and all callers reference it.

### Violation
```python
# config.py: MAX_RETRIES = 3
# worker.py: max_retries = 3
# scheduler.py: 3 retries hardcoded inline
```

### Pass
```python
# config.py: MAX_RETRIES = int(os.environ.get('MAX_RETRIES', '3'))
# all callers: from config import MAX_RETRIES
```

### Enforcement
Code review.

### Rationale
Config drift breaks the assumption that one place controls behavior. A single source of truth restores the invariant.

<!-- RULE END: DRY-CONFIG-001 -->
---

<!-- RULE START: DRY-CONFIG-002 -->
## Rule DRY-CONFIG-002

**Domain**: code-quality
**Severity**: Medium
**Scope**: Component
**Mandatory**: false

### Trigger
When introducing or modifying a feature flag.

### Statement
Feature flags are defined in a single registry (feature-flag module, env var, flag service). Inline `if env == 'prod'` or `if VERSION == 'v2'` checks scattered across modules are violations.

### Violation
```python
# users.py: if get_env() == 'prod': new_path() else: old_path()
# orders.py: if os.environ['STAGE'] == 'prod': ...
```

### Pass
```python
# flags.py: feature(name='new_user_flow', default=False)
# all callers: if flags.is_enabled('new_user_flow'): new_path()
```

### Enforcement
Code review.

### Rationale
Scattered flag checks lose the ability to flip a flag in one place. Centralization is the structural defense for the next change.

<!-- RULE END: DRY-CONFIG-002 -->
---

<!-- RULE START: DRY-DUP-001 -->
## Rule DRY-DUP-001

**Domain**: code-quality
**Severity**: High
**Scope**: Component
**Mandatory**: false

### Trigger
When the same logic block appears in two or more locations.

### Statement
Duplicated logic of 5+ substantively identical lines must be extracted to a shared function or module. Cosmetic differences (variable names, formatting) do not exempt duplication. The exemption for one-off scripts is narrow and documented.

### Violation
```python
# orders.py
tax = subtotal * 0.08
total = subtotal + tax

# invoices.py
tax = invoice.amount * 0.08
total = invoice.amount + tax
```

### Pass
```python
# pricing.py
def apply_tax(amount, rate=TAX_RATE):
    return amount + (amount * rate)

# orders.py / invoices.py both import apply_tax
```

### Enforcement
Code review. Duplicate-detection tools (jscpd, pylint duplicate-code).

### Rationale
Duplication multiplies bug surface: a fix in one copy leaves the others wrong. Extraction is the structural defense.

<!-- RULE END: DRY-DUP-001 -->
---

<!-- RULE START: DRY-DUP-002 -->
## Rule DRY-DUP-002

**Domain**: code-quality
**Severity**: Medium
**Scope**: Component
**Mandatory**: false

### Trigger
When the same constant value (number, string, regex) appears in multiple files.

### Statement
Constants used in 2+ locations are centralized in a constants/config module and imported. Repeating a tax rate, a timeout, a status string, an API base URL across files is a violation.

### Violation
```python
# A.py: TAX_RATE = 0.08
# B.py: tax = amount * 0.08
# C.py: 'TAX_RATE: 8%' in a UI string
```

### Pass
```python
# constants.py: TAX_RATE = 0.08
# all callers: from constants import TAX_RATE
```

### Enforcement
Code review. Linter rules can flag literal magic numbers (overlaps with CLEAN-MAGIC-001).

### Rationale
Scattered constants drift the moment business needs change. One canonical definition makes a single edit the only edit.

<!-- RULE END: DRY-DUP-002 -->
---

<!-- RULE START: DRY-DUP-003 -->
## Rule DRY-DUP-003

**Domain**: code-quality
**Severity**: Medium
**Scope**: Component
**Mandatory**: false

### Trigger
When writing input validation logic.

### Statement
Validation logic is shared via schemas (Pydantic, Zod, JSON Schema) or validator functions, not copy-pasted across handlers. A given field's rules live in one place.

### Violation
```python
# Each endpoint re-implements email regex check and length check.
```

### Pass
```python
class EmailInput(BaseModel):
    email: EmailStr
# All endpoints accept EmailInput.
```

### Enforcement
Code review.

### Rationale
Validation drift across endpoints leads to one endpoint accepting input another rejects. Shared schemas keep the contract uniform.

<!-- RULE END: DRY-DUP-003 -->
---

<!-- RULE START: DRY-QUERY-001 -->
## Rule DRY-QUERY-001

**Domain**: code-quality
**Severity**: Medium
**Scope**: Component
**Mandatory**: false

### Trigger
When writing database queries from handler or service code.

### Statement
Common queries are wrapped in repository or DAO methods, not inlined at every call site. A given query (`active users by tenant`, `unpaid invoices older than N`) lives in one method.

### Violation
```python
# handler1: User.query.filter(User.active==True, User.tenant_id==t).all()
# handler2: same query, copy-pasted
```

### Pass
```python
# repository.py: def active_users(tenant_id): ...
# both handlers call active_users(tenant_id)
```

### Enforcement
Code review.

### Rationale
Inlined queries duplicate filter logic and indexing assumptions. A repository method holds the canonical form.

<!-- RULE END: DRY-QUERY-001 -->
---

<!-- RULE START: DRY-TEMPLATE-001 -->
## Rule DRY-TEMPLATE-001

**Domain**: code-quality
**Severity**: Medium
**Scope**: Component
**Mandatory**: false

### Trigger
When building UI views that repeat the same visual pattern in multiple pages.

### Statement
Repeated UI patterns (cards, modals, form rows, error displays) are extracted to shared components, not copied between views. A shared component is the source of truth for the pattern's behavior and styling.

### Violation
```jsx
// Each page renders <div className='card'>...</div> with copied markup.
```

### Pass
```jsx
// components/Card.tsx exported; all pages import <Card>.
```

### Enforcement
Code review.

### Rationale
Copy-pasted UI fragments drift visually and behaviorally. A shared component anchors the pattern.

<!-- RULE END: DRY-TEMPLATE-001 -->
---

<!-- RULE START: DRY-TYPE-001 -->
## Rule DRY-TYPE-001

**Domain**: code-quality
**Severity**: Medium
**Scope**: Component
**Mandatory**: false

### Trigger
When declaring types or interfaces consumed by multiple modules.

### Statement
Shared types/interfaces are defined once and imported, not redeclared in each consumer. TypeScript `interface User` repeated in three files is a violation; one definition + three imports is the structure.

### Violation
```typescript
// userService.ts: interface User { id: number; name: string; }
// orderService.ts: interface User { id: number; name: string; }
// inventoryService.ts: interface User { id: number; name: string; }
```

### Pass
```typescript
// types/user.ts: export interface User { id: number; name: string; }
// all services: import { User } from '../types/user';
```

### Enforcement
Code review.

### Rationale
Drifting type definitions create silent mismatches at module boundaries. A single source aligns every consumer.

<!-- RULE END: DRY-TYPE-001 -->
---

<!-- RULE START: ERR-CIRCUIT-001 -->
## Rule ERR-CIRCUIT-001

**Domain**: code-quality
**Severity**: Medium
**Scope**: Component
**Mandatory**: false

### Trigger
When an external dependency fails repeatedly.

### Statement
Repeated failures to an external service trigger a circuit breaker: the breaker opens, subsequent calls fail fast with a fallback or error, the breaker half-opens after a cooldown to probe recovery. Libraries: resilience4j, polly, py-breaker, opossum.

### Violation
```python
# Every request continues to call the failing upstream, exhausting threads.
```

### Pass
```python
@breaker(failure_threshold=5, recovery_timeout=30)
def call_upstream(): ...
```

### Enforcement
Code review. Breaker libraries with metrics.

### Rationale
Without a breaker, every request waits the timeout before failing; the failing service drags down everything that calls it. The breaker turns a slow failure into a fast failure.

<!-- RULE END: ERR-CIRCUIT-001 -->
---

<!-- RULE START: ERR-FALLBACK-001 -->
## Rule ERR-FALLBACK-001

**Domain**: code-quality
**Severity**: Medium
**Scope**: Component
**Mandatory**: false

### Trigger
When implementing critical paths that depend on optional or recoverable inputs (cache, secondary service, personalization).

### Statement
Critical paths have defined fallback behavior, documented in code or comments. The fallback path is tested. 'If the cache is down, use the database' is explicit, not implicit.

### Violation
```python
data = cache.get(key) or db.fetch(key)  # what if both fail?
```

### Pass
```python
try:
    data = cache.get(key)
except CacheError:
    logger.warning('cache miss; using DB fallback')
    data = db.fetch(key)
# If DB also fails, the error propagates to the caller.
```

### Enforcement
Code review.

### Rationale
Fallback decisions are part of the design, not an emergent property. Documented fallback paths preserve the critical workflow under partial outage.

<!-- RULE END: ERR-FALLBACK-001 -->
---

<!-- RULE START: ERR-GRACEFUL-001 -->
## Rule ERR-GRACEFUL-001

**Domain**: code-quality
**Severity**: High
**Scope**: Component
**Mandatory**: false

### Trigger
When implementing long-running processes (web servers, workers, daemons, CLI tools that accept signals).

### Statement
The application handles SIGTERM and SIGINT gracefully: stops accepting new work, drains in-flight requests within a deadline, flushes buffers, exits cleanly. Hard-kill on signal is a violation.

### Violation
```python
# default behavior: SIGTERM kills the process mid-request.
```

### Pass
```python
shutdown_event = threading.Event()
signal.signal(signal.SIGTERM, lambda *a: shutdown_event.set())
while not shutdown_event.is_set():
    serve_one_request(timeout=1.0)
drain_in_flight(deadline=30)
logger.info('shut down cleanly')
```

### Enforcement
Code review.

### Rationale
Graceful shutdown preserves in-flight requests and avoids dropped writes on deployment. Hard-kill turns every deploy into a small outage.

<!-- RULE END: ERR-GRACEFUL-001 -->
---

<!-- RULE START: ERR-GRACEFUL-002 -->
## Rule ERR-GRACEFUL-002

**Domain**: code-quality
**Severity**: Medium
**Scope**: Component
**Mandatory**: false

### Trigger
When implementing background jobs, queue workers, or scheduled tasks.

### Statement
Workers have shutdown hooks that complete in-progress work or requeue it. A worker killed mid-job leaves either a half-done state or a re-runnable job; never a silently dropped job.

### Violation
```python
# Worker yanked mid-job; the message is gone (auto-acked at receive).
```

### Pass
```python
# Worker acks message only after job completes. SIGTERM triggers
# wait_for_current_job_to_finish(timeout) then exit.
```

### Enforcement
Code review.

### Rationale
Dropped jobs on shutdown produce silent data inconsistency. Acknowledgement-after-complete plus shutdown hooks preserve the at-least-once contract.

<!-- RULE END: ERR-GRACEFUL-002 -->
---

<!-- RULE START: ERR-HANDLE-001 -->
## Rule ERR-HANDLE-001

**Domain**: code-quality
**Severity**: High
**Scope**: Component
**Mandatory**: false

### Trigger
When making any call to an external system: HTTP, database, file I/O, message queue, third-party SDK, IPC.

### Statement
Every external call is wrapped in error handling with an explicit timeout. Bare network or file calls without try/except + timeout are violations. The handler logs, maps to a domain error, or retries deliberately.

### Violation
```python
response = requests.get('https://api.example.com/data')  # no timeout, no handling
```

### Pass
```python
try:
    response = requests.get('https://api.example.com/data', timeout=5.0)
    response.raise_for_status()
except (requests.Timeout, requests.ConnectionError) as e:
    logger.warning('upstream failure', extra={'service': 'example'})
    raise UpstreamUnavailable('example') from e
```

### Enforcement
Code review.

### Rationale
Unhandled external failures propagate as raw library exceptions to callers that cannot recover or even identify them. Wrapping is the structural defense.

<!-- RULE END: ERR-HANDLE-001 -->
---

<!-- RULE START: ERR-HANDLE-002 -->
## Rule ERR-HANDLE-002

**Domain**: code-quality
**Severity**: High
**Scope**: Component
**Mandatory**: false

### Trigger
When re-raising or wrapping caught exceptions.

### Statement
Errors propagate with context: the wrapping exception preserves the original via `raise ... from e` (Python), `cause:` (JS), `Throwable.initCause` (Java), `wrap` (Go errors.Is/As). Bare re-raise that loses the chain is a violation.

### Violation
```python
try:
    pay(order)
except StripeError:
    raise PaymentFailed()  # original cause lost
```

### Pass
```python
try:
    pay(order)
except StripeError as e:
    raise PaymentFailed(order.id) from e
```

### Enforcement
Code review.

### Rationale
Unchained exceptions hide the root cause behind a generic wrapper. The original stack trace is the most valuable artifact in an incident.

<!-- RULE END: ERR-HANDLE-002 -->
---

<!-- RULE START: ERR-HANDLE-003 -->
## Rule ERR-HANDLE-003

**Domain**: code-quality
**Severity**: Medium
**Scope**: Component
**Mandatory**: false

### Trigger
When constructing error messages returned to end users.

### Statement
User-facing error messages are helpful and human-readable but never expose internal details: file paths, stack traces, SQL fragments, library names, internal IDs. A correlation ID lets support map the user-facing message to the internal log.

### Violation
```python
return {'error': str(traceback.format_exc())}, 500
```

### Pass
```python
return {'error': 'We could not process your request. Reference: ABCD-1234', 'reference': correlation_id}, 500
```

### Enforcement
Code review.

### Rationale
Internal-detail leaks aid reconnaissance and confuse legitimate users. A clear public message + an internal correlation ID balances both audiences.

<!-- RULE END: ERR-HANDLE-003 -->
---

<!-- RULE START: ERR-RETRY-001 -->
## Rule ERR-RETRY-001

**Domain**: code-quality
**Severity**: High
**Scope**: Component
**Mandatory**: false

### Trigger
When implementing retry logic for external calls or transient failures.

### Statement
Retries use exponential backoff with jitter, not fixed intervals. Backoff base is at least 100ms; jitter is random within a window to avoid thundering herd; growth multiplier is 2-3x.

### Violation
```python
for attempt in range(5):
    try:
        return call()
    except TransientError:
        time.sleep(1)  # fixed interval; thundering herd at scale
```

### Pass
```python
for attempt in range(5):
    try:
        return call()
    except TransientError:
        delay = min(30, (2 ** attempt) * 0.1) * (0.5 + random.random())
        time.sleep(delay)
```

### Enforcement
Code review. Retry libraries (tenacity, retry, polly) implement this correctly.

### Rationale
Fixed-interval retries synchronize and amplify upstream failures. Exponential backoff with jitter spreads the retry load and gives upstream room to recover.

<!-- RULE END: ERR-RETRY-001 -->
---

<!-- RULE START: ERR-RETRY-002 -->
## Rule ERR-RETRY-002

**Domain**: code-quality
**Severity**: Medium
**Scope**: Component
**Mandatory**: false

### Trigger
When implementing retry logic.

### Statement
Retry attempts are capped (typically 3-5). Infinite retry loops are forbidden. After the cap, the call fails through to the next layer of error handling (fallback, circuit break, error response).

### Violation
```python
while True:
    try: return call()
    except TransientError: continue
```

### Pass
```python
for attempt in range(5):
    try: return call()
    except TransientError: continue
raise ServiceUnavailable()
```

### Enforcement
Code review.

### Rationale
Unbounded retries hang the request, consume the worker, and never surface the failure to the caller.

<!-- RULE END: ERR-RETRY-002 -->
---

<!-- RULE START: ERR-TIMEOUT-001 -->
## Rule ERR-TIMEOUT-001

**Domain**: code-quality
**Severity**: High
**Scope**: Component
**Mandatory**: false

### Trigger
When making any external call (HTTP, DB, RPC, lock acquisition, queue receive).

### Statement
All external calls have explicit timeouts. Unbounded waits are forbidden. The library default is not acceptable as documentation: the timeout is passed at the call site or set via shared client config.

### Violation
```python
response = requests.get('https://api.example.com/data')  # no timeout
```

### Pass
```python
response = requests.get('https://api.example.com/data', timeout=5.0)
```

### Enforcement
Code review. Linter rule (ruff S113 for requests without timeout).

### Rationale
Bare external calls inherit library defaults that are often 'no timeout' or 'minutes'. One slow upstream stalls the whole worker pool.

<!-- RULE END: ERR-TIMEOUT-001 -->
---

<!-- RULE START: ERR-TIMEOUT-002 -->
## Rule ERR-TIMEOUT-002

**Domain**: code-quality
**Severity**: Medium
**Scope**: Component
**Mandatory**: false

### Trigger
When configuring timeout values for external calls.

### Statement
Timeout values are configurable (env var, config file, settings module). Hardcoded timeouts spread across the codebase are violations; one config controls them by environment and downstream-service.

### Violation
```python
response = requests.get(url, timeout=5)  # hardcoded everywhere
```

### Pass
```python
response = requests.get(url, timeout=settings.UPSTREAM_TIMEOUT_SECONDS)
```

### Enforcement
Code review.

### Rationale
Tuning timeouts during an incident is a 1-line config change when timeouts are configurable. Otherwise it is a code change, a deploy, and a delay.

<!-- RULE END: ERR-TIMEOUT-002 -->
---

<!-- RULE START: ERR-VALIDATION-001 -->
## Rule ERR-VALIDATION-001

**Domain**: code-quality
**Severity**: High
**Scope**: Component
**Mandatory**: false

### Trigger
When returning validation errors from an API.

### Statement
Validation errors are returned as structured responses with field-level errors and error codes. A flat string like 'Validation failed' is a violation; the response identifies which field failed, why, and a machine-readable code.

### Violation
```python
return {'error': 'Validation failed'}, 400
```

### Pass
```python
return {'errors': [
    {'field': 'email', 'code': 'INVALID_FORMAT', 'message': 'Not a valid email'},
    {'field': 'age', 'code': 'OUT_OF_RANGE', 'message': 'Must be 0-150'},
]}, 400
```

### Enforcement
Code review. Pydantic + FastAPI produces this shape automatically.

### Rationale
Structured validation errors let UIs highlight the bad field and let integrations handle errors programmatically. A bare string forces every consumer to parse.

<!-- RULE END: ERR-VALIDATION-001 -->
