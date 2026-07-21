---
example_id: EXM-PLAN-001
node_type: WorkedExample
domain: process
scope: task
trigger: "User requests an example of a bite-sized plan task -- what the 2-5 minute micro-cycle of steps looks like inside one task of an implementation plan."
statement: "Concrete walk-through of one plan task decomposed into the 2-5 minute micro-cycle: exact files, then five checkbox steps (write failing test, run it to watch it fail, minimal implementation, run it to watch it pass, commit), each with complete code and the exact command + expected output."
rationale: "Worked examples anchor abstract methodology in specific commands and outputs. 'Bite-sized' is vague until you see one task rendered as five one-action steps; the example shows the granularity PBK-PROC-PLAN-001 prescribes."
tags: [example, planning, plan, micro-cycle, bite-sized, worked, process]
confidence: peer-reviewed
authority: human
last_validated: 2026-06-03
staleness_window: 365
evidence: peer-reviewed
source_attribution: "writ-native"
source_commit: null
title: "One plan task as the 2-5 minute micro-cycle"
before: "An approved design adds rejection of empty emails to the signup form. The planner must render this as one bite-sized task."
applied_skill: PBK-PROC-PLAN-001
result: "Task rendered as five one-action steps -- failing test, run-to-fail, minimal code, run-to-pass, commit -- each with complete code and an exact command plus expected output. No placeholders; the implementer reproduces it without interpretation."
linked_skill: PBK-PROC-PLAN-001
edges:
  - { target: PBK-PROC-PLAN-001, type: DEMONSTRATES }
category: CAT-DISC-001
---

# Worked example: one plan task as the 2-5 minute micro-cycle

Non-retrievable via standard pipeline. Surfaces when a user asks what a bite-sized plan task
looks like, or via bundle expansion from `PBK-PROC-PLAN-001`.

### Task 3: Reject empty email on signup

**Files**
- Modify: `src/signup.py:40-52`
- Test: `tests/test_signup.py`

Each step is one action (2-5 minutes):

- [ ] **Step 1: Write the failing test**
  ```python
  def test_signup_rejects_empty_email():
      result = submit_signup({"email": ""})
      assert result.error == "Email required"
  ```
- [ ] **Step 2: Run it, watch it fail (for the right reason)**
  Run: `pytest tests/test_signup.py::test_signup_rejects_empty_email -v`
  Expected: FAIL -- `AssertionError: None != "Email required"` (behavior missing, not an error).
- [ ] **Step 3: Minimal implementation** (no more than the test needs)
  ```python
  if not data.get("email", "").strip():
      return Result(error="Email required")
  ```
- [ ] **Step 4: Run it, watch it pass**
  Run: `pytest tests/test_signup.py::test_signup_rejects_empty_email -v`
  Expected: PASS; other signup tests still green.
- [ ] **Step 5: Commit**
  Run: `git add src/signup.py tests/test_signup.py && git commit -m "feat: reject empty email on signup"`
