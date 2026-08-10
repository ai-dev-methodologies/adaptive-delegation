# Changelog

All notable installable changes to Adaptive Delegation are recorded here.
The canonical package version is stored in
[`adaptive-delegation/VERSION`](adaptive-delegation/VERSION).

This project follows Semantic Versioning and remains pre-1.0 while its packet
and routing contracts are still being validated in real Codex use:

- Before 1.0, MINOR may include an incompatible experimental contract change.
- After 1.0, MAJOR is reserved for incompatible stable contracts.
- PATCH: backward-compatible fix, validation hardening, or documentation repair.

Every installable package change must update both `adaptive-delegation/VERSION`
and this changelog. Release tags should use `v<version>`.

## [0.7.0] - 2026-08-10

- Made `$adaptive-delegation` explicit and controller-only. Installed
  `UserPromptSubmit` and `PreToolUse` hooks now keep the Sol/high-or-above main
  on orchestration, require a declared current-session authority and Objective
  Lock digest, admit only the exact package role/model/effort launch, and deny
  main task tools unless a bounded evidence-backed exception or exhausted
  ladder takeover is recorded. Cost, task size, existing context, and latency
  cannot authorize direct main execution.
- Added owner-only controller event evidence for activations, decisions,
  authorized leaf launches, main-only exceptions, takeovers, and denied main
  tools. Installation preserves foreign hooks and the existing Stop owner,
  installs no Stop hook, and records trust only for its two managed handlers.
- Expanded cumulative routing reviews and sanitized health reporting with
  explicit trigger metadata,
  model-selection fitness (`appropriate`, `underpowered`, `overpowered`, and
  `inconclusive`), observed-versus-unobserved token cost coverage, quality and
  integration outcomes, controller aggregates in health output, and a
  25-accepted-task sufficiency floor. Unavailable measurements are no longer
  represented as observed zero cost.

## [0.6.3] - 2026-08-10

- Fixed failed direct-typed child executions being left as integration-pending
  attempts. Nonzero dispatcher results now close the adaptive audit with a
  failure `post_result`; only successful child execution can await integration.
- Classified stdout, tool-output, tool-count, and rollout-size limits as
  `context_ceiling`, so quantitative policy failures produce a valid paired
  audit result instead of being rejected as scope overbreadth.

## [0.6.2] - 2026-08-09

- Added the read-only `model_routing_audit.py health` command with a
  versioned, sanitized evidence-health report, fixed anomaly categories, and
  no runtime-ledger mutation or state-file creation. Current-policy sufficiency
  excludes historical acceptance, reviews are treated as cumulative snapshots,
  and continuity scanning is a documented aggregate-only health exception.

## [0.6.1] - 2026-08-08

- Changed installation to copy an explicit runtime allowlist instead of the
  complete source package. Repository tests, deployment documentation, and
  maintainer-only routing references now remain in the checkout and are not
  installed into the user Codex home.
- Made version comparison hash the same runtime allowlist while still
  reporting unexpected files in an installed package as drift.

## [0.6.0] - 2026-08-03

- Added privacy-safe, duplicate-aware feedback reporting. Prepared reports keep
  a stable random Report ID; submitted receipts exclude already-shared attempt
  fingerprints without storing raw task or attempt identifiers.
- Added a packaged copy-paste Codex prompt that checks all canonical GitHub
  issues for the exact Report ID, creates at most one issue, and records the
  returned URL locally with an idempotent command.
- Added a fail-closed release preflight. Feature-to-main promotion and
  published-main deployment now require a complete README review, current
  version and changelog, config-matched route ladders, and exact Git evidence.
- Documented the Maker, Checker, and main-authority lifecycle with maintained
  diagrams. The package has no redundant adaptive Verifier role; distinct
  Checker evidence and main integration retain separate responsibilities.

## [0.5.2] - 2026-08-03

- Corrected the long-horizon classifier so Goal/Ultragoal membership is not a
  route input. The qualified path is available for any bounded slice whose
  latency, horizon, oracle, and risk evidence satisfies the main's decision.
- Documented the main-only release order: validate on a feature branch, merge
  and push `main`, then install locally from the clean published main commit.

## [0.5.1] - 2026-08-02

- Made route classification explicitly main-authoritative: the Sol/high-or-
  above main classifies every bounded slice from task evidence, and workflow
  labels alone cannot select the long-horizon route.
- Added a fail-closed package decision contract for the classification owner,
  required dimensions, long-horizon predicates, child rerouting prohibition,
  and observable-failure escalation rule.

## [0.5.0] - 2026-08-02

- Made the skill's built-in contract explicitly sufficient: bounded execution
  remains Luna-first, stops immediately at declared acceptance, and forbids
  optional review, broad testing, or adjacent improvement without requiring
  extra user prompt text.
- Added a quota-first, latency-insensitive long-horizon route for active Codex
  goal and Ultragoal work with a strong oracle:
  `Luna max -> Terra xhigh -> Terra max -> Sol high -> main Sol ultra`.
- Restored Terra `xhigh`/`max` Maker and Checker bindings only for that route.
  They require observable preceding-route failure and never run as paired A/B.
- Preserved the existing direct-latency Terra `medium`/`high` path for work with
  a measurable time constraint.
- Kept `ultra` main-authoritative; Terra has no `ultra` route and no leaf may
  inherit main `ultra`.

## [0.4.0] - 2026-08-02

- Established the pre-1.0 Codex-only package, portable installer, deterministic
  version comparison, privacy-safe issue reporting, and isolated verification.
- Added Luna-first, effort-first routing with exact Native role bindings and
  main-authoritative Sol `ultra` takeover.
- Added Terra `medium` and `high` as evidence-seeking intermediates after
  observable Luna acceptance/quality failures, with task-shape-specific route
  selection before Sol leaf escalation.
- Added a guarded direct-latency Terra path requiring a pre-observable,
  scoped, strong-oracle, recoverable, non-ambiguous predicate; runtime/tool
  failures remain environment retries and never model-escalation evidence.
- Removed stale Terra `xhigh`/`max` and dormant A/B experiment bindings. Terra
  use is passively logged as `post_luna_failure` or `direct_latency`, and audits
  compare accepted-task outcomes without perpetual paired runs.
- Split the Objective Lock's stable terminal outcome/authority from a
  replaceable path/iteration envelope so blocked paths return to main for
  in-scope alternatives while fabrication and unauthorized substitution remain
  forbidden.
- Updated model-routing audit vocabulary, role templates, pricing metadata,
  installation docs, and regression tests.

This is an experimental pre-1.0 contract change because packets require an
explicit `terminal_outcome`, and the earlier Objective Lock contract is
replaced by v3: a stable terminal outcome/authority layer plus a replaceable
path/iteration envelope. Re-execute unfinished packets as fresh 0.4 tasks; do
not continue an older packet across the Objective Lock v3 wire contract.
