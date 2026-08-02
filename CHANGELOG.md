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
