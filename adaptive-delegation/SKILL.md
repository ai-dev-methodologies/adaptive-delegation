---
name: adaptive-delegation
description: Codex-only skill for Codex native subagents. Use when routing bounded implementation and verification work for Objective-Locked delegation, scope-drift prevention, bounded verification, token effective, token-effective, token efficiency, token-efficient delegation, cost-efficient subagents, Luna-first delegation, adaptive delegation, effort-first escalation, model routing audit, validate model selection, reduce Sol usage, or evidence-checked delegation requests; also match 토큰효율화 and 토큰 효율화.
---

# Adaptive Delegation

**Codex only:** this skill routes work to Codex native subagents. Claude Code
is unsupported, and this package does not provide a general external runtime
integration.

Use explicit `$adaptive-delegation` when deterministic activation matters.
Implicit activation remains allowed for requests that match this skill's
description.

The invocation is sufficient by itself. Do not require the user to append a
separate Luna-first, stop-on-acceptance, or no-extra-review prompt. This skill
already requires bounded implementation and verification to start Luna-first,
forbids Terra or Sol escalation without observable route failure except the
declared direct-latency case, stops immediately at acceptance, and excludes
optional reviews, broad tests, and adjacent improvements.

## Activation gate

Step zero, before routing or launching any child, checks that the current main
authority is exactly `gpt-5.6-sol` with `reasoning_effort` set to `high`,
`xhigh`, `max`, or `ultra`. If that check fails, print exactly this English
warning block:

```text
Adaptive Delegation blocked: main authority must be gpt-5.6-sol with reasoning_effort >= high. Current: <model>/<effort>. No child was launched. Switch the main session to gpt-5.6-sol/high or above, then invoke $adaptive-delegation again.
```

The skill cannot mutate the parent model. After printing the block, launch no
child and stop. Do not route around this gate.

When the gate passes, before tools print exactly:
`Routing: main=<decision>; ready=<n>; parallel=<n>; serial=<reason|none>.`

The main owns intent, planning, integration, acceptance, and final claims.
It also exclusively owns route classification and selection. The Sol/high-or-
above activation gate exists because this classification is a main-authority
decision: before every child launch, the main classifies each bounded slice
from its task shape, oracle strength, risk and ambiguity, latency sensitivity,
execution horizon, and recoverability, then selects the matching package
default and exact ladder. A child may not select, reinterpret, or change its
route.

Workflow names are not route inputs. A Codex goal or Ultragoal label is neither
required nor sufficient for the quota-first long-horizon route. That route is
eligible whenever the main determines that the bounded slice itself is
long-horizon, latency-insensitive, risk `low`/`medium`, and protected by a
strong acceptance oracle. If any predicate is false or unproven, the main
chooses the ordinary task-shape route or keeps the work main-authoritative.
After the initial selection, only observable failure may advance the exact
ladder.

Start implementation in a bounded leaf. When the evidence-classified ladder is
exhausted, the main is the final escalator and may take over the unresolved
slice without widening it. Model or reasoning escalation changes capability,
never authority or scope. Use Maker/Checker separation when risk warrants it:
a Maker makes the bounded change and a distinct-session Checker checks it. Every
child is a leaf and reports evidence, conflicts, and its stop condition.

Select Checker capability from oracle shape and risk, not from a rule that the
Checker must exceed the Maker model. A strong deterministic oracle may use a
cheaper Checker because checking is narrower than making. If the oracle rejects
the artifact, return to main and advance the exact Maker ladder. If the Checker
itself has a tool/environment failure, repair or retry that Checker without
upgrading Maker. If the oracle is weak, stop leaf escalation and use main
takeover. The optional dispatcher integration-receipt path currently requires
the distinct installed `adaptive-sol-checker-medium` session as its issuer; do
not add another Verifier stage after sufficient Checker evidence. Main owns
final integration acceptance and the stop decision.

## Primary invariant — Objective Lock

Delegate bounded independent work aggressively when it materially improves
speed, token efficiency, or verification quality, but only inside one
canonical **OBJECTIVE LOCK**. No valid Objective Lock, no child launch.

Before routing, construct a self-contained **OBJECTIVE LOCK** from the current
user request and repository evidence. It must declare the terminal outcome,
non-goals (`non_goals`), read/write/network authority, authorized lanes, a
progression policy, and global terminal conditions. The current method, data
source, stage, test plan, path-local verification, side effects, and path stop
condition belong to a replaceable path/iteration envelope. Every packet must
also declare `terminal_outcome`; no valid lock means no child launch. The skill
must not depend on a user-global `AGENTS.md` or machine-specific policy file to
supply these fields.

The dispatcher serializes one route-independent canonical v3 JSON object and
carries its SHA-256 consistency digest through Native admission, typed
execution, terminal/integration records, linked audit schema `0.3.0`, retry,
escalation, Checker review, and main takeover. A stronger model, higher effort,
retry, or takeover may finish the unresolved slice but may not change any lock
field. The digest is same-user drift evidence, not a signature or proof that
the declared acceptance oracle is semantically adequate.

The lock binds the main session too. Main-side planning, repository inspection,
routing preflight, package inspection, verification, retry decisions, and
integration must remain inside the same authority and verification ceiling.
Delegating a narrow leaf never authorizes the main to perform broader discovery
or extra review around it.

Use the smallest verification path that proves the acceptance evidence. Stop
as soon as that evidence passes and the stop condition applies. A blocked path
returns to the main for an in-scope alternative and ends the current lane
attempt chain; the main starts the next authorized lane with a new path
envelope under the same lock. A truthful blocked-lane report uses a successful
child process result with receipt outcome `path_blocked`; it is not terminal
acceptance. Final BLOCKED is valid only when all authorized lanes are terminal.
Continue iterative discovery or
flywheel work until the terminal outcome passes or the user stop condition
applies. The verification ceiling limits nonessential verification and never
truncates core outcome work. Never fabricate evidence or substitute an
unauthorized method. After sufficient evidence exists, do not perform
additional reviews, repository-wide analysis, repeated validation, optional
model consultations,
unrelated cleanup, refactoring, architectural redesign, abstraction,
documentation expansion, speculative robustness, or consistency polishing.
Record adjacent improvements as concise backlog findings instead of
implementing them.

Keep routing preflight proportional to the locked task. After loading this
`SKILL.md` once, do not reopen it, enumerate the package, inspect dispatcher
source, invoke `--help`, or read optional references merely to reconstruct
package internals. For an ordinary bounded Native route, inspect the live spawn
schema/catalog once, read only the selected entry in
`config/model-routing.defaults.json` and its installed role TOML, then use the
documented admission interface. For the config read, select only
`task_defaults` plus `.role_bindings[$role]` with the exact role name; never
fall back to printing the whole JSON object. Expand that preflight only after a
concrete admission failure makes a specific additional read necessary.

Expand scope only when direct evidence proves that the accepted path crosses a
required public contract, shared invariant, security/auth/financial boundary,
cross-process concurrency boundary, schema/protocol migration, or
compatibility/rollback surface. Record the trigger, evidence, added scope,
budget, side effects, and stop condition. Uncertainty alone never expands
scope. A materially broader objective requires a new explicitly authorized
task or packet; do not silently turn a takeover into a redesign.

## Policy source and routing defaults

The policy source of truth is the package config at
`adaptive-delegation/config/model-routing.defaults.json` in this repository.
The repository and package sources are canonical; an installed copy is a
deployment target and does not become a second policy source.

The default strategy is Luna-first, effort-first within Luna, then an
evidence-seeking Terra intermediate after an observable Luna acceptance or
quality failure, followed by bounded Sol leaf escalation before main takeover:

These are candidate defaults selected by the main after classification, not
global modes selected from a workflow name. The main repeats classification
for each bounded slice; one long-running goal may legitimately contain slices
that start on different routes.

| Work shape | Default route |
| --- | --- |
| Simple lookup or extraction | `gpt-5.6-luna/medium` |
| Clear implementation or transformation | `gpt-5.6-luna/high` |
| Bounded complex implementation or verification | `gpt-5.6-luna/xhigh` |
| Any bounded slice that is latency-insensitive, long-horizon, low/medium risk, and has a strong oracle | `gpt-5.6-luna/max` |
| Weak oracle, ambiguous/high-risk, or long contract | Main-authoritative `gpt-5.6-sol/ultra` |

Leaf `ultra` is forbidden. Sol `medium` and `high` are fixed leaf roles; they do
not inherit the main's authority or `ultra` effort. The main retains authority
and may take over at `gpt-5.6-sol/ultra`. There is one same-model reasoning
retry per stage, with reevaluation after every attempt. The fixed ladders are:

- Simple lookup or extraction: `luna/medium -> luna/high -> luna/xhigh -> luna/max -> terra/medium -> sol/medium -> main-takeover sol/ultra`.
- Clear implementation or transformation: `luna/high -> luna/xhigh -> luna/max -> terra/medium -> sol/medium -> sol/high -> main-takeover sol/ultra`.
- Bounded complex implementation, debugging, or review: `luna/xhigh -> luna/max -> terra/high -> sol/medium -> sol/high -> main-takeover sol/ultra`.
- Bounded complex work with a strong oracle uses the same bounded-complex ladder and may not skip a configured step.
- Any bounded slice that is long-horizon, latency-insensitive, risk
  `low`/`medium`, and has a strong acceptance oracle:
  `luna/max -> terra/xhigh -> terra/max -> sol/high -> main-takeover sol/ultra`.
- Weak-oracle, ambiguous/high-risk, or long-contract work stays main-authoritative at `sol/ultra`.

For a `weak_oracle` failure discovered on a leaf, `main_takeover` moves directly
to the final main-authority step. It is not an adjacent leaf escalation, and
`raise_model` cannot select main authority.

Every leaf step and Checker route resolves to a package-declared role with the
exact model and effort. `sol/ultra` is a main-authority route, never a child
role. The runtime validator rejects unknown routes, skipped steps, mismatched
counters, exhausted same-route retries, and model/effort substitutions.

The config records the official 2026-07-30 API token prices and normalized
Sol-equivalent factors: Luna `0.04`, Terra `0.4`, and Sol `1.0`. Effort changes
token consumption, so per-token price alone never selects a route; Codex quota
or credit units are not provider-token equivalents. Routing is
provisional and evidence-seeking; accepted-task quality, latency, weighted
tokens, and total cost determine later revisions.

Terra `medium` and `high` remain the evidence-seeking intermediate routes for
ordinary scoped or latency-sensitive work. Terra `xhigh` and `max` are active
only in the latency-insensitive long-horizon quota-first ladder after observable
Luna failure. They trade elapsed time for lower Sol usage and are provisional
until local accepted-task logs justify retention. Ordinary runs passively
record Terra `use_mode=post_luna_failure` or `use_mode=direct_latency`; no
perpetual, random, or duplicate paired A/B is allowed. The main may directly
choose Terra only when it records a pre-observable, latency-sensitive, scoped,
strong-oracle, recoverable, non-ambiguous predicate. Terra does not support an
`ultra` route, and leaf `ultra` remains forbidden.

## Observable failure and review evidence

Hidden reasoning is not visible. Classify failure only from observable
evidence:

- test or acceptance failure;
- contradiction with the packet or repository evidence;
- missed constraint or scope violation;
- truncation or context-limit evidence;
- runtime or tool error; or
- weak oracle or an ambiguity that prevents a trustworthy decision.

Do not invent a failure class from an unseen reasoning chain. Log an ambiguous
observation before freezing a weak rule. Prefer an auditable observation to a
confident rule unsupported by evidence.

The resolved runtime home is `$CODEX_HOME` when it is set, otherwise
`$HOME/.codex`; in a shell, set and export it before using it:
`RUNTIME_HOME="${CODEX_HOME:-$HOME/.codex}"; export RUNTIME_HOME`. Never read or
fall back outside it. Central
append-only attempt records live at `$RUNTIME_HOME/state/model-routing/attempts.jsonl`;
review records live at `$RUNTIME_HOME/state/model-routing/reviews/`. Every attempt record has a
`pre_decision` or `post_result` type. Linked v0.3 records capture the declared
main authority, policy and surface fingerprints, pre-selection rationale,
observed result, exact effort/model escalation counts, execution completion,
oracle verdict, and integration acceptance. A successful child process is not
integration acceptance. Review failures, escalations, direct-Sol use, and
model-price changes at the configured cadence. The dispatcher records package
attempts automatically and the audit CLI auto-creates triggered reviews.

When asked to validate model selection, read the audit logs automatically:
consult the model-routing attempts and reviews before reporting a conclusion.

When asked to turn local usage experience into a GitHub issue, read
[references/CODEX-ISSUE-REPORT-PROMPT.md](references/CODEX-ISSUE-REPORT-PROMPT.md),
then use the `issue-report` and `record-submission` commands from
`scripts/model_routing_audit.py`. The formatter prints only allowlisted
Markdown and never publishes or uploads the attempts ledger. A separate
owner-only issue-state ledger keeps pending random Report IDs and submitted
attempt fingerprints so later requests do not resend recorded history.

## Bounded continuity reuse

Continuity is an optimization, not a mandatory preflight. Consult
[TOKEN_EFFICIENCY_CONTINUITY.md](TOKEN_EFFICIENCY_CONTINUITY.md) only when the
task repeats a stable workspace/objective pair, the Objective Lock permits the
state read, and a prior accepted route or evidence path is likely to replace
material work. Skip continuity for a fresh one-shot task with complete
acceptance evidence, or whenever the lookup would exceed the read scope or
verification ceiling.

When consultation is justified, export `RUNTIME_HOME` and run `python3
"$RUNTIME_HOME/skills/adaptive-delegation/scripts/read_continuity.py"
--workspace "$WORKSPACE" --objective-key "$OBJECTIVE_KEY"` with exact values;
it returns at most the latest three accepted matching records. Never `tail`,
`grep`, or `cat` a continuity ledger. Reuse valid decisions and evidence paths
unless newer direct evidence invalidates them, and do not reload unrelated raw
logs. At acceptance or handoff, append one compact record only when the lock
permits that state write and reuse is expected; the distinct-session Checker
records when present, otherwise the sole verified executor. `token_budget` is
optional/advisory; its absence preserves Native V2 eligibility and never
triggers external rerouting.

## Codex native routing and local admission evidence

After delegation is chosen, prefer Native V2 through a verified fixed
`agent_type`. Select the installed package role whose TOML fixes the exact Luna,
Terra, or Sol leaf model and effort, pass the matching `reasoning_effort` and
`fork_turns="none"`, and verify the role binding before creation. In this mode
the chosen `agent_type` is the explicit model selection; omitting the optional
`model` override is not leader-model inheritance.

Inspect the live `collaboration.spawn_agent` schema and agent-type catalog
before every route; do not reuse an old capability claim. The absence of a
selected model from the optional `model` override enum does not reject a Native
route when its allowlisted fixed `agent_type` exists. A surface that uses
explicit model overrides instead must support `agent_type`, `model`,
`reasoning_effort`, and
`fork_turns="none"`. Both modes require the installed role TOML/launch binding,
exact resolved role/model/effort allowlist, `desired=explicit=native_v2`, and
locally validated runtime metadata. Before creation, require the bounded local
sequence `pending_receipt -> native_spawn_gate -> child_creation_eligibility`;
this is consistency evidence, not a clock-backed security proof.

Use the exact typed direct path (`--direct-typed`) only when the fixed role or
Native surface is unavailable, the Native call is rejected, validated runtime
model/effort mismatches the binding, or a hard parent-enforced cap is required.
Model substitution is forbidden for a rejected admission. In particular,
Terra may not replace Luna or Sol merely because the chosen fixed role is
unavailable. A pre-creation rejection means no child and child token 0. Network
defaults to off unless the packet explicitly permits it.

A corrected or fallback launch envelope must canonically match the dispatched
packet in full, including objective, scope, network, resource, budget, and
routing fields. A matching dispatch identifier and route alone are insufficient.

Use validated child session metadata/turn_context for the session, model, and
effort. Hidden fields, hook `updatedInput`, and prompt text are not evidence.
Model omission is valid only for a verified fixed-role selection; otherwise
model omission and inheritance are not evidence. A mismatch cancels only that
child and returns control to root.

## Packets, truthful caps, and integration

Every packet states the objective, required `non_goals`, owned mutable surfaces,
acceptance evidence, verification ceiling, resource cap, token budget, stop
condition, collision ownership, and side effects. Packets are narrow planning
inputs, not proof of enforcement. For
Native V2, caps are unavailable/planning/advisory unless trusted live parent
monitoring exists; mark enforcement unavailable and never claim `parent_enforced` or
`quantitative_caps_enforced` without that proof. The typed direct path may make
those claims only when trusted parent monitoring proves them.

The typed direct path enforces `token_budget` against cost-weighted usage:
`ceil(input_tokens / 4) + output_tokens`. Codex `input_tokens` already includes
cached input. Therefore the CLI's raw `tokens used` display can exceed this
weighted budget without a cap violation. This is a routing proxy, not a provider
billing amount.

Every package-owned dispatcher packet also declares `main_authority` and a
bounded `routing_audit`. The latter includes task/attempt identifiers, the
stable decision timestamp, exact cumulative effort and model escalation
counts, task/oracle/risk/selection enums, workspace and main-session identity,
and the dispatch surface plus its SHA-256 schema fingerprint. Missing,
malformed, or sensitive fields fail closed before child creation.

When a hard token or resource cap is required, use the canonical typed direct
Codex worker path with exact role binding, isolated runtime, network
defaults, ledger semantics, `rollout_budget`, and trusted parent monitoring. A
real cap stop preserves evidence, stops only that child, and returns to root
for a narrower packet. Do not describe Native V2 caps as blanket hard-enforced.

Completion is not integration. Child execution first records a dispatcher-
captured terminal event. A separate `--finalize-integration` phase is the only
path that reads an integration receipt. The receipt must match the exact packet
digest, canonical Objective Lock version/digest, route/model/effort, child and
rollout, terminal nonce/result/digest, captured output digest, declared
worktree digest, verification checks, evidence artifact, and the
package-declared `adaptive-sol-checker-medium` session. The Checker session
must differ from both the child and the declared main session. Pre-created,
stale, mutable, or mismatched evidence fails closed.

The model-routing ledger appends `pre_decision` before execution. A failed
execution closes that attempt immediately. A successful child remains pending
with no `post_result` until integration finalization succeeds, at which point
the accepted terminal result is appended. Within the same installed terminal,
receipt, and audit schema, a failed receipt or pre-gate check stays pending for
corrected finalization without rewriting history.

Schema upgrades are an explicit cutover. Finalize v1 terminal/receipt and
linked `0.2.0` pending attempts before updating. After updating, those pending
chains remain readable evidence but are deliberately non-finalizable; never
backfill or rewrite them. Re-execute the bounded work as a genuinely fresh
chain with a new task ID, attempt index 1, dispatch ID, packet, v2 execution,
v2 terminal/receipt, and linked `0.3.0` records.

This is same-user local integrity checking, not a signature, remote
attestation, or a separate security principal. A malicious process running as
the same operating-system user can forge local files and session records. The
main remains the final trusted authority and must not describe a local receipt
as cryptographic proof.

## Portable locations and GitHub deployment

| Purpose | Location |
| --- | --- |
| Adaptive-delegation package | `$RUNTIME_HOME/skills/adaptive-delegation/` |
| Policy source of truth | `$RUNTIME_HOME/skills/adaptive-delegation/config/model-routing.defaults.json` |
| Package dispatcher | `$RUNTIME_HOME/scripts/adaptive_dispatch_attestation.py` |
| Issue-publication prompt | `$RUNTIME_HOME/skills/adaptive-delegation/references/CODEX-ISSUE-REPORT-PROMPT.md` |
| Model-routing attempts | `$RUNTIME_HOME/state/model-routing/attempts.jsonl` |
| Model-routing reviews | `$RUNTIME_HOME/state/model-routing/reviews/` |
| Issue-report duplicate state | `$RUNTIME_HOME/state/model-routing/issue-report-state.jsonl` |
| Continuity ledger | `$RUNTIME_HOME/state/adaptive-delegation/continuity.jsonl` |

The standalone repository is the portable source for Codex deployment.
Deployment fetches the repository and runs `python3 scripts/install.py`; see
[CROSS_PC_TRANSFER.md](CROSS_PC_TRANSFER.md). The installer copies the
package, installs its package dispatcher, and regenerates only
package-declared role bindings.
Codex normally detects the skill change automatically; restart only when the
update does not appear.

Never copy authentication, logs, issue-report state, continuity data, or
rollout/session data. Those files stay on the machine where they were created.
