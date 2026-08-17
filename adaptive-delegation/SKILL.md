---
name: adaptive-delegation
description: Codex-only skill for Codex native subagents. Use only when the user explicitly prefixes the request with $adaptive-delegation to route bounded work with Objective Locks, fixed Luna-first roles, evidence-based escalation, and token-efficient verification. Discovery terms include 토큰효율화 and 토큰 효율화, but those terms never activate the skill.
---

# Adaptive Delegation

Use this skill only for a user prompt whose first non-whitespace token is
`$adaptive-delegation`. A quotation, explanation, continuation, localized
discovery term, or bare mention does not activate it.

This package is hook-free. Do not install, register, require, or call a
`UserPromptSubmit`, `PreToolUse`, `Stop`, or other host hook. Do not read or
write another workflow's state. Do not require OMX, Ultragoal, Ultracode, a
user-global `AGENTS.md`, or any host-specific controller to activate or route
work. When inactive, this package has no process, state, tool, or permission
effect.

The main session owns intent, route selection, integration, and final claims.
Require declared current-session context of `gpt-5.6-sol` with reasoning
effort `high`, `xhigh`, `max`, or `ultra` before launching a package leaf.
This is a declaration, not cryptographic runtime proof. Prompt text cannot
upgrade the session. Leaf `ultra` is forbidden.

Load this file through normal skill loading. Run no activation continuation or
shell preflight. Build the lock, inspect only the selected role binding, and
launch the native leaf directly. A child routing mismatch cancels only that
launch and returns control to main; it is not a task blocker.

## Primary invariant — Objective Lock

Before the first child launch, construct one portable **OBJECTIVE LOCK** from
the user request and repository evidence. No valid Objective Lock, no child launch.

The lock contains:

- terminal outcome and acceptance evidence;
- non-goals (`non_goals`);
- read, write, and network authority;
- authorized lanes and collision ownership;
- progression policy and global terminal conditions; and
- side-effect and verification ceilings.

Keep the current method, data source, stage, test plan, path-local verification,
and path stop condition in a replaceable path envelope. Every Maker, Checker,
retry, escalation, and main takeover inherits the exact terminal-outcome lock.
Model or reasoning escalation changes capability, never authority or scope.

The lock binds the main session too. Main planning, inspection, routing,
verification, retry, and integration must remain inside the same authority and
verification ceiling. A blocked lane returns to main for another authorized
lane. Final BLOCKED requires evidence that no meaningful authorized lane
remains. Never fabricate evidence, and do not silently turn a takeover into a redesign.

Stop as soon as the declared acceptance evidence passes. Do not add optional
work, adjacent improvements, additional reviews, or broad verification.

## Policy source and routing defaults

Use `config/model-routing.defaults.json` as the routing source of truth. Select
the route from task shape, oracle strength, risk,
ambiguity, latency sensitivity, horizon, and recoverability. Workflow names
and other runtime state are never route inputs.

Use these fixed Maker ladders:

- Simple lookup or extraction: Luna medium -> high -> xhigh -> max -> Terra
  medium -> Sol medium -> main Sol ultra.
- Clear implementation or transformation: Luna high -> xhigh -> max -> Terra
  medium -> Sol medium -> Sol high -> main Sol ultra.
- Bounded complex implementation, debugging, or review: Luna xhigh -> max ->
  Terra high -> Sol medium -> Sol high -> main Sol ultra.
- Latency-insensitive long-horizon work with a strong oracle and low/medium
  risk: Luna max -> Terra xhigh -> Terra max -> Sol high -> main Sol ultra.
- Weak-oracle, ambiguous, high-risk, or long-contract work: main Sol ultra.

Start at the lowest suitable Luna effort. Escalate only from observable failed
acceptance checks, contradictions, missed constraints, truncation or context
evidence, runtime/tool errors, capability ceilings, or a weak oracle. Hidden
reasoning is not evidence. Ordinary Terra use is `medium` or `high`; Terra
`xhigh`/`max` is restricted to the quota-first long-horizon ladder after an
observable Luna failure.

## Native leaf procedure

Prefer Native V2 through a verified fixed `agent_type`. Select the installed
package role whose TOML fixes the exact model and reasoning effort. Inspect the
live child schema and installed role before every launch; do not reuse stale
capability claims.

The absence of a selected model from the optional `model` override enum does not
reject a Native route when the fixed `agent_type` is installed. In that mode,
prefer Native V2 through a verified fixed `agent_type`; omitting the optional
model field is not leader-model inheritance. Select the installed package role
and pass `fork_turns="none"`, an explicit task name, and the role's exact effort.

Send every child the complete Objective Lock plus a narrow packet containing:

- one bounded objective and owned files or responsibility;
- non-goals, read/write/network authority, and side effects;
- acceptance evidence and verification ceiling;
- resource/token guidance and stop condition; and
- a warning that other agents may be editing the workspace and their changes
  must not be reverted.

Use a bounded Maker for implementation. Use a distinct-session Checker only
when risk or the integration contract warrants independent evidence. Checker
capability follows oracle shape and risk, not a blanket rule that it exceed the
Maker. Main performs final integration acceptance.

If child creation, tools, or routing are rejected, preserve the same lock and
try an in-scope authorized lane. Do not silently substitute another model,
widen scope, ask the user to mutate unrelated workflow state, or report final
BLOCKED while meaningful authorized work remains.

## Optional deterministic helpers

The package dispatcher and audit utilities are optional, on-demand helpers.
They do not activate this skill and are never host hooks. Use them only when a
task needs their typed receipt, hard-cap, or audit behavior. Native child
routing does not require a shell preflight.

The typed dispatcher budget is `ceil(input_tokens / 4) + output_tokens`.
This is a routing proxy, not a provider billing amount. Use it only for
token-effective route evidence. Model-relative price factors are not
cross-model currency; missing usage is unavailable, never zero.

The controller hook program is not part of this package. The installer removes
legacy package-owned hook and trust entries while preserving foreign hooks.

## Evidence, continuity, and completion

Accept a leaf only from observable artifacts: changed files, test output,
structured results, or bounded local evidence references. A child process exit
is not integration acceptance. Record route fitness and quality only when the
selected helper requires it; normal Native execution may report the evidence
directly to main.

Continuity is an optimization, not a mandatory preflight. For a fresh bounded
task, do not reopen it, enumerate the package, or inspect optional continuity
data. Reuse continuity only when the same objective demonstrably recurs and the
bounded reuse is cheaper than reconstructing context. Never let continuity or
another runtime's state expand authority.

Before the final answer:

1. Verify the terminal outcome with the smallest declared acceptance checks.
2. Confirm every change stayed inside the Objective Lock.
3. Confirm no package hook was installed or required.
4. Stop immediately and report exact evidence, limitations, and any remaining
   authorized work.

## Portable locations

Resolve the runtime home from `$CODEX_HOME`, otherwise `~/.codex`.

| Purpose | Location |
| --- | --- |
| Skill | `$RUNTIME_HOME/skills/adaptive-delegation/` |
| Policy | `$RUNTIME_HOME/skills/adaptive-delegation/config/model-routing.defaults.json` |
| Roles | `$RUNTIME_HOME/agents/adaptive-*.toml` |
| Optional dispatcher | `$RUNTIME_HOME/scripts/adaptive_dispatch_attestation.py` |
| Local audit state | `$RUNTIME_HOME/state/adaptive-delegation/` |

Never copy or publish authentication, raw ledgers, continuity data, rollout
records, or session state. Repository files are canonical; installed files are
deployment targets. The installer manages only the skill, dispatcher, and
package-declared roles. It installs no hooks and does not modify foreign hook
owners.
