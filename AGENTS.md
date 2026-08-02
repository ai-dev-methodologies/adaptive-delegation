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

- Keep routing Luna-first and effort-first. Bounded work starts on the lowest
  suitable Luna effort and escalates from observable evidence.
- The main-authority gate is fail-closed over declared current-session context:
  the main must be `gpt-5.6-sol` with reasoning effort `high`, `xhigh`, `max`,
  or `ultra` before delegation can launch. Do not describe this declaration as
  cryptographic runtime proof.
- Native Luna uses the fixed, package-declared role bindings in
  `adaptive-delegation/roles/*.toml`. Verify the bound model and effort; do
  not silently substitute Terra when Luna admission is rejected.
- Leaf `ultra` is forbidden. `gpt-5.6-sol/ultra` is a main-authoritative
  takeover only.
- Model or reasoning escalation changes capability, never authority or scope.
  A main takeover inherits the exact objective, write scope, acceptance
  evidence, and stop condition of the unresolved slice and must stop when
  those acceptance conditions are proved.
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

The calling request or current main-session `AGENTS.md` remains responsible for
general scope discipline outside an active adaptive-delegation workflow. It
should state the intended outcome, non-goals, allowed write set, acceptance
evidence, and stop condition. While this skill is active, the packet and every
main-authority takeover preserve that boundary; a materially broader objective
requires a new, explicitly authorized task or packet.

The policy source is
`adaptive-delegation/config/model-routing.defaults.json`; explanatory rules
live in `adaptive-delegation/references/MODEL_ROUTING_POLICY.md`. Continuity
guidance is in `adaptive-delegation/TOKEN_EFFICIENCY_CONTINUITY.md`.

## Change and review rules

Keep diffs minimal, preserve unrelated work, and prefer existing utilities and
tests over new abstractions or dependencies. Every change must state its
implementation envelope (objective, owned files, acceptance evidence, and
stop condition). Use a bounded Maker for implementation and an independent
Checker when risk warrants it; integration acceptance is separate from a child
process merely exiting successfully. Public issue reports must use the local
allowlisted formatter in `REPORTING.md`; raw ledgers never leave the machine.

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
