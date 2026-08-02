# Adaptive Delegation

**Codex-only skill:** this repository packages a skill for Codex native subagents.
Claude Code and other agent runtimes are not supported execution targets.

`adaptive-delegation` routes bounded Codex work through a Luna-first policy,
raises Luna effort before model tier, and then uses fixed Sol leaf roles only
when observable evidence requires more capability. It records observable
outcomes, permits only declared role/model/effort transitions, and returns
unresolved work to the main Codex session when the leaf ladder is exhausted or
the acceptance oracle is weak.

Its primary invariant is: delegate bounded independent work aggressively, but
only inside one portable Objective Lock. No valid lock means no child launch;
no external `AGENTS.md` is required to construct or enforce the packaged lock.

The repository and its packaged policy are canonical. Installed copies are
deployment targets, not additional policy sources.

For prompt-driven installation or updates on another developer's computer,
send Codex the copy-paste workflow in
[`CODEX-INSTALL-PROMPT.md`](CODEX-INSTALL-PROMPT.md). It authorizes the final
user-level install only after validation and isolated promotion pass.

## What the skill validates and requires

The dispatcher fails closed on the typed/direct paths it owns. Native child
and main-takeover scope rules are agent obligations plus local post-hoc
consistency checks; they are not an operating-system security boundary.

- The declared main session must be `gpt-5.6-sol` at `high`, `xhigh`, `max`, or
  `ultra` before a package-owned child can launch.
- Every default and escalation step resolves to an installed, package-declared
  Codex role with an exact model and reasoning effort.
- Leaf `ultra` and silent model substitution are forbidden.
- Model or reasoning escalation changes capability, not authority or scope.
  The policy requires every child and main-authority takeover to stay inside
  the canonical Objective Lock: objective, non-goals, read/write/network
  authority, intended behavior, acceptance evidence, verification ceiling,
  known side effects, and stop condition. Once the declared evidence is
  satisfied, work stops; additional reviews, repeated validation, optional
  model consultations, adjacent redesign, or polishing require a new explicit
  task.
- The same lock binds main-side planning, repository inspection, routing
  preflight, verification, retry decisions, and integration. A fresh one-shot
  task with complete acceptance evidence skips continuity and does not reopen
  optional package internals.
- Retry and escalation decisions must follow observable failure evidence and a
  contiguous route history. Arbitrary jumps and exhausted same-route retries
  fail closed.
- A successful child process is not local integration finalization. Optional
  local integration receipts are evaluated only after execution and must
  match the exact packet, Objective Lock digest, child terminal result,
  output/worktree digests, route, and a distinct-session Checker.
- Successful execution remains pending in the append-only routing ledger until
  integration finalization succeeds. Receipt or pre-gate failures can be
  corrected only with the same installed terminal/receipt/audit schema.
- Before updating from terminal/receipt v1 and audit `0.2.0`, finalize every
  pending attempt. After the update, an old pending chain remains readable
  evidence but deliberately cannot be finalized or backfilled. Re-execute it
  as a fresh chain with a new task ID, attempt index 1, dispatch ID, packet, and
  v2 terminal/receipt plus `0.3.0` audit records.
- Before updating from package `1.x`, finalize every pending Objective Lock v1
  chain. Version 2 keeps v1 audit evidence readable but starts new work with a
  fresh task ID and Objective Lock v2; it never continues a task across lock
  versions.
- Before updating from package `2.x`, finalize pending attempts because package
  3 changes the routing-policy fingerprint. Historical Terra records remain
  readable, but unfinished work restarts at attempt index 1 under the new
  Luna-to-Sol ladder.

The main-profile eligibility gate uses declared current-session context; main
authority comes from the user/control topology, not from model capability.
Local receipts provide same-user integrity and consistency checks; they are
not signatures, remote attestation, proof of semantic correctness, or a
security boundary against a malicious process running as the same
operating-system user.

The dispatcher renders one route-independent canonical Objective Lock v2 JSON
for both Native and typed execution. Its version and SHA-256 consistency digest
remain identical across retries, effort/model escalation, and main takeover;
linked audit schema `0.3.0` rejects a changed digest or mixed `0.2.0`/`0.3.0`
task history. This detects local contract drift on dispatcher-owned paths; it
does not prove semantic correctness or create a security principal.

## Activate the skill

Use `$adaptive-delegation` explicitly when deterministic activation matters.
Implicit activation is also available for matching requests. The skill
frontmatter contains the only two localized trigger literals; all other package
documentation is English. See
[`adaptive-delegation/references/TRIGGERS.md`](adaptive-delegation/references/TRIGGERS.md).

## Invocation and `ultra` reasoning behavior

Skill activation and reasoning effort are separate decisions. Invoking the
skill does not change the running main model or its effort, and requesting
`ultra` does not grant `ultra` to a child.

| Request form | Activation behavior | Model and effort behavior |
| --- | --- | --- |
| `$adaptive-delegation ...` | Deterministic explicit activation. | The main-authority gate runs, an Objective Lock is created, and bounded work follows the Luna-first route. |
| `$adaptive-delegation ... Use ultra reasoning.` | Deterministic explicit activation. | `ultra` applies to the main only if the current runtime is already configured as `gpt-5.6-sol/ultra`. Prompt text cannot upgrade the session. Leaf `ultra` remains forbidden. |
| A bounded task request containing either localized token-efficiency literal declared in the skill frontmatter | Eligible for implicit activation because the localized literal is in the skill description and implicit invocation is enabled. Explicit `$adaptive-delegation` remains the deterministic choice. | If activated, it runs the same Objective Lock and Luna-first workflow as explicit invocation. |
| The same localized token-efficiency request plus `Use ultra reasoning.` | Eligible for implicit activation because of the localized token-efficiency literal, not because of `ultra`. | An already-`ultra` main remains the authority; bounded children still use fixed Luna/Sol leaf roles and never inherit main `ultra`. |
| `Use ultra reasoning.` | Does not activate this skill by itself. | Normal session-level model and effort rules apply. |

A localized trigger must occur in an actionable delegation, implementation, or
verification request. Quoting the word, translating it, or asking only for its
definition does not request adaptive routing.

After activation, the workflow is identical for explicit and implicit entry:

1. Validate that the current main is `gpt-5.6-sol` at `high` or above. The
   skill cannot mutate a failing parent configuration.
2. Construct one portable Objective Lock before any child launch.
3. Route simple work to Luna `medium`, clear implementation to Luna `high`, and
   bounded complex work to Luna `xhigh`.
4. Escalate only from observable failure evidence, preserving the exact lock.
   Luna effort may rise through `max`; the route may then move to fixed Sol
   `medium` and `high` leaf roles, but leaf `ultra` is never allowed.
5. Keep weak-oracle, ambiguous, high-risk, or long-contract work with the main
   at `gpt-5.6-sol/ultra`, or return exhausted leaf work to that main takeover.
6. Stop as soon as the locked acceptance evidence passes. Do not add another
   review or broader verification merely because the main has `ultra` effort.

The fixed automatic paths are:

| Work shape | Fixed path |
| --- | --- |
| Simple lookup or extraction | `Luna medium -> high -> xhigh -> max -> Sol medium -> main Sol ultra` |
| Clear implementation or transformation | `Luna high -> xhigh -> max -> Sol medium -> Sol high -> main Sol ultra` |
| Bounded complex implementation or verification | `Luna xhigh -> max -> Sol medium -> Sol high -> main Sol ultra` |
| Weak oracle, ambiguous/high-risk, or long contract | `main Sol ultra` |

Terra is not part of any automatic path. Terra `max` remains a dormant binding
for a future versioned A/B experiment and cannot be selected by the current
default, failure-action, or human-override contract. Historical Terra logs
remain readable; later routing changes should be based on representative
accepted-task quality, latency, weighted tokens, and total cost.

## Install from GitHub

Python 3.11 or newer is required.

```sh
git clone https://github.com/ai-dev-methodologies/adaptive-delegation.git
cd adaptive-delegation
python3 scripts/install.py --dry-run
python3 -m unittest -v tests.test_install tests.test_dispatcher_gate tests.test_isolated_dogfood tests.test_version_status
python3 -m unittest discover -v -s adaptive-delegation/tests -p 'test_*.py'
python3 scripts/verify_isolated_dogfood.py --auth-source /path/to/read-only-auth.json
# With explicit user approval only:
python3 scripts/install.py
```

The default target is `$CODEX_HOME`, or `~/.codex` when `CODEX_HOME` is unset.
Use `--codex-home /path/to/.codex` for another target. The installer replaces
each managed target safely, preserves unrelated roles and existing directory
permissions, and removes only stale adaptive roles declared by the previously
installed package.

The installer never copies authentication, audit logs, continuity records, or
rollout/session data. Those remain local to the machine that created them.
The isolated promotion gate is mandatory before user-level installation; it is
a same-user quality guard, not a security boundary. See [`INSTALL.md`](INSTALL.md)
for its temporary-auth-symlink workflow and the explicit later approval step.
For the complete install, update, rollback, and second-PC workflow, see
[`INSTALL.md`](INSTALL.md).

## Validate the package

```sh
python3 scripts/install.py --dry-run
python3 -m unittest -v tests.test_install tests.test_dispatcher_gate tests.test_isolated_dogfood tests.test_version_status
python3 -m unittest discover -v -s adaptive-delegation/tests -p 'test_*.py'
```

Codex normally detects installed skill changes automatically. Restart Codex
only if the updated skill is not visible after installation.

## Version and update comparison

[`adaptive-delegation/VERSION`](adaptive-delegation/VERSION) is the canonical
Semantic Version and is copied into every installed package. Human-readable
release changes are recorded in [`CHANGELOG.md`](CHANGELOG.md). Installable
package changes must update both files.

Compare a checkout with the installed package without changing either:

```sh
python3 scripts/version_status.py
```

Use `--codex-home /path/to/.codex` for another target or `--json` for stable
machine-readable output. The command reports versions, package digests, and
relative `source_only`, `installed_only`, and `modified` paths. A matching
version with a different digest is `same_version_drift`; an older unversioned
installation is `installed_unversioned`.

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
- [`CODEX-INSTALL-PROMPT.md`](CODEX-INSTALL-PROMPT.md) — copy-paste Codex CLI
  installation and update prompts.
- [`CHANGELOG.md`](CHANGELOG.md) and
  [`adaptive-delegation/VERSION`](adaptive-delegation/VERSION) — release
  history and installed package version.
- [`REPORTING.md`](REPORTING.md) — privacy-safe issue workflow.
- [`AGENTS.md`](AGENTS.md) — repository maintenance rules.

Canonical repository:
<https://github.com/ai-dev-methodologies/adaptive-delegation.git>
