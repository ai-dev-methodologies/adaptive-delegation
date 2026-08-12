# Controller Lifecycle Recovery Design

## Outcome

Adaptive Delegation must keep one activation and one immutable Objective Lock
across all lanes required for the same terminal outcome. An accepted Maker
result may therefore be followed by a Checker or an evidence-backed main-only
lane without closing and reactivating the controller.

## State transitions

- `leaf_result_recorded` admits another `decision` regardless of whether the
  prior result was accepted, provided the Objective Lock digest is unchanged.
- A subsequent decision replaces only the path-local child launch binding; it
  never replaces the activation ID or Objective Lock digest.
- `close --terminal-status complete` remains the only successful terminal
  close and still requires accepted integration evidence for a leaf result.
- A new `cancel` command is admitted only from `awaiting_main_declaration` or
  `explicit_active`, before any Objective Lock decision or terminal evidence.
  It records `controller_cancelled`, moves the state to `closed`, omits a
  terminal status, and releases the session tool restriction without claiming
  task completion or blockage.

## Turn binding and diagnostics

Controller CLI execution remains restricted to the current main turn. If an
otherwise recognizable controller command comes from another turn, the hook
must report a main-turn binding mismatch and direct the main to continue on a
fresh user turn. It must not misreport that condition as malformed flags.
Foreign turns remain denied and cannot use `cancel` or any other lifecycle
command. A no-state or closed-state `activate` command must bind its exact
session, workspace, model, effort, and `main-turn-id` to the current hook
payload before the CLI may create or replace state.

## Verification

Regression tests must first reproduce and then prove fixes for accepted-leaf
continuation, pre-decision cancellation, foreign-turn cancellation denial, and
turn-mismatch diagnostics. Existing controller, package, installer, release
preflight, and isolated promotion tests must remain green. The installable
package becomes version `0.7.11`, and deployment occurs only from clean `main`
matching `origin/main` after the repository's pre-merge and deploy gates pass.
