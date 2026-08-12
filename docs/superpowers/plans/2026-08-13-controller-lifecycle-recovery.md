# Controller Lifecycle Recovery Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove the remaining controller lifecycle deadlocks and misleading diagnostics, verify the repair, and deploy version 0.7.11 locally.

**Architecture:** Extend the existing controller state machine with same-lock lane continuation and a narrow pre-decision cancellation transition. Keep main-turn authorization fail-closed while separating turn-binding failures from command-shape failures.

**Tech Stack:** Python 3.14, unittest, Git, repository release-preflight and installer scripts.

## Global Constraints

- Keep routing policy and role bindings unchanged.
- Preserve activation ID and Objective Lock digest across same-objective lanes.
- Never let a foreign turn execute lifecycle commands.
- Cancellation may not fabricate `complete` or `blocked` terminal evidence.
- Change repository sources first; installed copies are deployment targets.
- Bump `adaptive-delegation/VERSION` and update `CHANGELOG.md` for package changes.

---

### Task 1: Controller state-machine repair

**Files:**
- Modify: `adaptive-delegation/scripts/controller_gate.py`
- Modify: `adaptive-delegation/scripts/model_routing_audit.py`
- Test: `adaptive-delegation/tests/test_controller_gate.py`
- Test: `adaptive-delegation/tests/test_model_routing_audit.py`

- [x] Add focused failing tests for accepted-leaf continuation, cancellation, and turn-mismatch diagnostics.
- [x] Run the focused tests and confirm they fail for the reproduced v0.7.10 behavior.
- [x] Implement the minimal state transitions, CLI authorization, parser, and correction messages.
- [x] Reject stale or malformed activation argv before state creation while preserving unrelated no-state commands.
- [x] Teach sanitized controller health to count cancellation without reporting an invalid record or open activation.
- [x] Run the controller test module and `git diff --check`.

### Task 2: Package contract and version

**Files:**
- Modify: `adaptive-delegation/VERSION`
- Modify: `CHANGELOG.md`
- Modify: `README.md`
- Modify: `adaptive-delegation/SKILL.md`
- Modify: `adaptive-delegation/references/MODEL_ROUTING_POLICY.md`

- [x] Set version `0.7.11` and document the behavior without changing routing defaults.
- [x] Confirm README and installed-skill lifecycle descriptions match the implementation.

### Task 3: Verification and promotion

**Files:** none beyond Tasks 1 and 2.

- [x] Run install dry-run and both required unittest baselines.
- [ ] Obtain independent code and release-contract review and fix all blocking findings.
- [ ] Commit and push the feature branch, then run `release_preflight.py --mode pre-merge`.
- [ ] Merge and push `main`, then run `release_preflight.py --mode deploy` from clean `main == origin/main`.
- [ ] Run isolated dogfood from the published main commit, install locally, reconcile minimal OMX hooks, and verify source/installed version and digest equality plus fresh-process controller behavior.
