# Adaptive Delegation Repository Governance

This directory is the standalone, portable source repository for the
`adaptive-delegation` skill. Repository files are canonical. Installed copies
under `~/.codex/skills/adaptive-delegation/`, `~/.codex/scripts/`, and
`~/.codex/agents/` are deployment targets; never edit an installed copy first
and then try to back-port the change. Update this repository, verify it, and
run `scripts/install.py` only when deployment is requested.

## Policy invariants

- Keep routing Luna-first and effort-first. Bounded work starts on the lowest
  suitable Luna effort and escalates from observable evidence.
- The main-authority gate is fail-closed: the main must be
  `gpt-5.6-sol` with reasoning effort `high`, `xhigh`, `max`, or `ultra` before
  delegation can launch.
- Native Luna uses the fixed, package-declared role bindings in
  `adaptive-delegation/roles/*.toml`. Verify the bound model and effort; do
  not silently substitute Terra when Luna admission is rejected.
- Leaf `ultra` is forbidden. `gpt-5.6-sol/ultra` is a main-authoritative
  takeover only.
- Escalate only from observable evidence: failed acceptance checks,
  contradictions, missed constraints, truncation/context evidence,
  runtime/tool errors, capability ceilings, or a weak oracle. Hidden reasoning
  is not evidence.
- Keep authentication, audit logs, rollout/session data, continuity records,
  and local policy overrides machine-local. Do not commit or deploy
  `~/.codex/state/**`, `auth.json`, or equivalent local state.
- Preserve legacy OMX read compatibility: `~/.codex/.omx-config.json` is a
  read-compatible fallback only, never the policy source of truth and never a
  file this package writes.

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
process merely exiting successfully.

Do not run `git init`, GitHub creation, remote setup, commits, pushes, or other
Git/GitHub mutations as part of ordinary maintenance. Run them only when the
user explicitly authorizes that repository operation.

## Required verification

From this directory, run the smallest relevant checks and report their exact
results. The package baseline is:

```sh
python3 scripts/install.py --dry-run
python3 -m unittest -v tests.test_install tests.test_dispatcher_gate
python3 -m unittest discover -v -s adaptive-delegation/tests -p 'test_*.py'
```

For documentation-only changes, at minimum inspect the diff, confirm every
relative link target exists, and run the dry-run plus the unit-test commands
above before claiming completion.
