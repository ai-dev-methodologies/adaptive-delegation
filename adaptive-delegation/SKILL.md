---
name: adaptive-delegation
description: Codex-only skill for Codex native subagents. Use when routing bounded implementation and verification work for token effective, token-effective, token efficiency, token-efficient delegation, cost-efficient subagents, Luna-first delegation, adaptive delegation, effort-first escalation, model routing audit, validate model selection, reduce Sol usage, or evidence-checked delegation requests; also match 토큰효율화 and 토큰 효율화.
---

# Adaptive Delegation

**Codex only:** this skill routes work to Codex native subagents. Claude Code
is unsupported, and this package does not provide a general external runtime
integration.

Use explicit `$adaptive-delegation` when deterministic activation matters.
Implicit activation remains allowed for requests that match this skill's
description.

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
Start implementation in a bounded leaf. When the evidence-classified ladder is
exhausted, the main is the final escalator and may take over the unresolved
slice without widening it. Model or reasoning escalation changes capability,
never authority or scope. Use Maker/Checker separation when risk warrants it:
a Maker makes the bounded change and a distinct-session Checker checks it. Every
child is a leaf and reports evidence, conflicts, and its stop condition.

## Policy source and routing defaults

The policy source of truth is the package config at
`adaptive-delegation/config/model-routing.defaults.json` in this repository.
The repository and package sources are canonical; an installed copy is a
deployment target and does not become a second policy source.

The default strategy is Luna-first and effort-first:

| Work shape | Default route |
| --- | --- |
| Simple lookup or extraction | `gpt-5.6-luna/medium` |
| Clear implementation or transformation | `gpt-5.6-luna/high` |
| Bounded complex implementation or verification | `gpt-5.6-luna/xhigh` |
| Weak oracle, ambiguous/high-risk, or long contract | Main-authoritative `gpt-5.6-sol/ultra` |

Leaf `ultra` is forbidden. The main retains authority and may take over at
`gpt-5.6-sol/ultra`. There is one same-model reasoning retry per stage, with
reevaluation after every attempt. The effort-first ladders are:

- Simple lookup or extraction: `luna/medium -> luna/high -> luna/xhigh -> luna/max -> main-takeover sol/ultra`.
- Clear implementation or transformation: `luna/high -> luna/xhigh -> luna/max -> terra/xhigh -> terra/max -> main-takeover sol/ultra`.
- Bounded complex implementation or verification: `luna/xhigh -> luna/max -> terra/xhigh -> terra/max -> main-takeover sol/ultra`.
- Bounded complex work with a strong oracle may omit `terra/xhigh` but may not skip any other configured step.
- Weak-oracle, ambiguous/high-risk, or long-contract work stays main-authoritative at `sol/ultra`.

For a `weak_oracle` failure discovered on a leaf, `main_takeover` moves directly
to the final main-authority step. It is not an adjacent leaf escalation, and
`raise_model` cannot select main authority.

Every leaf step and Checker route resolves to a package-declared role with the
exact model and effort. `sol/ultra` is a main-authority route, never a child
role. The runtime validator rejects unknown routes, skipped steps, mismatched
counters, exhausted same-route retries, and model/effort substitutions.

The config records Luna as a user-provided 80% reduction versus its prior
price and Terra as a user-provided 20% reduction versus its prior price. These
are relative, user-provided changes, not absolute prices or official API-price
claims; routing is provisional and evidence-seeking.

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
`~/.codex`; in a shell, set `RUNTIME_HOME="${CODEX_HOME:-$HOME/.codex}"` once
from that rule and never read or fall back outside it. Central
append-only attempt records live at `$RUNTIME_HOME/state/model-routing/attempts.jsonl`;
review records live at `$RUNTIME_HOME/state/model-routing/reviews/`. Every attempt record has a
`pre_decision` or `post_result` type. Linked v0.2 records capture the declared
main authority, policy and surface fingerprints, pre-selection rationale,
observed result, exact effort/model escalation counts, execution completion,
oracle verdict, and integration acceptance. A successful child process is not
integration acceptance. Review failures, escalations, direct-Sol use, and
model-price changes at the configured cadence. The dispatcher records package
attempts automatically and the audit CLI auto-creates triggered reviews.

When asked to validate model selection, read the audit logs automatically:
consult the model-routing attempts and reviews before reporting a conclusion.

To prepare a privacy-safe GitHub issue, run the local `issue-report` command
from `scripts/model_routing_audit.py` and follow the repository-level
`REPORTING.md`. The command prints only an allowlisted Markdown summary and
never publishes or uploads the ledger.

## Always-on continuity

Before routing, consult
[TOKEN_EFFICIENCY_CONTINUITY.md](TOKEN_EFFICIENCY_CONTINUITY.md):
run `python3 "$RUNTIME_HOME/skills/adaptive-delegation/scripts/read_continuity.py"
--workspace "$WORKSPACE" --objective-key "$OBJECTIVE_KEY"` with exact values;
it returns at most the
latest three accepted matching records. Never `tail`, `grep`, or `cat` a
continuity ledger. Reuse valid decisions and evidence paths unless newer direct evidence invalidates them,
and do not reload unrelated raw logs. At acceptance or handoff, exactly one
designated recorder appends the compact record: the distinct-session Checker when
present, otherwise the sole verified executor. `token_budget` is
optional/advisory; its absence preserves Native V2 eligibility and never
triggers external rerouting.

## Codex native routing and local admission evidence

After delegation is chosen, prefer Native V2 through a verified fixed
`agent_type`. Select the installed Luna role whose TOML fixes the exact model
and effort, pass the matching `reasoning_effort` and `fork_turns="none"`, and
verify the role binding before creation. In this mode the chosen `agent_type`
is the explicit model selection; omitting the optional `model` override is not
leader-model inheritance.

Inspect the live `collaboration.spawn_agent` schema and agent-type catalog
before every route; do not reuse an old capability claim. The absence of Luna
from the optional `model` override enum does not reject Native Luna when an
allowlisted fixed Luna `agent_type` exists. A surface that uses explicit model
overrides instead must support `agent_type`, `model`, `reasoning_effort`, and
`fork_turns="none"`. Both modes require the installed role TOML/launch binding,
exact resolved role/model/effort allowlist, `desired=explicit=native_v2`, and
locally validated runtime metadata. Before creation, require the bounded local
sequence `pending_receipt -> native_spawn_gate -> child_creation_eligibility`;
this is consistency evidence, not a clock-backed security proof.

Use the exact typed direct path (`--direct-typed`) only when the fixed role or
Native surface is unavailable, the Native call is rejected, validated runtime
model/effort mismatches the binding, or a hard parent-enforced cap is required.
Terra substitution is forbidden for a rejected Luna admission. A pre-creation
rejection means no child and child token 0. Network defaults to off unless the
packet explicitly permits it.

A corrected or fallback launch envelope must canonically match the dispatched
packet in full, including objective, scope, network, resource, budget, and
routing fields. A matching dispatch identifier and route alone are insufficient.

Use validated child session metadata/turn_context for the session, model, and
effort. Hidden fields, hook `updatedInput`, and prompt text are not evidence.
Model omission is valid only for a verified fixed-role selection; otherwise
model omission and inheritance are not evidence. A mismatch cancels only that
child and returns control to root.

## Packets, truthful caps, and integration

Every packet states the objective, owned mutable surfaces, acceptance evidence,
verification ceiling, resource cap, token budget, stop condition, collision ownership, and side
effects. Packets are narrow planning inputs, not proof of enforcement. For
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
package-declared `adaptive-terra-checker-high` session. The Checker session
must differ from both the child and the declared main session. Pre-created,
stale, mutable, or mismatched evidence fails closed.

The model-routing ledger appends `pre_decision` before execution. A failed
execution closes that attempt immediately. A successful child remains pending
with no `post_result` until integration finalization succeeds, at which point
the accepted terminal result is appended. A failed receipt stays pending so a
corrected, distinct-session-checked receipt can be submitted without rewriting
history. A failure before the receipt gate also remains pending for corrected
finalization.

This is same-user local integrity checking, not a signature, remote
attestation, or a separate security principal. A malicious process running as
the same operating-system user can forge local files and session records. The
main remains the final trusted authority and must not describe a local receipt
as cryptographic proof.

## Objective-bound verification

Every task begins with an **IMPLEMENTATION ENVELOPE**: objective,
read/write/network authority, intended behavior, acceptance evidence,
verification ceiling, known side effects, and stop condition. Verify the
smallest path proving acceptance. These fields form the **OBJECTIVE LOCK**.
The dispatcher serializes one route-independent canonical v1 JSON object for
both Native and typed execution and carries its SHA-256 consistency digest
through Native admission, terminal/integration records, linked audit schema
`0.3.0`, retry, escalation, and main takeover. Linked `0.2.0` records remain
readable but cannot be continued into or from a `0.3.0` task history.

The lock applies equally to Luna and Terra leaves, Checker routes, and a Sol
main-authority takeover. A stronger model, higher reasoning effort, retry, or
takeover can finish the unresolved slice but cannot broaden its authority.
The digest is same-user drift evidence, not a signature or proof that the
declared acceptance oracle is semantically adequate.

Stop as soon as the required acceptance evidence passes and the stop condition
applies. Do not continue into unrelated cleanup, refactoring, architectural
generalization, abstraction, documentation expansion, speculative robustness,
consistency polishing, or a more "complete" design unless the original
acceptance contract requires it. Completeness, elegance, uncertainty, or spare
budget is not scope-expansion evidence. Record adjacent improvements as concise
backlog findings instead of implementing them.

Expand only on direct evidence of a shared public contract or interface,
shared state or invariant, security/auth/financial boundary,
cross-process concurrency or lease semantics, schema/protocol migration or
compatibility/rollback surface, or an accepted path crossing a boundary.

Record every **SCOPE EXPANSION** with trigger, evidence, added scope, budget,
side effects, and stop condition. Uncertainty alone does not expand scope;
unrelated defects are backlog findings unless they invalidate the acceptance
claim. A materially broader objective requires a new, explicitly authorized
task or packet; do not silently turn a takeover into a redesign.

## Portable locations and GitHub deployment

| Purpose | Location |
| --- | --- |
| Adaptive-delegation package | `$RUNTIME_HOME/skills/adaptive-delegation/` |
| Policy source of truth | `$RUNTIME_HOME/skills/adaptive-delegation/config/model-routing.defaults.json` |
| Package dispatcher | `$RUNTIME_HOME/scripts/adaptive_dispatch_attestation.py` |
| Model-routing attempts | `$RUNTIME_HOME/state/model-routing/attempts.jsonl` |
| Model-routing reviews | `$RUNTIME_HOME/state/model-routing/reviews/` |
| Continuity ledger | `$RUNTIME_HOME/state/adaptive-delegation/continuity.jsonl` |

The standalone repository is the portable source for Codex deployment.
Deployment fetches the repository and runs `python3 scripts/install.py`; see
[CROSS_PC_TRANSFER.md](CROSS_PC_TRANSFER.md). The installer copies the
package, installs its package dispatcher, and regenerates only
package-declared role bindings.
Codex normally detects the skill change automatically; restart only when the
update does not appear.

Never copy authentication, logs, continuity data, or rollout/session data.
Those files stay on the machine where they were created.
