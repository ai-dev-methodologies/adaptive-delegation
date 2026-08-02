# Changelog

All notable installable changes to Adaptive Delegation are recorded here.
The canonical package version is stored in
[`adaptive-delegation/VERSION`](adaptive-delegation/VERSION).

This project follows Semantic Versioning:

- MAJOR: incompatible packet, audit, installation, or operational contract.
- MINOR: backward-compatible capability, route, role, or workflow addition.
- PATCH: backward-compatible fix, validation hardening, or documentation repair.

Every installable package change must update both `adaptive-delegation/VERSION`
and this changelog. Release tags should use `v<version>`.

## [2.0.0] - 2026-08-02

- Made the portable Objective Lock the skill's primary invariant, independent
  of user-global or project `AGENTS.md` files.
- Added required machine-checked `non_goals` to canonical Objective Lock v2.
- Bound Maker, Checker, retry, escalation, and main takeover paths to the same
  lock while explicitly prohibiting post-acceptance review and validation
  expansion.
- Applied the same lock to main-side routing preflight and made continuity
  lookup conditional so fresh bounded tasks do not inspect optional package
  internals or state.
- Kept Objective Lock v1 audit evidence readable while rejecting cross-version
  task continuation and requiring a fresh v2 task for unfinished work.

## [1.0.0] - 2026-08-02

- Established the Codex-only Adaptive Delegation package and portable installer.
- Added Luna-first, effort-first routing with exact role/model/effort bindings.
- Added canonical Objective Lock propagation across Native, typed, retry,
  escalation, Checker, integration, and main-takeover paths.
- Added linked `0.3.0` audit records, legacy cutover rules, privacy-safe issue
  reporting, bounded continuity reads, and isolated promotion verification.
- Added prompt-driven installation and deterministic source-versus-installed
  version comparison for Codex CLI operators.
