---
playbook_id: PBK-PROC-DIAGNOSE-CRASH-STACKTRACE-001
node_type: Playbook
domain: process
severity: high
scope: task
trigger: "When a crash, exception, panic, segfault, or fatal error is observed AND a stack trace (or an equivalent location: a logged error line, an assertion with file:line) is available."
statement: "The stack trace is your observation and your narrowing. Read the top in-project frame first, trace the bad value back to its origin, reproduce from the trace, and falsify before fixing."
rationale: "For a crash with a trace, the runtime observation already points at a call site, so reading code first is the disciplined move, not a reflex. The danger is patching the frame where the error surfaced instead of where the bad state was created."
tags: [debugging, crash, stacktrace, exception, diagnose, playbook, process]
confidence: peer-reviewed
authority: human
last_validated: 2026-05-29
staleness_window: 365
evidence: peer-reviewed
source_attribution: "writ-native"
source_commit: null
phase_ids: []
preconditions: []
dispatched_roles: []
edges: []
category: CAT-PROC-001
trigger_keywords: ["stack trace", "segfault", "crash", "exception", "panic"]
---

# Playbook: Diagnose a crash with a stack trace

## When this applies

A crash, exception, panic, segfault, or fatal error **with** a stack trace or an
equivalent error location. If there is no location, fall back to the general loop
(PBK-PROC-DEBUG-001).

## Ordering (the trace inverts the usual loop)

1. **Read the top in-project frame first.** The trace is already your observation
   and your narrowing -- it names the call site. Skip library/framework frames;
   open the first frame you own.
2. **Read the values at that frame.** What was null/undefined/out-of-range? Which
   precondition did the code assume that did not hold?
3. **Walk up to the origin.** The crash site is where the fault *surfaced*, not
   necessarily where the bad state was *created*. Trace the offending value back to
   where it entered: an input boundary, a prior assignment, a missing initialization.
4. **Reproduce from the trace.** Construct the smallest input or state that reaches
   the same frame. A failing reproduction is the strongest evidence.
5. **Falsify before fixing (mandatory).** State how the hypothesis could be wrong
   ("if X is the cause, the value at frame N must be Y") and check it against the
   trace or the reproduction. A guess that happened to come last is not a diagnosis.

## Why reading code first is correct here

The general loop says observe runtime before reading code. A stack trace *is* that
runtime observation and it points at a specific call site, so reading code first is
disciplined, not a shortcut. The gate is unchanged -- no fix without a falsified
hypothesis -- only the entry point differs.

## Red flags

- "The exception message is enough." The message is the symptom; the top frame is the location.
- "Add a guard at the crash site and move on." That patches the surface, not the origin (step 3).
- Naming a root cause from the surfacing frame without tracing where the bad state began.
