# Adaptive Delegation

**Codex-only skill:** this repository packages explicit, evidence-backed
delegation through Codex native subagents. Claude Code and other agent runtimes
are unsupported execution targets.

Current installable package version: `0.8.1`.

`adaptive-delegation` is explicit and opt-in, and it is hook-free. A prompt activates it
only when its first non-whitespace token is `$adaptive-delegation`. It installs
no `UserPromptSubmit`, `PreToolUse`, `Stop`, or other hook and does not read or
write OMX, Ultragoal, Ultracode, or other host workflow state. When inactive it
has no process, state, tool, or permission effect. Bare names and natural
language mentions do not activate it.

The main session is controller-only in the sense that it owns intent, routing,
integration, and final claims; this is a skill procedure, not a global hook
that blocks tools. The package requires declared current-session context of
`gpt-5.6-sol` with `high`, `xhigh`, `max`, or `ultra` effort before a package
leaf launches. Prompt text cannot upgrade the session. Model or reasoning escalation changes capability, not authority or scope.

The central rule is one portable Objective Lock per terminal outcome. It binds
the terminal outcome, non-goals, read/write/network authority, authorized
lanes, progression policy, verification ceiling, and stop conditions. Every
Maker, Checker, retry, escalation, and takeover inherits it. A blocked lane
returns to main for another authorized path; final BLOCKED requires evidence
that none remains.

## What the skill validates and requires

- Main selects an exact package role from task shape, oracle strength, risk,
  ambiguity, latency sensitivity, horizon, and recoverability.
- Every default resolves to an installed `adaptive-*` role with fixed model and
  effort. Silent substitution is forbidden.
- Main starts at the lowest suitable Luna effort and escalates only from
  observable evidence.
- A bounded Maker owns implementation; a distinct Checker is used only when
  risk or the integration contract requires it. The optional receipt path uses
  `adaptive-sol-checker-medium`.
- Main accepts the integrated evidence and stops as soon as the declared oracle
  passes. Additional reviews and adjacent work are out of scope.
- Leaf `ultra` remains forbidden.

The fixed ladders are:

| Work shape | Fixed path |
| --- | --- |
| Simple lookup or extraction | `Luna medium -> Luna high -> Luna xhigh -> Luna max -> Terra medium -> Sol medium -> main Sol ultra` |
| Clear implementation or transformation | `Luna high -> Luna xhigh -> Luna max -> Terra medium -> Sol medium -> Sol high -> main Sol ultra` |
| Bounded complex implementation or verification | `Luna xhigh -> Luna max -> Terra high -> Sol medium -> Sol high -> main Sol ultra` |
| Latency-insensitive long horizon with a strong oracle and low/medium risk | `Luna max -> Terra xhigh -> Terra max -> Sol high -> main Sol ultra` |
| Weak oracle, ambiguous/high risk, or long contract | `main Sol ultra` |

Workflow labels such as `Goal` or `Ultragoal` are not route inputs. The detailed
runtime contract is in
[`adaptive-delegation/SKILL.md`](adaptive-delegation/SKILL.md), with the role
flow in [`docs/DELEGATION-FLOW.md`](docs/DELEGATION-FLOW.md).

## Activate the skill

Start the prompt with:

```text
$adaptive-delegation <bounded task and acceptance evidence>
```

Codex loads the skill normally. There is no activation command, hook preflight,
global controller state, or host workflow transition. The main constructs the
Objective Lock, verifies the chosen installed role, and launches a native leaf
directly. See
[`adaptive-delegation/references/TRIGGERS.md`](adaptive-delegation/references/TRIGGERS.md).

## Invocation and `ultra` reasoning behavior

Skill activation and reasoning effort are separate decisions.

| Request | Result |
| --- | --- |
| `$adaptive-delegation ...` | Explicit activation; declared Sol/high-or-above main applies the routing policy. |
| `$adaptive-delegation ... Use ultra reasoning.` | Activates the skill, but `ultra` applies only if the main is already configured for it. Prompt text cannot upgrade the session. Leaf `ultra` remains forbidden. |
| A bare mention or quotation | Does not activate this skill by itself. |
| A localized token-efficiency phrase | Discovery only; does not activate this skill by itself. |
| `Use ultra reasoning.` | Does not activate this skill by itself. |

## Hook-free compatibility contract

The installer manages only the skill package, optional dispatcher, and
package-declared roles. It installs no hooks. On update it removes only exact
legacy adaptive `controller_gate.py` registrations and their matching trust
entries, including its exact direct-command approval rule; all foreign hooks,
rules, Stop owners, and host configuration remain intact.

This gives the same activation behavior in plain Codex, Codex with OMX, Codex
with Ultracode, or a process containing both. Those hosts may impose their own
policy, but adaptive neither depends on nor modifies it. A foreign hook failure
is returned to main as a path-local runtime failure; adaptive never asks the
user to mutate another workflow's phase or state.

The controller hook program is not part of the package. Historical controller
records remain readable by aggregate audit tooling, but activation never
registers or calls a controller hook.

## Optional dispatcher and evidence

Native fixed-role routing is the default. The packaged typed dispatcher is an
optional helper for hard-cap, receipt, or audit scenarios. It is not a hook and
does not activate the skill. Its weighted budget is
`ceil(input_tokens / 4) + output_tokens`, a routing proxy rather than provider
billing.

Read-only aggregate health is available through:

```sh
python3 adaptive-delegation/scripts/model_routing_audit.py health
```

Raw attempts, reviews, continuity, `dispatch_attestation.jsonl`,
`issue-report-state.jsonl`, credentials, and rollout/session data remain local.
Use the allowlisted formatter described in [`REPORTING.md`](REPORTING.md) and
the packaged [`CODEX-ISSUE-REPORT-PROMPT.md`](adaptive-delegation/references/CODEX-ISSUE-REPORT-PROMPT.md)
for public reports.

## Install from GitHub

Python 3.11 or newer is required.

```sh
git clone https://github.com/ai-dev-methodologies/adaptive-delegation.git
cd adaptive-delegation
python3 scripts/release_preflight.py --mode deploy
python3 scripts/install.py --dry-run
python3 -m unittest -v tests.test_install tests.test_dispatcher_gate tests.test_version_status tests.test_release_preflight
python3 -m unittest discover -v -s adaptive-delegation/tests -p 'test_*.py'
python3 scripts/verify_isolated_dogfood.py --auth-source /path/to/read-only-auth.json
# With explicit user approval only:
python3 scripts/install.py
```

The default target is `$CODEX_HOME`, or `~/.codex` when unset. The installer
does not copy authentication or runtime state. Full installation and rollback
rules are in [`INSTALL.md`](INSTALL.md); the copy-paste workflow is
[`CODEX-INSTALL-PROMPT.md`](CODEX-INSTALL-PROMPT.md).

## Validate the package

```sh
python3 scripts/install.py --dry-run
python3 -m unittest -v tests.test_install tests.test_dispatcher_gate tests.test_version_status tests.test_release_preflight
python3 -m unittest discover -v -s adaptive-delegation/tests -p 'test_*.py'
python3 scripts/verify_isolated_dogfood.py --auth-source /path/to/read-only-auth.json
```

After installation, a fresh Codex process should discover the updated skill.
No hook topology restart is required by this package.

## Maintainer promotion and local deployment order

`main` is the only deployable branch. Review this README against the skill,
policy, version, installer, and reporting behavior before merging.

1. On the feature branch, run `scripts/release_preflight.py --mode pre-merge`,
   then push the reviewed commit.
2. Merge through the repository's authorized workflow.
3. Fetch the remote and run `scripts/release_preflight.py --mode deploy` from a
   clean `main` or detached checkout exactly matching `origin/main`.
4. Run the dry run and required tests before the separately approved user-level
   install.

## Version and update comparison

Run `python3 scripts/version_status.py` to compare repository and installed
versions plus content digests. Version strings alone do not prove equality.
Release history is in [`CHANGELOG.md`](CHANGELOG.md).

## Local experience and GitHub issues

Do not publish raw ledgers. Generate an allowlisted report, inspect it, and
record every submitted Report ID with `record-submission` so later reports omit
covered attempt fingerprints.

## Repository map

| Path | Purpose |
| --- | --- |
| `adaptive-delegation/SKILL.md` | Runtime instructions |
| `adaptive-delegation/config/model-routing.defaults.json` | Routing source of truth |
| `adaptive-delegation/roles/` | Fixed native role bindings |
| `adaptive-delegation/scripts/` | Optional dispatcher, diagnostics, and audit tools |
| `scripts/install.py` | Hook-free installer and legacy hook cleanup |
| `scripts/release_preflight.py` | Merge/deploy release gate |
| `docs/DELEGATION-FLOW.md` | Role and evidence flow |
