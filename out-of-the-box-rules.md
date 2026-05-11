# Writ Public Rulebook: Out-of-the-Box Rule Inventory

Every rule listed here passes the enforceability test: an AI agent can make a binary pass/fail decision from the rule's trigger, statement, and violation fields without human interpretation.

- **Mandatory** rules are loaded every turn via `/always-on` and are never ranked. They are the safety invariants that cannot be ranked away.
- **Retrieved** rules are indexed by BM25 + vector and surfaced only when a query is relevant. They are guidance that should appear when the task matches.

**Total: 220 rules across 12 domains.**

The live Writ corpus also retains Writ-specific extensions on top of these 220 (ENF-PROC-*, FW-M2-*, PHP-*, PY-*, META-*, etc.), bringing the production count to 276 rules / 30 mandatory. This document is the *public* rulebook; see `HANDBOOK.md` for the full live state.

---

## 1. Security (the most vital domain)

A missed security rule is a shipped vulnerability. The mandatory set covers universal invariants; the retrieved set covers context-specific guidance.

### 1A. Injection Prevention (17 rules)

| Rule ID | Severity | What it enforces | Why it matters |
|---|---|---|---|
| `SEC-INJ-SQL-001` | critical | Parameterized queries only; no string concatenation or interpolation in SQL. | SQL injection remains the single most-exploited web vulnerability. Parameterization is the only structurally-safe pattern: it removes user-input-as-code as an attack surface rather than trying to sanitize it. |
| `SEC-INJ-SQL-002` | critical | ORM raw query methods require bound parameters. | ORM raw escape hatches (Django `raw()`, SQLAlchemy `text()`) reintroduce injection exactly where the developer thinks the ORM is protecting them. Binding closes the gap. |
| `SEC-INJ-SQL-003` | high | Stored procedure calls use parameterized inputs. | Stored procedures do not magically sanitize their inputs; concatenation into a `CALL` statement is still SQL injection. |
| `SEC-INJ-XSS-001` | critical | All user-supplied content rendered through framework escaping (React JSX, Blade `{{ }}`, Jinja2 `{{ }}`). | Framework auto-escaping is the structural defense against XSS. Bypassing it falls back to manual sanitization, which is almost never done correctly. |
| `SEC-INJ-XSS-002` | critical | No `dangerouslySetInnerHTML`, `v-html`, `{!! !!}`, Svelte `{@html}`, or equivalent raw-HTML render APIs without sanitization. | These APIs disable the framework's structural defense. If raw HTML is genuinely required, content must be sanitized through a vetted library (DOMPurify, HTMLPurifier). |
| `SEC-INJ-XSS-003` | high | DOM manipulation methods (`innerHTML`, `outerHTML`, `document.write`) prohibited with user data. | These are the vanilla-JS equivalent of `dangerouslySetInnerHTML`; same XSS surface, same defense. |
| `SEC-INJ-CMD-001` | critical | No shell command construction from user input; use subprocess argument lists, not `shell=True`. | Shell metacharacters in user input let attackers chain arbitrary commands. Argument-list invocation passes through the OS exec primitive directly, bypassing the shell. |
| `SEC-INJ-CMD-002` | high | System exec functions (`exec`, `eval`, `os.system`, `child_process.exec`) prohibited with dynamic strings. | Dynamic-string evaluation is arbitrary code execution by design. Replace with a lookup table or dispatch dict. |
| `SEC-INJ-PATH-001` | critical | File path operations validate against traversal (`../`, null bytes, symlink resolution). | Path traversal lets an attacker read or write anywhere the application has access. Canonicalize and validate against an allowlist root. |
| `SEC-INJ-LDAP-001` | high | LDAP filter construction uses parameterized APIs, not string formatting. | LDAP injection is structurally identical to SQL injection but harder to spot because LDAP syntax is unfamiliar to most developers. |
| `SEC-INJ-SSRF-001` | critical | Outbound HTTP from user-supplied URLs validates against an allowlist; no internal network access. | SSRF turns the server into a proxy for attacking internal infrastructure (cloud metadata endpoints, internal services). Allowlists are the only safe boundary. |
| `SEC-INJ-SSTI-001` | critical | Template rendering never accepts user input as the template string itself. | User-controlled templates are arbitrary code execution in the template engine. Templates are code, not data. |
| `SEC-INJ-HEADER-001` | high | HTTP response headers never constructed from unsanitized user input (CRLF injection). | CRLF injection lets attackers inject arbitrary headers and even response bodies, enabling cache poisoning and XSS. |
| `SEC-INJ-LOG-001` | medium | Log output sanitizes user input to prevent log injection and forging. | Log injection lets attackers forge log entries, confuse incident response, and hide their tracks. |
| `SEC-INJ-DESER-001` | critical | No deserialization of untrusted data (pickle, `unserialize`, `yaml.load` without SafeLoader, Java `ObjectInputStream`). | Unsafe deserializers execute attacker-controlled code during object reconstruction; pickle in particular is documented to be a remote-code-execution primitive. |
| `SEC-INJ-REDIR-001` | high | Redirect URLs validated against allowlist of internal paths; no open redirect from user-supplied URL parameters. | Open redirects are phishing accelerators: attackers send links that look like your domain but bounce to a credential-harvesting site. |
| `SEC-INJ-CSRF-001` | critical | State-changing requests validated against an anti-CSRF token (synchronizer token, double-submit cookie, or framework-native protection). | Cross-site request forgery causes the victim's authenticated browser to submit attacker-chosen requests. Modern frameworks ship CSRF protection; missing it is a clear violation. |

**Mandatory candidates**: `SEC-INJ-SQL-001`, `SEC-INJ-XSS-001`, `SEC-INJ-CMD-001`, `SEC-INJ-DESER-001`, `SEC-INJ-SSRF-001`, `SEC-INJ-CSRF-001`.

### 1B. Authentication (10 rules)

| Rule ID | Severity | What it enforces | Why it matters |
|---|---|---|---|
| `SEC-AUTH-HASH-001` | critical | Passwords hashed with bcrypt, argon2, or scrypt; never MD5, SHA-1, or SHA-256 alone. | Fast hashes are cracked at billions per second on commodity GPUs. Password hashes must be slow on purpose; bcrypt at cost 12 caps adversary throughput by six orders of magnitude. |
| `SEC-AUTH-HASH-002` | high | Salt is unique per user, generated by the hashing library, not custom. | Per-user salts defeat rainbow tables. Library-generated salts come from a CSPRNG; hand-rolled salts are routinely weak or shared. |
| `SEC-AUTH-TIMING-001` | high | Authentication comparisons use constant-time functions (`hmac.compare_digest`, timing-safe equals). | Timing attacks let a remote attacker peel a secret one byte at a time by observing micro-latency. Constant-time comparison closes the side channel structurally. |
| `SEC-AUTH-TOKEN-001` | critical | Session tokens generated with a CSPRNG (`secrets`, `crypto.randomBytes`), minimum 128 bits. | `random.random` is seeded by predictable system state. CSPRNGs source entropy from the kernel and have no recoverable state. |
| `SEC-AUTH-TOKEN-002` | high | Session tokens transmitted only over HTTPS, with Secure + HttpOnly + SameSite flags. | Secure stops MITM credential theft; HttpOnly stops XSS-driven cookie exfiltration; SameSite stops cross-site CSRF. All three are zero-cost browser-level defenses. |
| `SEC-AUTH-MFA-001` | medium | MFA secret storage encrypted at rest; TOTP window validates only current and adjacent periods. | A wide TOTP window expands the brute-force keyspace; plaintext secrets give a database leak full account takeover. |
| `SEC-AUTH-BRUTE-001` | high | Failed login attempts rate-limited per account and per IP (lockout or exponential backoff). | Credential stuffing is automated and cheap. Without limits, attackers try a billion known passwords in hours. |
| `SEC-AUTH-RESET-001` | high | Password reset tokens are single-use, time-limited (max 1 hour), and invalidated on password change. | A reset token without expiry is a permanent backdoor surviving email leaks and browser history. Single-use tokens stop replay attacks. |
| `SEC-AUTH-ENUM-001` | medium | Login and reset endpoints return identical responses for valid and invalid accounts. | Account enumeration powers targeted phishing and credential-stuffing prioritization. Uniform responses remove the oracle. |
| `SEC-AUTH-LOGOUT-001` | medium | Logout invalidates server-side session; token is not just cleared client-side. | A cookie-only logout leaves the session valid on any other device or in any captured copy. Server-side invalidation makes the credential genuinely unusable. |

**Mandatory candidates**: `SEC-AUTH-HASH-001`, `SEC-AUTH-TOKEN-001`.

### 1C. Authorization & Access Control (9 rules)

| Rule ID | Severity | What it enforces | Why it matters |
|---|---|---|---|
| `SEC-AUTHZ-ENFORCE-001` | critical | Every route or endpoint has an explicit authorization check; no "open by default". | Authorization missed by default is the most common access-control bug. Every endpoint must declare its policy explicitly; CI flags handlers that do not. |
| `SEC-AUTHZ-IDOR-001` | critical | Object access verified against the authenticated user's permissions, not just object ID existence. | Insecure direct object reference is an OWASP Top 10 staple because the loader-by-ID pattern is the default and the permission check is easy to omit. |
| `SEC-AUTHZ-PRIV-001` | high | Privilege escalation paths (role change, admin flag) require re-authentication. | A stolen session cookie is a credential. Re-auth on privilege-changing actions limits the damage: the attacker may read but cannot escalate without the original password. |
| `SEC-AUTHZ-SCOPE-001` | high | API tokens carry the minimum required scopes; no wildcard permissions. | Wildcard scopes turn any token leak into full account takeover. Minimum scopes contain the blast radius. |
| `SEC-AUTHZ-RBAC-001` | medium | Role checks happen at the service or controller layer, not only at the route layer. | Route-only authorization breaks the moment another caller (background job, internal RPC) reuses the underlying function. Place checks on the operation itself. |
| `SEC-AUTHZ-DEFAULT-001` | critical | New endpoints default to deny; access requires an explicit permission grant. | Deny-by-default is the only configuration that fails safe when a developer forgets to think about authorization. |
| `SEC-AUTHZ-TENANT-001` | critical | Multi-tenant queries filter by tenant ID at the data layer, not just the API layer. | Cross-tenant data leaks are the highest-impact authorization bug in SaaS: a single missing filter exposes every customer at once. Data-layer enforcement is the structural defense. |
| `SEC-AUTHZ-FUNC-001` | high | Administrative functions separated by endpoint path and middleware, not just UI visibility. | Hidden-not-disabled controls are routinely discovered via JS-bundle inspection or curl. Path-and-middleware separation is mechanically enforceable; UI hiding is not. |
| `SEC-AUTHZ-MASS-001` | critical | Model binding from user input uses explicit allowlists; no unguarded mass assignment from request body to model. | Mass assignment lets the caller set fields the developer never meant to be writable (role, is_admin, balance). An explicit allowlist at the binding layer is the structural defense. |

**Mandatory candidates**: `SEC-AUTHZ-ENFORCE-001`, `SEC-AUTHZ-IDOR-001`, `SEC-AUTHZ-DEFAULT-001`, `SEC-AUTHZ-MASS-001`.

### 1D. Input Validation & Sanitization (8 rules)

| Rule ID | Severity | What it enforces | Why it matters |
|---|---|---|---|
| `SEC-VAL-SERVER-001` | critical | All input validation happens server-side; client-side validation is UX only. | Every byte from the client is hostile until validated. Server-side validation is the only trust boundary that matters. |
| `SEC-VAL-TYPE-001` | high | Request payloads validated against a typed schema (Pydantic, Zod, JSON Schema, Marshmallow) before business logic. | Schemas turn validation from a pile of manual `if` statements into a single declarative source of truth that also generates docs, types, and OpenAPI. |
| `SEC-VAL-LENGTH-001` | high | String inputs have maximum length constraints; no unbounded text fields. | Unbounded fields are a denial-of-service vector (gigabyte payloads) and a database-bloat vector. Length caps are zero-cost and prevent both. |
| `SEC-VAL-RANGE-001` | medium | Numeric inputs validated against domain-appropriate ranges. | Unbounded numeric inputs are the root of negative-quantity refunds, integer overflows, and prices smaller than rounding error. |
| `SEC-VAL-FILE-001` | critical | File uploads validated by content (magic bytes), not just extension; stored outside the web root. | Extension and MIME-only checks are trivially spoofed. Content sniffing closes the spoof; out-of-web-root storage closes the direct-execute vector. |
| `SEC-VAL-REGEX-001` | medium | User-supplied regex patterns rejected or sandboxed (ReDoS prevention). | A catastrophic-backtracking regex can hang a worker for minutes on a single short input; a single-request denial of service. |
| `SEC-VAL-ENCODING-001` | high | Input decoded to canonical form before validation (double-encoding, mixed encoding attacks). | Encoding bypass is one of the oldest WAF-evasion tricks. Canonical-form validation removes the trick by collapsing all encodings before the check. |
| `SEC-VAL-ALLOW-001` | high | Validation uses allowlists, not blocklists, wherever the valid set is enumerable. | Allowlists fail closed: anything not on the list is rejected. Blocklists fail open: anything the author did not anticipate is allowed. |

**Mandatory candidates**: `SEC-VAL-SERVER-001`, `SEC-VAL-FILE-001`.

### 1E. Cryptography & Secrets (8 rules)

| Rule ID | Severity | What it enforces | Why it matters |
|---|---|---|---|
| `SEC-CRYPTO-KEY-001` | critical | No hardcoded secrets, API keys, passwords, or private keys in source code. | Hardcoded secrets end up in git history, CI logs, error messages, and container images. Once committed, a secret is effectively public and must be rotated. |
| `SEC-CRYPTO-KEY-002` | high | Secrets loaded from environment variables or a secret-management service, never from config files committed to VCS. | Even a "private" git repo is a much wider blast surface than a secrets manager. Pulling secrets at runtime keeps them out of the build artifact. |
| `SEC-CRYPTO-ALGO-001` | critical | Symmetric encryption uses AES-256-GCM or ChaCha20-Poly1305; no ECB mode, no DES/3DES, no RC4. | ECB preserves plaintext patterns (the "ECB penguin"); unauthenticated modes allow ciphertext modification. AEAD bundles confidentiality and integrity. |
| `SEC-CRYPTO-ALGO-002` | high | Asymmetric keys minimum RSA-2048 or Ed25519/ECDSA P-256+; no RSA-1024. | 1024-bit RSA is within practical attack reach of well-funded adversaries. Modern minimums keep keys secure across the lifetime of the data they protect. |
| `SEC-CRYPTO-RAND-001` | critical | Cryptographic operations use a CSPRNG; no `Math.random()`, `random.random()`, or `rand()` for security-sensitive values. | Predictable IVs and salts collapse the security of AEAD encryption (nonce reuse in GCM is catastrophic) and password hashing. The CSPRNG distinction is structural. |
| `SEC-CRYPTO-TLS-001` | high | TLS 1.2 minimum; TLS 1.0/1.1 disabled; cipher suite excludes known-weak ciphers. | TLS 1.0 and 1.1 carry known weaknesses (BEAST, POODLE, weak MACs). Raising the floor is configuration-only with no application impact. |
| `SEC-CRYPTO-CERT-001` | medium | Certificate validation not disabled in HTTP clients; no `verify=False` in production. | Disabling certificate validation removes the entire point of HTTPS: there is no longer any guarantee about who is on the other end. |
| `SEC-CRYPTO-IV-001` | high | IVs and nonces are unique per encryption operation, generated by a CSPRNG, never reused. | Nonce reuse in GCM is one of the most catastrophic crypto failures: an attacker who sees two GCM messages with the same key+nonce can recover plaintexts and forge new messages. |

**Mandatory candidates**: `SEC-CRYPTO-KEY-001`, `SEC-CRYPTO-RAND-001`.

### 1F. HTTP Security Headers & Transport (6 rules)

| Rule ID | Severity | What it enforces | Why it matters |
|---|---|---|---|
| `SEC-HDR-CSP-001` | high | Content-Security-Policy header is set; no `unsafe-inline` or `unsafe-eval` without documented justification. | CSP is defense-in-depth against XSS that survives a bypass of input escaping. A well-formed CSP downgrades a slipped-through XSS to a script that cannot load resources. |
| `SEC-HDR-CORS-001` | critical | `Access-Control-Allow-Origin` is never wildcard (`*`) for credentialed requests. | Wildcard origins with credentials let any malicious site read authenticated API responses. The explicit-origin requirement is the only structural defense. |
| `SEC-HDR-FRAME-001` | medium | `X-Frame-Options` or CSP `frame-ancestors` set to prevent clickjacking. | Clickjacking overlays a transparent frame of the target site over a decoy and tricks the user into clicking the framed UI. Frame-Options blocks the structural prerequisite. |
| `SEC-HDR-HSTS-001` | high | `Strict-Transport-Security` header with `max-age >= 31536000` on HTTPS responses. | HSTS instructs browsers to never speak HTTP to the host again, killing downgrade attacks. Zero-cost once HTTPS coverage is complete. |
| `SEC-HDR-TYPE-001` | medium | `X-Content-Type-Options: nosniff` set on all responses. | MIME sniffing turns user-uploaded files into XSS vectors by reinterpreting a misdeclared file as something else. The nosniff header structurally disables the sniff. |
| `SEC-HDR-REFERRER-001` | low | `Referrer-Policy` set to `no-referrer` or `strict-origin-when-cross-origin`. | Default referrer headers leak full URLs (including password-reset tokens and search queries) to advertising and analytics endpoints. |

### 1G. Rate Limiting & DoS Prevention (5 rules)

| Rule ID | Severity | What it enforces | Why it matters |
|---|---|---|---|
| `SEC-RATE-API-001` | high | Public API endpoints have rate limiting per client identity (API key, IP, or user). | Without rate limits, a single client can exhaust capacity for everyone else. Per-identity limits provide fairness and a per-tenant DoS floor. |
| `SEC-RATE-LOGIN-001` | high | Authentication endpoints rate-limited independently from general API limits. | Login endpoints are the highest-value attack surface; a per-account limit defeats credential stuffing of a target user, a per-IP limit defeats horizontal sweeps. |
| `SEC-RATE-UPLOAD-001` | high | File upload endpoints enforce size limits (both per-file and per-request body). | Unbounded upload endpoints are a direct DoS vector: a single 4 GB POST can exhaust memory or fill disk. Application-layer caps prevent the request from ever reaching that state. |
| `SEC-RATE-QUERY-001` | medium | Database queries triggered by user input have pagination and result-set limits. | An unbounded query is a database DoS waiting to happen: one user with a wide filter holds a worker and a connection for minutes. |
| `SEC-RATE-BATCH-001` | medium | Batch and bulk API endpoints cap items per request and enforce per-batch rate limits. | Batch endpoints amplify request cost without amplifying client cost. Capping batch size keeps the cost ratio bounded. |

### 1H. Data Protection & Privacy (6 rules)

| Rule ID | Severity | What it enforces | Why it matters |
|---|---|---|---|
| `SEC-DATA-PII-001` | critical | PII (emails, SSNs, phone numbers, addresses) never logged in plaintext. | Logs are the most-replicated artifact a production system produces: stdout, CloudWatch, Splunk, S3, backups, devops laptops. PII in logs is functionally a permanent leak. |
| `SEC-DATA-PII-002` | high | API responses exclude fields the requesting user is not authorized to see (no over-fetching). | Over-fetching is one of the most common privacy bugs: developers add a field for one consumer and forget it ships to every other consumer. Explicit serializers contain the blast radius. |
| `SEC-DATA-ENCRYPT-001` | high | Sensitive data encrypted at rest (database-level or field-level encryption). | Database leaks are the highest-impact security event a service can suffer. Field-level encryption raises the bar so a leak yields ciphertext, not records. |
| `SEC-DATA-MASK-001` | medium | Error responses and stack traces never expose internal paths, query text, or schema details to end users. | Stack traces in HTTP responses leak file paths, library versions, and code structure that aid reconnaissance. Generic messages plus correlation IDs preserve debuggability without exposing internals. |
| `SEC-DATA-RETAIN-001` | medium | Data retention policy enforced; no indefinite storage of user data without documented justification. | Long-retained data is a long-running liability: a leak today exposes data from years past. A retention policy bounds exposure structurally. |
| `SEC-DATA-EXPORT-001` | medium | Data export endpoints implement access controls and audit logging. | Bulk-export endpoints are the highest-leverage exfiltration paths in a compromised account. Explicit permissions plus audit logging plus rate limits provide defense-in-depth. |

**Mandatory candidates**: `SEC-DATA-PII-001`.

### 1I. Dependency & Supply Chain (4 rules)

| Rule ID | Severity | What it enforces | Why it matters |
|---|---|---|---|
| `SEC-DEP-AUDIT-001` | high | No known critical or high CVEs in direct dependencies (`npm audit`, `pip-audit`, `cargo audit`). | Most exploited vulnerabilities in modern services are dependency CVEs (Log4Shell, Spring4Shell). The audit step is mechanical and prevents the regression. |
| `SEC-DEP-LOCK-001` | medium | Lockfiles committed and used for deterministic builds (`package-lock.json`, `poetry.lock`, `Cargo.lock`). | Lockfiles make installs deterministic: identical inputs produce identical outputs. A typosquat or compromised version cannot enter the build without an explicit lockfile update. |
| `SEC-DEP-PIN-001` | medium | Dependencies pinned to exact versions or narrow ranges, not open-ended (`^`, `~`, `*`). | Open-ended versions silently take new releases on every install, which has historically included malicious or breaking changes. Narrow ranges plus a lockfile bound the surprise. |
| `SEC-DEP-REVIEW-001` | low | New dependency additions documented with justification in PR description. | Adding a dependency is a long-term commitment to a third party's security posture. The review forces a deliberate choice and creates an artifact for later incident response. |

**Security domain total: 73 rules. 16 mandatory, 57 retrieved.**

---

## 2. Clean Code & Code Quality (25 rules)

| Rule ID | Severity | What it enforces | Why it matters |
|---|---|---|---|
| `CLEAN-NAME-001` | medium | Functions, variables, and classes use descriptive names; no single-letter names outside loop counters and lambdas. | Names are the reader's shortest path to intent. Cryptic names force re-deriving meaning every time the code is read. |
| `CLEAN-NAME-002` | medium | Boolean variables and functions prefixed with `is`/`has`/`can`/`should` or equivalent. | Predicate names let the reader scan the condition as English. `if user.active:` reads correctly; `if user.status:` could mean anything. |
| `CLEAN-FUNC-001` | high | Functions do one thing; no function both mutates state and returns a computed value (Command-Query Separation). | CQS makes side effects visible at the call site. A "getter" that mutates is a landmine: every caller has hidden persistence semantics it must reason about. |
| `CLEAN-FUNC-002` | medium | Functions stay at or below 50 lines of logic (excluding declarations and comments). | Long functions hide the shape of the work. Decomposed code reads like a table of contents and lets the reader drill in only where needed. |
| `CLEAN-FUNC-003` | medium | Functions accept at most 4 positional parameters; beyond that, use an options or config object. | Long parameter lists are positional-coupling hazards: callers mis-order arguments, and adding a parameter ripples through every call site. |
| `CLEAN-FUNC-004` | medium | No flag arguments that switch function behavior; split into separate functions. | Flag arguments hide that the function is two functions in disguise. Named alternatives make the choice explicit at the call site. |
| `CLEAN-NEST-001` | high | Maximum 3 levels of nesting; deeper code extracted via early returns or helper functions. | Deeply nested code forces the reader to track too many simultaneous conditions. Early returns flatten the structure into the happy path. |
| `CLEAN-COMMENT-001` | medium | Comments explain WHY the code is the way it is (constraints, invariants, surprising business rules), not WHAT it does. | Restating-the-code comments rot the moment the code changes. WHY-comments stay useful because the constraint outlives the syntax. |
| `CLEAN-COMMENT-002` | medium | No commented-out code committed; use version control history. | Commented-out code is dead weight that confuses readers and bloats diffs. Git remembers; the file does not need to. |
| `CLEAN-DEAD-001` | medium | No unreachable code, unused imports, or unused variables. | Dead code distracts readers and rots over time. Removing it is free and improves the signal-to-noise ratio. |
| `CLEAN-MAGIC-001` | high | No magic numbers or strings; extract to named constants with domain context. | A named constant explains the value at use site and definition. Magic literals force the reader to derive the meaning by triangulating with adjacent code. |
| `CLEAN-RETURN-001` | medium | Functions return a single, predictable type; no `str-or-None-or-list` returns. | Multiple return types push the caller into ad-hoc type checks at every call site. Single-type returns let the type system carry the contract. |
| `CLEAN-SIDE-001` | high | Functions named as getters or computers (`get_*`, `compute_*`, `to_*`, `format_*`) have no side effects. | When name and behavior disagree, the caller's mental model is wrong. Side-effect-free getters are safe to call anywhere. |
| `CLEAN-ERR-001` | high | No empty catch or except blocks; at minimum log the error. | Silent exception swallowing turns a stack trace in monitoring into a mystery failure that surfaces minutes or hours later. |
| `CLEAN-ERR-002` | high | Catch specific exceptions, not bare `except` or `catch(Exception)`. | Bare catches mask programming errors as domain errors. Specific catches keep programming bugs visible. |
| `CLEAN-ERR-003` | medium | Error messages include context (what was being attempted, with what input). | Context-rich errors are the on-call engineer's first line of defense. Bare messages force a code dive to figure out what went wrong. |
| `CLEAN-ASSERT-001` | medium | Assertions are for invariants only, never for input validation or control flow. | Stripped assertions in production silently let the bad path proceed. Real validation belongs in real checks; assertions are developer-facing "this should be impossible" guards. |
| `CLEAN-COUPLING-001` | high | Modules depend on abstractions (interfaces, protocols), not concrete implementations. | Hard-coded dependencies make code untestable and untransferable. Abstractions let the module work against any conforming implementation. |
| `CLEAN-COUPLING-002` | medium | No circular imports or circular module dependencies. | Cycles make the dependency graph un-orderable and the modules un-testable in isolation. |
| `CLEAN-FORMAT-001` | low | Formatting enforced by a configured formatter (Prettier, Black, rustfmt); no manual style debates. | Formatter wars consume engineering time without product value. Delegate the entire decision to a tool and move on. |
| `CLEAN-TODO-001` | low | TODO/FIXME/HACK comments include a ticket/issue reference or author and date. | Untracked TODOs accumulate into a graveyard that no one cleans. Tracking forces the comment to either become work or be deleted. |
| `CLEAN-LOG-001` | medium | Structured logging (JSON or key-value) with severity levels, not print statements. | Structured logs are queryable, filterable, and routable. `print()`-style logs require regex parsing and lose context when handlers change. |
| `CLEAN-LOG-002` | medium | Log messages include a correlation or request ID for traceability. | Distributed systems are only debuggable when logs across services share an identifier. The correlation ID is the join key for an incident. |
| `CLEAN-BOOL-001` | medium | No boolean comparisons to `True`/`False` literal; use truthy/falsy directly. | Explicit comparison with a literal adds noise without adding precision. The truthy/falsy interpretation is the convention. |
| `CLEAN-TERNARY-001` | low | Nested ternary operators prohibited; use `if`/`else` blocks. | Nested ternaries collapse intent into a riddle. Block form is verbose but legible. |

---

## 3. DRY Principle (8 rules)

| Rule ID | Severity | What it enforces | Why it matters |
|---|---|---|---|
| `DRY-DUP-001` | high | No duplicated logic blocks of 5 or more lines; extract to a shared function. | Duplication multiplies bug surface: a fix in one copy leaves the others wrong. Extraction is the structural defense. |
| `DRY-DUP-002` | medium | No duplicated constant values across files; centralize in a constants or config module. | Scattered constants drift the moment business needs change. One canonical definition makes a single edit the only edit. |
| `DRY-DUP-003` | medium | No copy-pasted validation logic; share via schema definition or validator function. | Validation drift across endpoints leads to one endpoint accepting input another rejects. Shared schemas keep the contract uniform. |
| `DRY-CONFIG-001` | high | Configuration values defined once (env var, config file, constant), not scattered. | Config drift breaks the assumption that one place controls behavior. A single source of truth restores the invariant. |
| `DRY-CONFIG-002` | medium | Feature flags defined in a single registry, not inline boolean checks. | Scattered flag checks lose the ability to flip a flag in one place. Centralization is the structural defense for the next change. |
| `DRY-TEMPLATE-001` | medium | Repeated UI patterns extracted to shared components, not copied between views. | Copy-pasted UI fragments drift visually and behaviorally. A shared component anchors the pattern. |
| `DRY-QUERY-001` | medium | Common database queries wrapped in repository or DAO methods, not inlined at call sites. | Inlined queries duplicate filter logic and indexing assumptions. A repository method holds the canonical form. |
| `DRY-TYPE-001` | medium | Shared types or interfaces defined once and imported, not redeclared in each module. | Drifting type definitions create silent mismatches at module boundaries. A single source aligns every consumer. |

---

## 4. SOLID Principles (12 rules)

| Rule ID | Severity | What it enforces | Why it matters |
|---|---|---|---|
| `SOLID-SRP-001` | high | Each class has exactly one reason to change; no class handling both HTTP parsing and business logic. | A class that knows about too many concerns changes for too many reasons. Single-responsibility classes evolve independently. |
| `SOLID-SRP-002` | medium | Controller and handler functions delegate to a service layer; no business logic in route handlers. | Business logic in controllers is untestable without HTTP plumbing and invisible to non-HTTP callers (jobs, CLIs). |
| `SOLID-SRP-003` | medium | Data access separated from business rules (repository pattern or equivalent). | Mixing query syntax into services couples them to an ORM. The repository layer is the seam where storage technology can change. |
| `SOLID-OCP-001` | medium | Extension via composition, strategy, or plugin hooks, not modification of existing classes. | Closed-for-modification is the structural defense against regression: existing code paths keep working when new variants ship. |
| `SOLID-OCP-002` | medium | Switch/match on type replaced by polymorphism when there are more than 3 branches and types are extensible. | Long type switches mean each new type requires editing every dispatcher. Polymorphism puts type-specific logic with the type. |
| `SOLID-LSP-001` | high | Subclasses do not weaken preconditions or strengthen postconditions of their parent. | LSP violations turn polymorphism into a runtime trap: code that worked against the parent breaks unpredictably with a subclass. |
| `SOLID-LSP-002` | medium | Overridden methods maintain the parent's return type contract (no surprise `None` returns). | Return-type drift in overrides breaks every caller that assumed the parent's contract. |
| `SOLID-ISP-001` | medium | Interfaces or protocols contain only methods their consumers use; no fat interfaces. | Fat interfaces force consumers to depend on methods they do not use, propagating breaking changes through every implementation. |
| `SOLID-ISP-002` | medium | Optional method implementations (raising `NotImplementedError`) indicate the interface should be split. | `NotImplementedError` in production is a runtime time bomb. The structural defense is a narrower interface. |
| `SOLID-DIP-001` | high | High-level modules import abstractions (protocols, interfaces), not concrete implementations. | Concrete dependencies make business logic untestable, untransferable, and tightly coupled to vendor decisions. |
| `SOLID-DIP-002` | medium | Dependencies injected via constructor or factory, not instantiated inside business logic. | Injection makes dependencies visible and replaceable. Direct construction hides them and freezes substitutability. |
| `SOLID-DIP-003` | medium | Framework-specific types do not leak into domain logic (no Django ORM in service layer, no Express `req` in business module). | Framework types in domain code make every method untestable without the framework and prevent reuse from non-framework callers. |

---

## 5. Architecture & Design Patterns (15 rules)

| Rule ID | Severity | What it enforces | Why it matters |
|---|---|---|---|
| `ARCH-LAYER-001` | high | Layer boundaries enforced: presentation → service → data access; no skipping layers. | Layer skipping defeats the purpose of layers: business logic ends up duplicated across controllers, data access scattered, and isolated testing impossible. |
| `ARCH-LAYER-002` | medium | Domain models have no framework imports; framework types converted at boundaries. | Framework-coupled domain models drag the framework into every test, reuse, and refactor. Plain models are portable. |
| `ARCH-BOUNDARY-001` | high | External service calls wrapped in an adapter or client class; no raw HTTP calls in business logic. | Raw external calls in business code couple every caller to the vendor's API shape, error model, and retry semantics. Adapters isolate that surface. |
| `ARCH-BOUNDARY-002` | medium | Third-party library usage concentrated in adapter modules, not spread across the codebase. | Concentrated library use trades a one-line import for the ability to migrate the library later. |
| `ARCH-EVENT-001` | medium | Cross-domain communication uses events or messages, not direct method calls across bounded contexts. | Direct calls tangle bounded contexts: changes in one ripple to others. Events keep contexts independently deployable and testable. |
| `ARCH-DTO-001` | medium | API request and response shapes defined as explicit DTOs, not raw dicts passed through layers. | Raw dicts hide the contract between layers and propagate typos as runtime errors. DTOs make the contract machine-checkable. |
| `ARCH-MIGRATION-001` | high | Database schema changes use versioned migrations, not manual DDL. | Versioned migrations make schema state reproducible, reviewable, and rollback-able. Manual DDL turns the schema into a folk artifact. |
| `ARCH-MIGRATION-002` | medium | Migrations are reversible (have both up and down); irreversible changes documented. | Reversible migrations preserve the option to roll back without data loss. Irreversible changes are sometimes necessary but explicit decisions. |
| `ARCH-STATE-001` | high | Shared mutable state protected by explicit synchronization; no unguarded global mutations. | Unguarded concurrent mutation produces nondeterministic bugs that are nearly impossible to reproduce. Synchronization or immutability removes the entire bug class. |
| `ARCH-STATE-002` | medium | Application state management uses a single pattern (Redux, Zustand, context) per project, not mixed. | Mixed state-management produces state that lives in multiple places at once and drifts. One pattern is the structural defense. |
| `ARCH-IDEMPOTENT-001` | high | API write endpoints are idempotent; use idempotency keys for charges, emails, notifications. | Retries are universal in distributed systems. Idempotency keys turn "safe to retry" from hope into guarantee. |
| `ARCH-ASYNC-001` | high | Async functions awaited at all call sites; no fire-and-forget without explicit justification. | Floating async work loses errors and timing. The await (or supervised spawn) is the structural defense. |
| `ARCH-ASYNC-002` | medium | No blocking calls (sync I/O, sleep, CPU-bound loops) inside async event loops. | A single blocking call inside the event loop stalls every concurrent task. Async I/O preserves the concurrency model. |
| `ARCH-ENV-001` | medium | Environment-specific behavior controlled by configuration, not code branches on environment name. | Env-name branches couple code to a specific environment topology. Config-driven behavior travels: the same code runs anywhere if the config is right. |
| `ARCH-FEATURE-001` | medium | Feature flags have expiration dates and cleanup plans; no permanent flags. | Eternal feature flags accumulate as branches that never converge. Sunset dates create momentum to remove them. |

---

## 6. Testing (20 rules)

| Rule ID | Severity | What it enforces | Why it matters |
|---|---|---|---|
| `TEST-EXIST-001` | high | Every public function or method has at least one test. | Untested public APIs are unverified APIs: every caller is the first to find the bug. The test is the executable contract. |
| `TEST-EXIST-002` | high | Every API endpoint has at least one integration test. | Integration tests catch bugs that unit tests cannot: middleware ordering, request parsing, response shape, status codes, content negotiation. |
| `TEST-NAME-001` | medium | Test names describe the scenario and expected outcome, not just the function name. | Failing test names are read in CI output, incident timelines, and stack traces. Descriptive names diagnose the failure without opening the test file. |
| `TEST-ASSERT-001` | high | Every test has at least one assertion; no assertion-free tests. | An assertion-free test silently passes regardless of what the code does. The bug it claims to cover is invisible. |
| `TEST-ASSERT-002` | medium | Assertions are specific (`assertEquals`, not `assertTrue` on a boolean expression). | Specific assertions print diffs on failure: actual vs expected. Boolean assertions print only "False is not True", which says nothing. |
| `TEST-ISOLATE-001` | high | Tests do not depend on execution order or shared mutable state between tests. | Order-dependent tests pass in CI and fail in parallel runs (or vice versa). The flake is structural; the fix is per-test isolation. |
| `TEST-ISOLATE-002` | high | Tests do not make real network calls; external dependencies mocked or stubbed. | Tests that hit real services are slow, flaky, and side-effect-laden. Mocking is the structural defense. |
| `TEST-ISOLATE-003` | medium | Test database state reset between tests (transaction rollback, fixture reload, or fresh DB). | Leaked state between tests is the canonical source of order-dependent flakiness. Per-test isolation removes the entire class of bug. |
| `TEST-FIXTURE-001` | medium | Test fixtures or factories used for setup; no manual object construction repeated across tests. | Inline-constructed objects drift across tests; one new required field updates twenty tests. Factories centralize the construction. |
| `TEST-FIXTURE-002` | medium | Fixtures are minimal; only set up what the test needs, no kitchen-sink setup. | Bloated setup obscures intent and slows the suite. Minimal fixtures keep tests legible and fast. |
| `TEST-EDGE-001` | high | Error paths tested: invalid input, missing data, permission denied, timeout. | Happy-path-only suites prove the code works when nothing goes wrong. Error paths are where most production bugs live. |
| `TEST-EDGE-002` | medium | Boundary values tested: empty collections, zero, max int, empty string, null. | Boundary bugs are the canonical source of off-by-one errors and overflow surprises. Explicit boundary tests are the structural defense. |
| `TEST-EDGE-003` | medium | Concurrent access paths tested where applicable (race conditions, deadlocks). | Concurrency bugs only surface under contention. A single-threaded test of concurrent code proves nothing about correctness under load. |
| `TEST-MOCK-001` | medium | Mocks verify behavior (was this called with these args?), not just existence. | A mock without behavior assertions only proves "no exception thrown". Behavior assertions prove the integration with the mocked collaborator. |
| `TEST-MOCK-002` | medium | Mock return values are realistic (match actual API or service response shapes). | Drift between mock and reality lets tests pass while production breaks. Realistic mocks keep the gap closed. |
| `TEST-COVERAGE-001` | medium | Critical business logic paths have at least 80% branch coverage. | Coverage targets create a baseline that prevents tests from being silently abandoned. 80% branch is enough to catch most regressions without wasting effort on trivial code. |
| `TEST-PERF-001` | low | Performance-sensitive paths have benchmark tests with a documented baseline. | Performance regressions slip in silently as features land. Benchmarks turn "feels slow" into a measurable, gateable signal. |
| `TEST-REGRESSION-001` | high | Every bug fix accompanied by a regression test that reproduces the bug. | Bug fixes without regression tests guarantee the bug returns. The test is the structural defense against re-introduction. |
| `TEST-SNAPSHOT-001` | low | Snapshot tests explicitly reviewed on update; no blind snapshot updates. | Blind snapshot updates erode the test's value: it becomes a record of what the code does, not a check that it does the right thing. |
| `TEST-CI-001` | medium | All tests pass in CI before merge; no "known failing" tests left in the suite. | A green-with-skips suite is a yellow signal that gets ignored. Either the test is meaningful (fix it) or it is not (remove it). |

---

## 7. Error Handling & Resilience (12 rules)

| Rule ID | Severity | What it enforces | Why it matters |
|---|---|---|---|
| `ERR-HANDLE-001` | high | Every external call (HTTP, DB, file I/O) wrapped in error handling with a timeout. | Unhandled external failures propagate as raw library exceptions to callers that cannot recover or even identify them. Wrapping is the structural defense. |
| `ERR-HANDLE-002` | high | Errors propagated with context; not swallowed or re-raised bare. | Unchained exceptions hide the root cause behind a generic wrapper. The original stack trace is the most valuable artifact in an incident. |
| `ERR-HANDLE-003` | medium | User-facing error messages are helpful but do not expose internals. | Internal-detail leaks aid reconnaissance and confuse legitimate users. A clear public message plus an internal correlation ID balances both audiences. |
| `ERR-RETRY-001` | high | Retry logic uses exponential backoff with jitter, not fixed intervals. | Fixed-interval retries synchronize and amplify upstream failures. Exponential backoff with jitter spreads retry load and gives upstream room to recover. |
| `ERR-RETRY-002` | medium | Retry attempts capped (max 3-5); no infinite retry loops. | Unbounded retries hang the request, consume the worker, and never surface the failure to the caller. |
| `ERR-CIRCUIT-001` | medium | Repeated failures to an external service trigger a circuit breaker (stop calling, return fallback or error). | Without a breaker, every request waits the timeout before failing; the failing service drags down everything that calls it. |
| `ERR-FALLBACK-001` | medium | Critical paths have defined fallback behavior documented in code or comments. | Fallback decisions are part of the design, not an emergent property. Documented fallback paths preserve the critical workflow under partial outage. |
| `ERR-TIMEOUT-001` | high | All external calls have explicit timeouts; no unbounded waits. | Bare external calls inherit library defaults that are often "no timeout" or "minutes". One slow upstream stalls the whole worker pool. |
| `ERR-TIMEOUT-002` | medium | Timeout values configurable, not hardcoded. | Tuning timeouts during an incident is a one-line config change when configurable; otherwise it is a code change, a deploy, and a delay. |
| `ERR-GRACEFUL-001` | high | Application handles SIGTERM/SIGINT gracefully (drain connections, flush buffers, exit clean). | Graceful shutdown preserves in-flight requests and avoids dropped writes on deployment. Hard-kill turns every deploy into a small outage. |
| `ERR-GRACEFUL-002` | medium | Background jobs and workers have shutdown hooks that complete in-progress work. | Dropped jobs on shutdown produce silent data inconsistency. Acknowledgement-after-complete plus shutdown hooks preserve the at-least-once contract. |
| `ERR-VALIDATION-001` | high | Validation errors returned as structured error responses (field-level errors, error codes). | Structured validation errors let UIs highlight the bad field and let integrations handle errors programmatically. A bare string forces every consumer to parse. |

---

## 8. Performance & Caching (15 rules)

| Rule ID | Severity | What it enforces | Why it matters |
|---|---|---|---|
| `PERF-QUERY-001` | critical | No N+1 database query patterns; use joins, eager loading, or batch fetching. | N+1 is the single most common database performance bug. A list page with 100 items can issue 100+ extra queries, scaling with traffic. |
| `PERF-QUERY-002` | high | Database queries on columns used in WHERE or JOIN have corresponding indexes. | Unindexed queries are O(N) on table size; indexed queries are O(log N). The difference becomes catastrophic as data grows. |
| `PERF-QUERY-003` | medium | SELECT queries specify columns, not `SELECT *`; no unnecessary data transfer. | Wide selects compound at scale: 50KB rows fetched 1000 times is 50MB of unused data on the wire. Narrow selects are free wins. |
| `PERF-QUERY-004` | medium | Pagination required for list endpoints that could return unbounded results. | An unbounded list endpoint is a database DoS waiting to happen. Bounded pagination caps the worst case at the API layer. |
| `PERF-CACHE-001` | high | Cache keys include all parameters that affect the cached value; no stale cross-user cache hits. | Stale cross-user cache hits are at best a wrong-data bug and at worst a data-leak vulnerability. Complete cache keys close the gap. |
| `PERF-CACHE-002` | high | Cache entries have an explicit TTL; no indefinite caching without invalidation strategy. | Indefinite cache becomes a parallel database that drifts. TTL provides a freshness ceiling even when explicit invalidation fails. |
| `PERF-CACHE-003` | medium | Cache invalidation on write is explicit and documented; no "hope it expires" strategy. | TTL-only invalidation leaves staleness windows that produce visible bugs. Explicit invalidation closes the window. |
| `PERF-CACHE-004` | medium | Cache stampede mitigated (lock, probabilistic early expiration, or background refresh). | A stampeded cache turns the protected resource into the bottleneck precisely when it most needs protection. |
| `PERF-MEM-001` | high | Large collections processed via streaming or iteration, not loaded entirely into memory. | In-memory loading scales with data size; streaming scales with working-set size. The difference is between OOM and steady operation. |
| `PERF-MEM-002` | medium | Object references released after use in long-running processes; no memory leak patterns. | Memory leaks turn long-running processes into delayed crashes. Bounded structures keep memory predictable. |
| `PERF-ASYNC-001` | high | I/O-bound operations use async or non-blocking calls, not synchronous blocking. | Sync I/O in an async loop stalls every other concurrent request on that worker. Async preserves the concurrency model. |
| `PERF-BATCH-001` | medium | Multiple independent I/O operations run in parallel (`Promise.all`, `asyncio.gather`, goroutines). | Sequential awaiting is N × latency when the work is parallelizable. Parallel I/O is max(latency). |
| `PERF-LAZY-001` | medium | Expensive computations deferred until needed (lazy loading, on-demand initialization). | Eager work at startup costs the user nothing they will use. Lazy initialization amortizes cost across actual demand. |
| `PERF-BUNDLE-001` | medium | Frontend assets bundled and minified; no uncompressed JS/CSS in production. | Unbundled assets multiply HTTP round-trips and shipping bytes. Bundling and minification are zero-effort wins at deploy time. |
| `PERF-IMAGE-001` | low | Images served in modern formats (WebP, AVIF) with appropriate dimensions and lazy loading. | Image bytes dominate frontend payload. Modern formats and right-sizing cut payload by 50-80%; lazy loading defers off-screen cost. |

---

## 9. Scaling & Infrastructure (10 rules)

| Rule ID | Severity | What it enforces | Why it matters |
|---|---|---|---|
| `SCALE-STATELESS-001` | high | Application processes are stateless; session data stored in an external store (Redis, DB), not in-process memory. | Stateless processes scale horizontally: any worker can serve any request. Stateful processes pin the user to one machine, lose state on restart, and fail to scale beyond one node. |
| `SCALE-STATELESS-002` | medium | File storage uses object storage (S3, GCS, Azure Blob), not the local filesystem. | Local filesystem storage is invisible to other workers and disappears on container restart. Object storage is the structural fix. |
| `SCALE-QUEUE-001` | high | Long-running operations dispatched to a background queue, not executed in the request cycle. | Long-running synchronous work blocks the worker, hits client timeouts, and risks loss on deploy. Background queues decouple submission from completion. |
| `SCALE-QUEUE-002` | medium | Queue consumers are idempotent; duplicate delivery does not corrupt state. | Message redelivery is normal in distributed queues. Idempotent consumers handle it; non-idempotent ones produce silent data corruption. |
| `SCALE-DB-001` | high | Database connections pooled with size limits, not opened per request. | Per-request connections are slow (handshake overhead), exhaust the DB's connection limit at peak, and fail under load. Pooling is the structural defense. |
| `SCALE-DB-002` | medium | Read replicas used for read-heavy queries where eventual consistency is acceptable. | Reads dominate most workloads. Routing them to replicas offloads the primary and lets read capacity scale independently. |
| `SCALE-HEALTH-001` | high | Health check endpoint verifies actual service readiness (DB connection, critical dependencies). | A trivial health check turns "service ready" into "process running". The load balancer keeps sending traffic to a worker that cannot serve. |
| `SCALE-HEALTH-002` | medium | Readiness and liveness probes separated (ready = can serve; live = process not stuck). | Conflating ready and live causes spurious pod restarts or zombie rotation. Separation matches Kubernetes semantics. |
| `SCALE-CONFIG-001` | medium | Configuration supports environment-based overrides without code changes. | Hardcoded environment values force a build per environment and produce drift between staging and prod. |
| `SCALE-MIGRATE-001` | high | Database migrations are backwards-compatible (old code can run against new schema during rolling deploy). | Forward-only migrations break rolling deploys: half the pods see the new schema, half the old. Phased migrations preserve the invariant that any code version works. |

---

## 10. API Design (12 rules)

| Rule ID | Severity | What it enforces | Why it matters |
|---|---|---|---|
| `API-REST-001` | medium | HTTP methods match semantics (GET reads, POST creates, PUT/PATCH updates, DELETE deletes). | Method semantics drive correctness for caches, retries, and CSRF protections. A GET that deletes can be triggered by a link preview. |
| `API-REST-002` | medium | Resource URLs are nouns, not verbs (`/users`, not `/getUsers`). | Noun-based URLs let the method carry the verb. The URL identifies the resource; the method says what to do with it. |
| `API-STATUS-001` | high | Response status codes match the outcome (201 created, 404 not found, 422 validation, 500 server error). | Status codes are the integration contract for clients, monitors, and load balancers. Mismatched codes break retries, alerts, and circuit breakers. |
| `API-STATUS-002` | medium | 5xx errors never caused by invalid user input; those are 4xx. | 5xx tagging triggers paging and dashboard alerts. Misclassifying 4xx as 5xx floods the incident channel with non-incidents. |
| `API-VERSION-001` | medium | API versioning strategy defined and enforced (URL path, header, or query param). | Versioning lets the API evolve without breaking existing clients. Unversioned APIs make every change a coordinated client upgrade. |
| `API-PAGINATION-001` | high | List endpoints paginated with a consistent cursor or offset scheme and total count. | Pagination contains the API's worst-case response size. Consistent schemes let one client library work across every endpoint. |
| `API-PAGINATION-002` | medium | Default page size capped; maximum page size enforced server-side. | Server-side caps prevent a single request from exhausting capacity. The default keeps responses fast for the common case. |
| `API-ERROR-001` | high | Error responses follow a consistent schema (error code, message, field-level details). | Consistent error schemas let one client error-handler work everywhere. Inconsistent schemas force per-endpoint parsing. |
| `API-ERROR-002` | medium | Error messages are actionable; tell the caller what to fix, not just what failed. | Actionable errors halve the time-to-fix for integration partners. Bare messages force them to grep the source. |
| `API-CONTRACT-001` | high | API request and response schemas documented (OpenAPI, JSON Schema, or framework equivalent). | Hand-written docs drift. Generated docs stay in sync because they are the code. |
| `API-BREAKING-001` | high | Breaking API changes versioned; no silent contract changes. | Silent breakage is invisible to the team that ships and disastrous to the team that consumes. Versioning makes the contract visible. |
| `API-IDEMPOTENT-001` | medium | PUT and DELETE are idempotent; repeated calls produce the same result. | Network retries are universal. Idempotent PUT/DELETE makes retries safe; non-idempotent versions risk duplicate-state bugs. |

---

## 11. Development Lifecycle & Process (10 rules)

These are the Writ workflow rules: the process keeper.

| Rule ID | Severity | What it enforces | Why it matters |
|---|---|---|---|
| `PROC-PLAN-001` | high | Work mode requires a written plan before code; plan covers files, analysis, rules applied, capabilities. | A written plan exposes scope creep before code lands. The plan is also the artifact a reviewer reads first to know what to evaluate against. |
| `PROC-TEST-001` | high | Test skeletons written and approved before implementation. | Test-first ensures tests describe the contract independent of the implementation. Test-after risks tests that codify whatever the implementation happens to do. |
| `PROC-REVIEW-001` | medium | Code reviewed by at least one other person (or reviewer agent) before merge. | A second pair of eyes catches scope errors, missing tests, and security oversights that the author normalized to. The check is cheap relative to fixing in production. |
| `PROC-COMMIT-001` | medium | Commit messages follow a conventional format (`type: subject`) with a body for non-trivial changes. | Commit messages are read by every future engineer and during every incident. The 30 seconds spent writing a clear message saves hours later. |
| `PROC-BRANCH-001` | low | Feature branches named with a ticket or issue reference. | Traceable branch names link code to issue tracker to release notes. Untraceable names break the audit trail. |
| `PROC-CHANGELOG-001` | medium | User-facing changes documented in a changelog or release notes. | Changelogs are the contract with consumers: they can plan integrations from a written record, not from reverse-engineering deploys. |
| `PROC-DEPLOY-001` | high | Production deploys go through a CI/CD pipeline; no manual deployments. | Pipelined deploys are reproducible, gated, and auditable. Manual deploys produce drift, skip checks, and have no rollback. |
| `PROC-ROLLBACK-001` | high | Deployment strategy supports rollback (blue-green, canary, or feature flag). | Rollback is the most important property of the deployment system. Without it, every deploy is a one-way bet. |
| `PROC-ENV-001` | medium | Production credentials never shared in code, chat, or tickets; use secret management. | Once a credential is in a chat scroll, it lives forever in every chat client, every backup, and every export. Secret managers eliminate the durable exposure. |
| `PROC-INCIDENT-001` | medium | Post-incident review produces action items with owners and deadlines. | Untracked retro actions guarantee the incident repeats. Tracked actions are the difference between learning and re-learning. |

---

## 12. Documentation (8 rules)

| Rule ID | Severity | What it enforces | Why it matters |
|---|---|---|---|
| `DOC-API-001` | high | Public API endpoints have request and response documentation updated with each change. | Drifting API docs erode trust in the documentation overall. Generated docs solve this by construction. |
| `DOC-README-001` | medium | Repository README includes setup instructions that work on a clean machine. | A working README is the cheapest onboarding investment; tribal knowledge is the most expensive. |
| `DOC-ARCH-001` | medium | Architecture decisions recorded in ADRs or an equivalent decision log. | Undocumented decisions cost twice: the original deliberation is lost, and the next change repeats the analysis. |
| `DOC-INLINE-001` | medium | Complex algorithms have inline comments explaining the approach, not the syntax. | Algorithmic intent is opaque from syntax alone. A short why-comment saves the next reader the derivation. |
| `DOC-TYPE-001` | high | Public functions have type annotations (TypeScript types, Python type hints, Go types). | Types are the most compact, machine-checked documentation available. They catch bugs at edit time and document the contract for free. |
| `DOC-TYPE-002` | medium | Return types are explicit; no implicit `Any`, `unknown`, or `interface{}`. | Implicit `Any` defeats the type system. Explicit return types ensure the checker actually validates the contract. |
| `DOC-CONFIG-001` | medium | Configuration options documented with defaults, valid ranges, and effects. | Undocumented config is dark magic: nobody knows what to tune in an incident, and the wrong value causes silent failure. |
| `DOC-ONBOARD-001` | low | New developer onboarding documented (local setup, test run, deploy to staging). Advisory only; not enforceable per-file. | Documented onboarding compounds: each new hire improves it. Tribal onboarding stays expensive every cycle. |

---

## Summary

| Domain | Retrieved | Mandatory | Total |
|---|---:|---:|---:|
| Security | 57 | 16 | 73 |
| Clean Code | 25 | 0 | 25 |
| DRY | 8 | 0 | 8 |
| SOLID | 12 | 0 | 12 |
| Architecture | 15 | 0 | 15 |
| Testing | 20 | 0 | 20 |
| Error Handling | 12 | 0 | 12 |
| Performance & Caching | 15 | 0 | 15 |
| Scaling | 10 | 0 | 10 |
| API Design | 12 | 0 | 12 |
| Process & Lifecycle | 10 | 0 | 10 |
| Documentation | 8 | 0 | 8 |
| **Total** | **204** | **16** | **220** |

---

## Notes for Implementation

### Severity assignment logic

- **Critical**: A violation creates an exploitable vulnerability, data loss, or system failure in production. No exceptions.
- **High**: A violation causes bugs, maintenance debt, or security weakness that compounds over time. Exceptions require documented justification.
- **Medium**: A violation degrades code quality or developer experience. Exceptions are acceptable with team agreement.
- **Low**: A violation is a style or hygiene issue. Advisory only.

### Mandatory selection criteria

A rule is mandatory (always-on, never ranked) when ALL of these are true:

1. Severity is critical.
2. A violation is exploitable or causes data loss in production.
3. The rule is universal (applies regardless of language, framework, or domain).
4. An AI agent can mechanically detect violations from code inspection.

### Live corpus deviation from the 16-mandatory candidate set

The 220-rule public spec lists 16 mandatory candidates. The live Writ corpus promotes a slightly different set of 19 new mandatory rules from this rulebook (plus 11 Writ-specific `ENF-*` mandatory rules, for 30 total). The promoted set is:

- 1A Injection (6): SEC-INJ-SQL-001, XSS-001, CMD-001, SSRF-001, DESER-001, CSRF-001
- 1B Auth+AuthZ+Val (8): SEC-AUTH-HASH-001, TOKEN-001; SEC-AUTHZ-ENFORCE-001, IDOR-001, DEFAULT-001, MASS-001; SEC-VAL-SERVER-001, FILE-001
- 1C Crypto (2): SEC-CRYPTO-KEY-001, RAND-001
- 1D Data (1): SEC-DATA-PII-001
- 3B Performance (1): PERF-QUERY-001
- 4 Scaling (1): SCALE-STATELESS-001

Each promoted rule is backed by a cross-language regex analyzer in `bin/run-analysis.sh`. See `HANDBOOK.md` for the mandatory addition phase table.

### Language-specific extensions (included as examples)

The 220 rules above are language-agnostic. Writ ships the maintainer's own language-specific bundles as working examples of how to extend the rulebook for your stack:

- **Python**: `PY-*` rules (type hints, async patterns, import conventions, virtual environments).
- **JavaScript/TypeScript**: `JS-*`/`TS-*` rules (strict mode, Promise handling, null safety, module patterns).
- **Rust**: `RS-*` rules (ownership patterns, unsafe blocks, error handling with Result).
- **Go**: `GO-*` rules (error returns, goroutine lifecycle, context propagation).
- **SQL**: `SQL-*` rules (index usage, transaction isolation, migration patterns).

These are retrieved, not mandatory, and scoped to their language domain. Users can add their own language bundles following the same pattern.

### Relationship graph for the public rulebook

Rules should be ingested with edges:

- `SEC-INJ-SQL-001 DEPENDS_ON SEC-VAL-SERVER-001` (server-side validation is prerequisite to injection prevention).
- `SOLID-DIP-001 SUPPLEMENTS CLEAN-COUPLING-001` (DI is the mechanism for low coupling).
- `TEST-EXIST-001 SUPPLEMENTS PROC-TEST-001` (test-first process requires tests to exist).
- `PERF-QUERY-001 SUPPLEMENTS DRY-QUERY-001` (N+1 prevention and shared query methods serve the same goal; batch-fetch sometimes refines the shared method rather than contradicting it).
- `SCALE-STATELESS-001 DEPENDS_ON ARCH-STATE-001` (stateless processes require no unguarded global state).
- `ERR-RETRY-001 SUPPLEMENTS ERR-TIMEOUT-001` (retry strategy must account for timeout budgets).
- `SEC-AUTH-BRUTE-001 SUPPLEMENTS SEC-RATE-LOGIN-001` (brute force prevention is a form of rate limiting).
- `API-CONTRACT-001 DEPENDS_ON DOC-API-001` (API schema is a form of documentation).
- `SEC-INJ-CSRF-001 SUPPLEMENTS SEC-HDR-CORS-001` (CSRF and CORS are complementary defenses on state-changing requests).
- `SEC-AUTHZ-MASS-001 DEPENDS_ON SEC-VAL-TYPE-001` (typed schema validation is the mechanism for allowlisting assignable fields).
