# Adaptive Delegation Repository Governance

This directory is the standalone, portable source repository for the
`adaptive-delegation` skill. Repository files are canonical. Installed copies
under `~/.codex/skills/adaptive-delegation/`, `~/.codex/scripts/`, and
`~/.codex/agents/` are deployment targets; never edit an installed copy first
and then try to back-port the change. Update this repository, verify it, and
run `scripts/install.py` only when deployment is requested.

This repository is Codex-only: `adaptive-delegation` routes Codex native
subagents. Claude Code is unsupported.

## Policy invariants

- Keep routing Luna-first, effort-first within Luna, then through fixed Sol
  `medium`/`high` leaf roles. Bounded work starts on the lowest suitable Luna
  effort and escalates only from observable evidence.
- The main-authority gate is fail-closed over declared current-session context:
  the main must be `gpt-5.6-sol` with reasoning effort `high`, `xhigh`, `max`,
  or `ultra` before delegation can launch. Do not describe this declaration as
  cryptographic runtime proof.
- Native leaves use fixed, package-declared role bindings in
  `adaptive-delegation/roles/*.toml`. Verify the bound model and effort; do not
  silently substitute another model when a Luna or Sol admission is rejected.
- Terra is excluded from automatic ladders. Its retained `max` Maker/Checker
  bindings remain dormant until a future versioned, explicitly evaluated A/B
  contract activates them.
- Leaf `ultra` is forbidden. `gpt-5.6-sol/ultra` is a main-authoritative
  takeover only.
- Model or reasoning escalation changes capability, never authority or scope.
  Every child, Checker, retry, escalation, and main takeover inherits the exact
  canonical Objective Lock and must stop when its acceptance conditions are
  proved.
- Construct the complete portable Objective Lock before the first child
  launch. It includes objective, non-goals, read/write/network authority,
  intended behavior, acceptance evidence, verification ceiling, known side
  effects, and stop condition. No valid lock, no child launch.
- Apply the same lock to the main session's planning, repository inspection,
  routing preflight, verification, retries, and integration. Do not inspect
  package internals or optional continuity data unless a concrete admission
  failure or repeated-objective reuse makes that read necessary inside the
  declared ceiling.
- Every default, ladder step, and Checker route must resolve to an installed
  package role with the exact configured model and effort. Reject arbitrary
  jumps, stale counters, exhausted retries, and silent substitutions.
- Escalate only from observable evidence: failed acceptance checks,
  contradictions, missed constraints, truncation/context evidence,
  runtime/tool errors, capability ceilings, or a weak oracle. Hidden reasoning
  is not evidence.
- Keep authentication, audit logs, rollout/session data, and continuity
  records out of the repository. Do not commit or deploy `~/.codex/state/**`,
  `auth.json`, or equivalent runtime state.
- Integration finalization is a post-execution same-user integrity check. It
  must bind the terminal event, packet, child, output/worktree, evidence, and a
  distinct Checker session, but it is not a signature or separate security
  principal.

The skill constructs its self-contained Objective Lock from the current user
request and repository evidence. A user-global or project `AGENTS.md` may
further restrict the task but is never a required runtime dependency. While
this skill is active, every packet and main-authority takeover preserves the
same lock; a materially broader objective requires a new, explicitly
authorized task or packet.

The policy source is
`adaptive-delegation/config/model-routing.defaults.json`; explanatory rules
live in `adaptive-delegation/references/MODEL_ROUTING_POLICY.md`. Continuity
guidance is in `adaptive-delegation/TOKEN_EFFICIENCY_CONTINUITY.md`.

## Change and review rules

Keep diffs minimal, preserve unrelated work, and prefer existing utilities and
tests over new abstractions or dependencies. Every change must state its
implementation envelope (objective, non-goals, owned files, acceptance
evidence, verification ceiling, and stop condition). Use a bounded Maker for
implementation and an independent Checker when risk warrants it; integration
acceptance is separate from a child process merely exiting successfully.
Public issue reports must use the local allowlisted formatter in
`REPORTING.md`; raw ledgers never leave the machine.

Every change that alters the installed `adaptive-delegation/` package must bump
the Semantic Version in `adaptive-delegation/VERSION` and add the corresponding
entry to `CHANGELOG.md`. Use `scripts/version_status.py` to compare repository
and installed packages; never infer equality from a version string alone.

Do not run `git init`, GitHub creation, remote setup, commits, pushes, or other
Git/GitHub mutations as part of ordinary maintenance. Run them only when the
user explicitly authorizes that repository operation.

## Required verification

From this directory, run the smallest relevant checks and report their exact
results. The package baseline is:

```sh
python3 scripts/install.py --dry-run
python3 -m unittest -v tests.test_install tests.test_dispatcher_gate tests.test_version_status
python3 -m unittest discover -v -s adaptive-delegation/tests -p 'test_*.py'
```

For documentation-only changes, at minimum inspect the diff, confirm every
relative link target exists, and run the dry-run plus the unit-test commands
above before claiming completion.
