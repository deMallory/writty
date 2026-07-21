# Premise Verification Blueprint

## 0. Status and provenance

- **Status:** BLUEPRINT. Future work, not scheduled. No code written.
- **Authored:** 2026-06-17 against HEAD `c7a0a8a` (branch `friction-instrument-phase1`).
- **Origin:** design thread on the question "does Writ solve the agent-confidently-wrong-because-its-understanding-went-stale problem?" Answer: no, and it cannot fully; this blueprint is the partial defense plus the one piece that must exist before any of it.
- **On resume:** re-pin HEAD and re-verify every `file:line` and commit anchor below against live disk. They rot. Trusting them stale would be the exact failure this document exists to catch.
- **Related memory:** `project_ci_verification_gap.md`, `project_writ_north_star.md`, `project_multiproject_architecture.md`, `project_audit_2026_06_10.md` (the don't-trust-self-description lesson).

## 1. The problem

A gate verifies the *verdict* of a check the agent authored under a possibly-stale premise. It catches "claimed done without proof" (`ENF-PROC-VERIFY-001`, always-on) but not "the proof was of the wrong thing." The residue is an agent confidently wrong because its understanding went stale, shipped with a green checkmark.

There is no mechanical oracle of correctness. To check "is the understanding right" you would need the thing you lack. The only cure for the circularity (the checker shares the premise of the checked) is importing an external reference the stale premise did not author. Four sources exist: the world (probe declared assumptions against live state), independent derivation (different blindness), structure (answer-agnostic invariants), and time (invalidate conclusions when their sources change). When none reach, make the residue legible (calibrated confidence). The last inch, the unknown-unknown stale premise, is the human's permanently; a design that claims to close it is the one to distrust.

## 2. Diagnosis: the verifier is an unverified premise

The dominant recorded failure in this repo is not missing concepts. It is gates whose own correctness was never verified. That disease spans two classes:

- **Vacuous-pass:** the probe runs and measures nothing. Canonical instance: the v1.0.0 benchmark went green against the SentenceTransformer fallback because `make` hit a `python3` without `onnxruntime`. Declared, probed, passed, wrong.
- **Stale-fire:** the mechanism discriminates perfectly but the premise it encodes is gone. Canonical instance: `ENF-GATE-FINAL` denying writes for a rule deleted from the corpus. Known-bad denies, known-good permits, and it is still broken, because the staleness lives in "this verdict is justified by rule R" and R is gone, orthogonal to the input->verdict function.

A mechanism-level negative control catches vacuous-pass and is blind to stale-fire. Both must be addressed; neither's frequency is known (do not rank them on the contaminated n=3: the adjacency cache is a stale data source not a gate, and v1.0.0 is overdetermined).

**The deepest instance is the meta-verifier itself** (see Section 3 evidence): CI was deleted, its mitigation was a commit-message claim the artifact does not support, and nothing noticed for ~4 weeks because nothing checks that verification runs.

## 3. Evidence base (verified this session; re-verify on resume)

- `d43254a` (2026-05-14) added `.github/workflows/pr.yml`: the deny-path runner. It ran `make test` (full suite incl. `tests/test_enforce_violations.py`) in a pinned Neo4j 5 service container; the `setup-writ` action exported ONNX so `build_pipeline()` took the real path (comment cites the silent-ONNX-fallback bug `dae679a`) and guarded corpus `>= 250` rules.
- `dd17fd2` (2026-05-22) deleted all of `.github/` as part of a deliberate, correct "moving to a private enterprise project" divorce (pr.yml + publish.yml + marketplace.json + Pages + CONTRIBUTING + PROMOTIONAL-BRIEF removed together). The verification loss was **collateral**: pr.yml was filed under "GitHub infrastructure," not "verification that must run somewhere."
- The commit's claimed mitigation (a "CI-runner-agnostic note" in HANDBOOK) is not substantiated by the artifact at `dd17fd2` or HEAD (absent by every keyword); HANDBOOK was later recreated wholesale (`be32920`).
- At HEAD: no CI, `.git/hooks` empty, only manual `make test`.
- `make check` (Makefile) already exists and is complete: `test` + `bench` + `validate` (`writ.cli validate`, the authoritative graph validators), pinned to `.venv/bin/python3`, with the onnxruntime trap documented in-file. The runner exists; it just never runs.
- `tests/test_fix6_corpus_integrity.py:195` asserts `>= 280` rule blocks plus orphan bounds, the heir to pr.yml's dead `>= 250` guard. Unrun. `test_inc1_determinism.py` (`classify_corpus_state`) and `test_pol2b` (rule-count-no-drift) corroborate.
- Reconcile data-loss protection landed in code: `writ/cli.py:593` reconcile takes `project` ("M.1: never touches another project's nodes/edges"). A test *demonstrating* cross-project safety was not confirmed to exist.
- `TEC-PROC-RED-VERIFY-001` exists ("a test that errors has not achieved RED... an erroring test proves nothing") but is scoped to the agent's TDD tests, not to gates.

## 4. The regress terminator: negative control

"Verify the verifier" sounds infinite. It terminates in **depth** at one demonstration that a probe *discriminates*: fires on a known-bad input, passes on a known-good one. You verify the verifier exactly once, by negative control, then stop going deeper.

It does **not** terminate in **time**. A control's validity rots (the onnxruntime drift was a probe that was valid and became vacuous) and its very existence rots (`dd17fd2` deleted the runner). So every probe is a continuous gate, never a one-time check. "Verify once then stop" conflates depth with time; only the depth claim is true.

## 5. Step 0: the verification substrate (must precede everything else)

A new gate built in the same pipeline that produced "the gate existed as a file" inherits that disease. So the first work is not a new gate of any flavor. It is making the catchers provably run, anchored so their removal is not silent.

The load-bearing decision is **location**, not mechanism. The mechanism is easy; where the self-check terminates is the part that just failed in production. The anchor must satisfy: tracked, traversed by a routine path, observable on deletion, terminating outside the thing it protects.

**The three anchor questions, answered:**

- **Tracked artifact that holds the self-check:** the daemon's per-turn freshness check (tracked Python in `writ/`), reading a stamp that `make check` writes on success. Plus a tracked negative-control test and a tracked pre-push installer (reuse the `scripts/install-server-service.sh` pattern).
- **Routine path that traverses it:** every turn, the daemon is hit via `writ-rag-inject.sh` and `writ-statusline.sh` (the most-traversed path in the system); secondarily `git push` via the installed pre-push hook.
- **What breaks observably on deletion:** the stamp records the verified commit SHA. The daemon compares stamp-SHA to HEAD every turn (cheap; it does NOT run the suite). Delete the runner or hook -> the stamp stops advancing past HEAD -> the statusline renders `[WRIT] gates UNVERIFIED vs HEAD (last: <sha|never>)` every turn. Delete the daemon -> the whole product (rules, gates) dies and is noticed in one turn.

**The terminator is the daemon**, because its absence is catastrophic by self-interest, not by another checker. That is where the regress legitimately stops: the component you cannot run without. This self-check *is* 1b (source-binding) applied to the verifier itself, the stamp bound to its referent (HEAD), probed every turn; getting it right validates the 1b pattern for all other gates.

**Components (contracts, not code):**

1. **Stamp-on-success.** `make check` writes `<HEAD-sha> <timestamp>` to a daemon-readable local path (gitignored runtime state) only when `test` and `validate` pass. Contract: stamp present and `== HEAD` means the deny-path suite and graph validators passed against this exact tree.
2. **Trigger.** Tracked `scripts/install-verification-hook.sh` installs `.git/hooks/pre-push` running `make check`, blocking push on failure. The hook is untracked by git's design; its silent removal is covered by component 3.
3. **Terminator (daemon banner).** The daemon reads the stamp per turn, compares to HEAD, and renders the `UNVERIFIED vs HEAD` banner in the statusline and the always-on inject block when stale or absent. **Advisory, not blocking**, so it cannot brick the product.
4. **Negative control.** New `tests/test_verification_substrate.py`: asserts the banner fires on a stale/absent stamp and stays silent on a fresh one (deny+permit discrimination, demonstrated once), and that the installer wires `make check`. It runs inside `make check`; the daemon banner is the out-of-band guarantee if the test itself is deleted.

**Decisions and roads not taken:**

- Daemon-runs-the-suite: REJECTED. Per-turn heavy work, latency-floor risk. The daemon only reads a cheap stamp.
- Pre-push-only: REJECTED. Untracked, deletes silently, exactly how pr.yml went.
- Banner-as-hard-block: REJECTED. Fragility against the north star (do not make the gate product fragile). Hard-block lives only at the push chokepoint, where a human is already acting.
- Restore the GitHub workflow: REJECTED. The divorce was intentional and correct; this is a private single-graph repo. The substrate is local.

**Boundary of the guarantee (honest):** single-point silent deletion is closed. A two-point silent deletion (runner and the daemon banner logic together) is not, but the banner logic is tracked Python (a reviewable diff) and the daemon's own deletion is self-evidently catastrophic. Beyond that is cryptographic territory, past the bar of "one demonstration that removal fails something a human sees."

## 6. Gate selection under the private single-graph topology

Criterion, not inheritance from the 276-rule-marketplace era: the gate whose *silent* failure costs most in a private single-graph accumulator. The graph is the source of every premise the agent uses, so a silently incomplete or data-lost graph is the substrate of "confidently wrong because understanding went stale," upstream of every rule-deny path.

- **First negative-control target: `tests/test_fix6_corpus_integrity.py`** (graph completeness + orphan bounds). It exists, it is the direct heir to the deleted `>= 250` guard, and `make check` already runs it via `validate`. Step 0 makes it actually run and proves it discriminates.
- **Second target, to confirm: reconcile no-cross-project-deletion.** Highest blast-radius mutation in the single-graph world. M.1 scoping is coded (`writ/cli.py:593`); if no test asserts "project=A reconcile leaves project=B untouched," authoring that property is the highest-value new check, ahead of any rule-deny path.
- The old deny-path tests (`test_enforce_violations`, `test_phase2_gate_policy`) still run inside `make check`; they are simply no longer first.

## 7. 1a / 1b (after step 0)

- **1a, mechanism negative-control:** Section 5 component 4's discrimination pattern, applied to the selected gate's mechanism. Deny fires on known-bad, permit fires on known-good, in a pinned env. Cures vacuous-pass.
- **1b, source-binding:** Section 5 component 1's stamp-vs-referent pattern, generalized. Tag each gate with the `rule_id` / commit / schema version it depends on; probe every run that the referent still holds. Cures stale-fire. `ENF-GATE-FINAL` is the worked example: bind it to its rule's existence.

## 8. Node family (only if authored into the corpus later)

Mirror of the existing completion-verification family. `ENF-PROC-VERIFY-001` verifies the completion claim; this verifies the premise claim. Tagline: verify the premise, not just the verdict.

- `ENF-PROC-PREMISE-001` (gate): a conclusion cannot be cited until its load-bearing assumptions are declared as probeable claims and the probes pass.
- `ANT-PROC-PREMISE-001` (antipattern): "confidently wrong because the premise went stale."
- `SKL-PROC-PREMISE-001` (skill): enumerate assumptions and probe them against live reality.
- `RAT-PREMISE-001` (rationalization): "I already know how this works."
- Generalize `TEC-PROC-RED-VERIFY-001` from TDD-scoped to gate-scoped.

Caveat from the diagnosis: declared assumptions cover only known-unknowns. The strategically-undeclared known is reached only by independent re-derivation (different blindness); the unknown-unknown by that plus answer-agnostic invariants; both probabilistically, at cost, reserved for high blast radius. Do not oversell the node family as closing the residue.

## 9. What not to do

- Do not author a new gate before step 0 exists. It inherits the file-not-enforcement disease.
- Do not trust a commit message's self-description of a mitigation. Verify against the live tree (`dd17fd2` is the cautionary tale).
- Do not rank 1a vs 1b on the current evidence. Build both; the choice is unmeasurable until a non-synthetic instrument exists (the self-repo friction log is ~86% test-synthetic).
- Do not make the daemon banner blocking. Advisory only; the product must not become fragile.
- Do not silently cap or sample anything without logging what was dropped.
