$adaptive-delegation

Maintain the standalone `adaptive-delegation` repository.
This is a Codex-only skill for Codex native subagents; Claude Code is
unsupported.

Objective: `<describe the bounded maintenance objective>`
Owned mutable surfaces: `<list exact files or directories>`
Acceptance evidence: `<name the observable checks that prove the objective>`
Stop condition: `<state when to stop and hand back to the main>`

Before changing anything, read `AGENTS.md`,
`adaptive-delegation/SKILL.md`,
`adaptive-delegation/references/MODEL_ROUTING_POLICY.md`, and
`adaptive-delegation/TOKEN_EFFICIENCY_CONTINUITY.md`. Read only the latest
three relevant accepted continuity records when routing requires them. Treat
repository files as canonical; installed `~/.codex` files are deployment
targets, not edit-first sources.

Use a bounded Maker for the implementation and an independent Checker for
acceptance when risk warrants it. Keep ownership disjoint, record observable
evidence and any scope expansion, and have the Checker (or the sole verified
executor when no Checker is used) record the compact handoff. Update and test
the repository source first. Do not edit installed artifacts directly.

Keep the change portable and minimal. Preserve Luna-first routing, effort-first
Luna escalation, fixed Native Luna/Sol leaf role bindings, dormant Terra
experiment isolation, the Sol `high`-or-above main gate, leaf-`ultra`
prohibition, observable-evidence escalation, machine-local
logs/state exclusion, and the repository-as-canonical rule. Do not add
dependencies or alter product behavior without an explicit envelope. Model or
reasoning escalation changes capability, not authority or scope. Stop when the
declared acceptance evidence passes; put unrelated cleanup, redesign, and
polishing into backlog findings unless a new task explicitly authorizes them.

Run the relevant portable checks, normally:

```sh
python3 scripts/install.py --dry-run
python3 -m unittest -v tests.test_install tests.test_dispatcher_gate
python3 -m unittest discover -v -s adaptive-delegation/tests -p 'test_*.py'
```

When installation behavior is in scope, also dry-run against a temporary
`CODEX_HOME` and verify that no authentication, audit, continuity, rollout,
session, or runtime state files are copied. Perform a secret/privacy scan of
the diff and generated artifacts; redact or remove credentials, cookies,
tokens, and machine-local paths before handoff.

Before any user-level install or update, the isolated promotion gate is
mandatory: run `python3 -m unittest -v tests.test_isolated_dogfood` and then
`python3 scripts/verify_isolated_dogfood.py --auth-source <read-only-auth-file>`.
It uses a temporary candidate home and auth symlink; it is a same-user quality
guard, not a security boundary. Do not proceed from unit tests directly to a
user-level install: request and receive explicit later user approval after the
gate passes.

Do not run Git/GitHub mutations (`git init`, `git add`, commits, remote setup,
repository creation, or pushes) unless the user separately requests that
scope. Finish with changed files, exact commands and results, link/test
evidence, known gaps, and the recommended next handoff.
