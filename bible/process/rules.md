<!-- RULE START: PROC-BRANCH-001 -->
## Rule PROC-BRANCH-001

**Domain**: process
**Category**: CAT-PROC-001
**Severity**: Low
**Scope**: Component
**Mandatory**: false

### Trigger
When creating a feature branch.

### Statement
Feature branches are named with a ticket/issue reference: `bug/ORD-1234-negative-quantity`, `feat/ORD-1500-tenant-scoping`. Ad-hoc branch names without a tracking reference are violations.

### Violation
```
branch: lucio-fix-2
```

### Pass
```
branch: fix/ORD-1421-tenant-scoping
```

### Enforcement
Repository branch-naming convention. PR template checks. Related: PROC-INCIDENT-001.

### Rationale
Traceable branch names link code to issue tracker to release notes. Untraceable names break the audit trail.

<!-- RULE END: PROC-BRANCH-001 -->
---

<!-- RULE START: PROC-CHANGELOG-001 -->
## Rule PROC-CHANGELOG-001

**Domain**: process
**Category**: CAT-PROC-001
**Severity**: Medium
**Scope**: Component
**Mandatory**: false

### Trigger
When releasing user-facing changes.

### Statement
User-facing changes are documented in a changelog or release-notes file. The audience is end users / API consumers / customers, not engineers. Behavior changes, new features, breaking changes, deprecations are all logged.

### Violation
```
# CHANGELOG.md last updated 6 months ago; production has shipped 50 features since.
```

### Pass
```
# CHANGELOG.md:
# ## v2.5.0 (2026-05-10)
# - Added: tenant scoping on /api/orders.
# - Fixed: negative-quantity bypass on order creation.
# - Deprecated: /v1/legacy-orders (sunset 2026-09-01).
```

### Enforcement
Release-process tooling (changesets, conventional-changelog, knope) generates from commits.

### Rationale
Changelogs are the contract with consumers: they can plan integrations from a written record, not from reverse-engineering deploys.

Related rules: API-BREAKING-001, PROC-COMMIT-001.

<!-- RULE END: PROC-CHANGELOG-001 -->
---

<!-- RULE START: PROC-COMMIT-001 -->
## Rule PROC-COMMIT-001

**Domain**: process
**Category**: CAT-PROC-001
**Severity**: Medium
**Scope**: Component
**Mandatory**: false

### Trigger
When writing commit messages.

### Statement
Commit messages follow a conventional format: a short subject line (`type: subject` or just a clear summary), and a body for non-trivial changes describing the why. Single-line drive-by messages on substantive changes are violations.

### Violation
```
fix stuff
```

### Pass
```
fix: reject negative quantities in /api/orders

Negative quantities bypassed the existing balance check and produced
double-credit refunds. Adds SEC-VAL-RANGE-001 guard plus regression test.
```

### Enforcement
Code review.

### Rationale
Commit messages are read by every future engineer and during every incident. The 30 seconds spent writing a clear message saves hours later.

<!-- RULE END: PROC-COMMIT-001 -->
---

<!-- RULE START: PROC-DEPLOY-001 -->
## Rule PROC-DEPLOY-001

**Domain**: process
**Category**: CAT-PROC-001
**Severity**: High
**Scope**: Component
**Mandatory**: false

### Trigger
When deploying code to production.

### Statement
Production deploys go through a CI/CD pipeline. Manual deploys (scp, ssh, kubectl apply) are forbidden for production. The pipeline runs tests, builds artifacts, applies migrations, and rolls out via the deployment strategy.

### Violation
```
# Engineer SSHes into prod and runs `git pull && systemctl restart`.
# No record, no rollback path, no test gate.
```

### Pass
```
# `git push origin main` triggers CI; CI runs tests, builds image, applies
# migrations, deploys to staging, promotes to prod after smoke tests pass.
```

### Enforcement
CI/CD platform (GitHub Actions, GitLab CI, ArgoCD, Spinnaker).

### Rationale
Pipelined deploys are reproducible, gated, and auditable. Manual deploys produce drift, skip checks, and have no rollback.

Related rules: ARCH-MIGRATION-001, PROC-ROLLBACK-001, SCALE-MIGRATE-001.

<!-- RULE END: PROC-DEPLOY-001 -->
---

<!-- RULE START: PROC-ENV-001 -->
## Rule PROC-ENV-001

**Domain**: process
**Category**: CAT-PROC-001
**Severity**: Medium
**Scope**: Component
**Mandatory**: false

### Trigger
When handling production credentials.

### Statement
Production credentials are never shared in code, chat (Slack, Teams, email), tickets, or other text artifacts. They live exclusively in the secret management service. Sharing a credential is a security incident; the credential is rotated.

### Violation
```
Slack DM: 'here is the prod DB password: hunter2'
```

### Pass
```
Slack DM: 'request access via 1Password vault: production-database'
```

### Enforcement
Slack DLP scanning. Security training. Incident response on credential exposure.

### Rationale
Once a credential is in a chat scroll, it lives forever in every chat client, every backup, and every export. Secret managers eliminate the durable exposure.

Related rules: SEC-CRYPTO-KEY-001, SEC-CRYPTO-KEY-002.

<!-- RULE END: PROC-ENV-001 -->
---

<!-- RULE START: PROC-INCIDENT-001 -->
## Rule PROC-INCIDENT-001

**Domain**: process
**Category**: CAT-PROC-001
**Severity**: Medium
**Scope**: Component
**Mandatory**: false

### Trigger
When an incident occurs in production.

### Statement
Post-incident review produces action items with owners and deadlines. Action items are tracked to completion; the incident is not closed until they are. Blameless: the review focuses on systemic causes, not individual error.

### Violation
```
# Incident retro: 'we'll do better next time'; no tracked actions; same incident next month.
```

### Pass
```
# Postmortem doc: timeline, root cause, action items.
# Action: 'Add retry budget to upstream call (@alice, due 2026-05-24)'.
# Tracked in ticket system; reviewed weekly.
```

### Enforcement
Postmortem template + tracking. Incident-management platform (PagerDuty, Incident.io, FireHydrant). Related: ENF-PROC-DEBUG-001.

### Rationale
Untracked retro actions guarantee the incident repeats. Tracked actions are the difference between learning and re-learning.

<!-- RULE END: PROC-INCIDENT-001 -->
---

<!-- RULE START: PROC-PLAN-001 -->
## Rule PROC-PLAN-001

**Domain**: process
**Category**: CAT-PROC-001
**Severity**: High
**Scope**: Component
**Mandatory**: false

### Trigger
When starting any task that involves modifying code.

### Statement
Work mode requires a written plan before any production code is written. The plan covers files to be touched, an analysis of constraints, the rules that apply, and the capabilities to be tested. ENF-PROC-PLAN-001 and ENF-PROC-BRAIN-001 mechanically enforce this for the Writ workflow; the policy itself is universal.

### Violation
```
# Developer starts editing main.py directly; no plan written. Code lands
# scope-creeping into adjacent concerns; reviewer cannot tell what the
# author intended versus what they touched incidentally.
```

### Pass
```
# plan.md written first. Files: orders/service.py, orders/repo.py.
# Analysis: existing patterns for tenant scoping; constraint: no schema
# change. Rules applied: SEC-AUTHZ-TENANT-001, ARCH-LAYER-001.
# Capabilities: list orders for current tenant; reject cross-tenant access.
```

### Enforcement
ENF-PROC-PLAN-001 (format check) + ENF-PROC-BRAIN-001 (design before code) gates. Code review.

### Rationale
A written plan exposes scope creep before code lands. The plan is also the artifact a reviewer reads first to know what to evaluate against.

<!-- RULE END: PROC-PLAN-001 -->
---

<!-- RULE START: PROC-REVIEW-001 -->
## Rule PROC-REVIEW-001

**Domain**: process
**Category**: CAT-PROC-001
**Severity**: Medium
**Scope**: Component
**Mandatory**: false

### Trigger
When merging a change to a shared branch.

### Statement
Code is reviewed by at least one other person or a reviewer agent before merge. Auto-merge on green CI is permitted only for trivial mechanical changes (dependency updates, formatter pushes) and is configured per-repo.

### Violation
```
# Author merges their own PR moments after opening.
```

### Pass
```
# PR requires a reviewer approval; reviewer reads the diff and the plan;
# explicitly approves or requests changes.
```

### Enforcement
Repository branch protection rule.

### Rationale
A second pair of eyes catches scope errors, missing tests, and security oversights that the author normalized to. The check is cheap relative to the cost of fixing in production.

Related rules: ENF-PROC-SDD-001, PROC-COMMIT-001, PROC-PLAN-001.

<!-- RULE END: PROC-REVIEW-001 -->
---

<!-- RULE START: PROC-ROLLBACK-001 -->
## Rule PROC-ROLLBACK-001

**Domain**: process
**Category**: CAT-PROC-001
**Severity**: High
**Scope**: Component
**Mandatory**: false

### Trigger
When designing the deployment system.

### Statement
Deployment strategy supports rollback within minutes: blue-green, canary, feature flag, or `helm rollback` / `kubectl rollout undo`. A deploy that cannot be reverted produces extended outages on every bad change.

### Violation
```
# Deployment overwrites the previous image; rollback requires rebuilding
# the prior commit, taking minutes-to-hours.
```

### Pass
```
# Blue-green: both versions running; LB switches; rollback is an LB flip.
# Or: image versions in registry; rollback redeploys the prior tag.
```

### Enforcement
Deployment-platform config review.

### Rationale
Rollback is the most important property of the deployment system. Without it, every deploy is a one-way bet.

Related rules: ARCH-MIGRATION-002, PROC-DEPLOY-001, SCALE-MIGRATE-001.

<!-- RULE END: PROC-ROLLBACK-001 -->
---

<!-- RULE START: PROC-TEST-001 -->
## Rule PROC-TEST-001

**Domain**: process
**Category**: CAT-PROC-001
**Severity**: High
**Scope**: Component
**Mandatory**: false

### Trigger
When implementing production code that is not a one-shot script.

### Statement
Test skeletons are written and approved before the implementation. Tests carry the contract; the implementation conforms to them. ENF-PROC-TDD-001 mechanically enforces this in the Writ workflow.

### Violation
```
# Implementation lands first; tests added afterwards to match what was
# built. Tests validate the implementation, not the intent.
```

### Pass
```
# tests/test_orders_cancellation.py written first with failing tests.
# Implementation iterates until tests pass. Tests document intent.
```

### Enforcement
ENF-PROC-TDD-001 (failing test before src/ write) gate. Code review.

### Rationale
Test-first ensures tests describe the contract independent of the implementation. Test-after risks tests that codify whatever the implementation happens to do.

<!-- RULE END: PROC-TEST-001 -->
