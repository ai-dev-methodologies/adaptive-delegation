# Adaptive Delegation

**Codex-only skill:** this repository packages a skill for Codex native subagents.
Claude Code and other agent runtimes are not supported execution targets.

`adaptive-delegation` routes bounded Codex work through a Luna-first,
effort-first policy. It records observable outcomes, permits only declared
role/model/effort transitions, and returns unresolved work to the main Codex
session when the leaf ladder is exhausted or the acceptance oracle is weak.

The repository and its packaged policy are canonical. Installed copies are
deployment targets, not additional policy sources.

## What the skill enforces

- The declared main session must be `gpt-5.6-sol` at `high`, `xhigh`, `max`, or
  `ultra` before a package-owned child can launch.
- Every default and escalation step resolves to an installed, package-declared
  Codex role with an exact model and reasoning effort.
- Leaf `ultra` and silent model substitution are forbidden.
- Retry and escalation decisions must follow observable failure evidence and a
  contiguous route history. Arbitrary jumps and exhausted same-route retries
  fail closed.
- A successful child process is not integration acceptance. Optional local
  integration receipts are evaluated only after execution and must match the
  exact packet, child terminal result, output/worktree digests, route, and a
  distinct Checker session.
- Successful execution remains pending in the append-only routing ledger until
  integration finalization succeeds; receipt or pre-gate finalization failures
  remain pending, and only a successful finalization records acceptance.

The main-authority gate uses declared current-session context. Local receipts
provide same-user integrity and consistency checks; they are not signatures,
remote attestation, or a security boundary against a malicious process running
as the same operating-system user.

## Activate the skill

Use `$adaptive-delegation` explicitly when deterministic activation matters.
Implicit activation is also available for matching requests. The skill
frontmatter contains the only two localized trigger literals; all other package
documentation is English. See
[`adaptive-delegation/references/TRIGGERS.md`](adaptive-delegation/references/TRIGGERS.md).

## Install from GitHub

Python 3.11 or newer is required.

```sh
git clone https://github.com/ai-dev-methodologies/adaptive-delegation.git
cd adaptive-delegation
python3 scripts/install.py --dry-run
python3 scripts/install.py
```

The default target is `$CODEX_HOME`, or `~/.codex` when `CODEX_HOME` is unset.
Use `--codex-home /path/to/.codex` for another target. The installer replaces
each managed target safely, preserves unrelated roles and existing directory
permissions, and removes only stale adaptive roles declared by the previously
installed package.

The installer never copies authentication, audit logs, continuity records, or
rollout/session data. Those remain local to the machine that created them.
For the complete install, update, rollback, and second-PC workflow, see
[`INSTALL.md`](INSTALL.md).

## Validate the package

```sh
python3 scripts/install.py --dry-run
python3 -m unittest -v tests.test_install tests.test_dispatcher_gate
python3 -m unittest discover -v -s adaptive-delegation/tests -p 'test_*.py'
```

Codex normally detects installed skill changes automatically. Restart Codex
only if the updated skill is not visible after installation.

## Audit logs and GitHub issues

Routing attempts are stored locally in
`$CODEX_HOME/state/model-routing/attempts.jsonl` (default
`~/.codex/state/model-routing/attempts.jsonl`). Raw ledgers contain local
identifiers and must never be uploaded.

Generate an allowlisted Markdown summary instead:

```sh
python3 adaptive-delegation/scripts/model_routing_audit.py issue-report
```

The formatter reads the local ledger without modifying it and never creates a
missing ledger or parent directory. Its Markdown report body prints no task or
session identifiers, paths, prompts, evidence text, commands, or URLs; rejected
input receives a generic error that does not echo ledger content or paths. It
does not publish anything. Inspect the output before pasting it into the
repository's routing-report issue template. See [`REPORTING.md`](REPORTING.md).

## Repository map

- [`adaptive-delegation/SKILL.md`](adaptive-delegation/SKILL.md) — Codex skill
  workflow and operational contract.
- [`adaptive-delegation/config/model-routing.defaults.json`](adaptive-delegation/config/model-routing.defaults.json)
  — package policy source of truth.
- [`adaptive-delegation/references/MODEL_ROUTING_POLICY.md`](adaptive-delegation/references/MODEL_ROUTING_POLICY.md)
  — rationale, ladders, failure actions, and metrics.
- [`INSTALL.md`](INSTALL.md) — installation and cross-PC operations.
- [`REPORTING.md`](REPORTING.md) — privacy-safe issue workflow.
- [`AGENTS.md`](AGENTS.md) — repository maintenance rules.

Canonical repository:
<https://github.com/ai-dev-methodologies/adaptive-delegation.git>
