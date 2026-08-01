---
name: adaptive-delegation
description: Use when routing bounded implementation and verification work for token effective, token-effective, token efficiency, token-efficient delegation, cost-efficient subagents, Luna-first delegation, adaptive delegation, effort-first escalation, model routing audit, validate model selection, reduce Sol usage, or evidence-attested delegation requests; also match 토큰효율화 and 토큰 효율화.
---

# Adaptive Delegation

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
slice. Use Maker/Checker separation when risk warrants it: a Maker makes the
bounded change and an independent Checker checks it. Every child is a leaf and
reports evidence, conflicts, and its stop condition.

## Policy source and routing defaults

The policy source of truth is the package config at
`~/.codex/skills/adaptive-delegation/config/model-routing.defaults.json`.
`~/.codex/state/model-routing/policy.local.json` is an optional local override.
`~/.codex/.omx-config.json` is a legacy, read-compatible fallback only; it is
not authoritative and must not be written by this policy.

The default strategy is Luna-first and effort-first:

| Work shape | Default route |
| --- | --- |
| Simple lookup or extraction | `gpt-5.6-luna/medium` |
| Clear implementation or transformation | `gpt-5.6-luna/high` |
| Bounded complex implementation or verification | `gpt-5.6-luna/xhigh` |
| Former Terra bounded | `gpt-5.6-luna/xhigh` |
| Former Sol bounded with a strong oracle | `gpt-5.6-luna/max` |
| Weak oracle, ambiguous/high-risk, or long contract | Main-authoritative `gpt-5.6-sol/ultra` |

Leaf `ultra` is forbidden. The main retains authority and may take over at
`gpt-5.6-sol/ultra`. There is one same-model reasoning retry per stage, with
reevaluation after every attempt. The effort-first ladders are:

- Former Terra bounded: `luna/xhigh -> luna/max -> terra/xhigh -> terra/max -> main-takeover sol/ultra`.
- Former Sol bounded with a strong oracle: `luna/max -> terra/max -> sol/high -> main-takeover sol/ultra`.
- Weak oracle, ambiguous/high-risk, or long contract: `main-authoritative sol/ultra`; optionally `luna/xhigh` as scout-only.

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

Central append-only attempt records live at
`~/.codex/state/model-routing/attempts.jsonl`; review records live at
`~/.codex/state/model-routing/reviews/`. Every attempt record has a
`pre_decision` or `post_result` type. Linked v0.2 records capture the declared
main authority, policy and surface fingerprints, pre-selection rationale,
observed result, exact effort/model escalation counts, execution completion,
oracle verdict, and integration acceptance. A successful child process is not
integration acceptance. Review failures, escalations, direct-Sol use, and
model-price changes at the configured cadence. The dispatcher records package
attempts automatically and the audit CLI auto-creates triggered reviews.

When asked to validate model selection, read the audit logs automatically:
consult the model-routing attempts and reviews before reporting a conclusion.

## Always-on continuity

Before routing, consult
[TOKEN_EFFICIENCY_CONTINUITY.md](TOKEN_EFFICIENCY_CONTINUITY.md):
read only the latest three relevant accepted continuity records, reuse valid
decisions and evidence paths unless newer direct evidence invalidates them,
and do not reload unrelated raw logs. At acceptance or handoff, exactly one
designated recorder appends the compact record: the independent Checker when
present, otherwise the sole verified executor. `token_budget` is
optional/advisory; its absence preserves Native V2 eligibility and never
triggers external rerouting.

## Native V2 routing and exact attestation

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
trusted runtime evidence. Before creation, prove the same-call monotonic order
`pending_receipt -> native_spawn_gate -> child_creation_eligibility`.

Use the exact typed direct path (`--direct-typed`) only when the fixed role or
Native surface is unavailable, the Native call is rejected, trusted runtime
model/effort mismatches the binding, or a hard parent-enforced cap is required.
Terra substitution is forbidden for a rejected Luna admission. A pre-creation
rejection means no child and child token 0. Network defaults to off unless the
packet explicitly permits it.

Use trusted child session metadata/turn_context for the session, model, and
effort. Hidden fields, hook `updatedInput`, and prompt text are not evidence.
Model omission is valid only for a verified fixed-role selection; otherwise
model omission and inheritance are not evidence. A mismatch cancels only that
child and returns control to root.

## Packets, truthful caps, and integration

Every packet states the objective, owned mutable surfaces, acceptance evidence,
resource cap, token budget, stop condition, collision ownership, and side
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

When a hard token or resource cap is required, use the canonical typed
external worker path with exact role binding, isolated runtime, network
defaults, ledger semantics, `rollout_budget`, and trusted parent monitoring. A
real cap stop preserves evidence, stops only that child, and returns to root
for a narrower packet. Do not describe Native V2 caps as blanket hard-enforced.

Completion is not integration. Integrate only with an allowlisted receipt
whose exact `desired=explicit=effective` role/model/effort, trusted rollout
session id, launch-bound role config, successful finish, independent Checker
pass, sha256 evidence digest, and truthful token observation all match. Any
missing or mismatched proof blocks integration. Receipt authority is the
owner-only local rollout binding, not cryptographic or remote attestation.

## Objective-bound verification

Every task begins with an **IMPLEMENTATION ENVELOPE**: objective, owned
mutable surfaces, intended behavior, acceptance evidence, verification
ceiling, and known side effects. Verify the smallest path proving acceptance.
Expand only on direct evidence of a shared public contract or interface,
shared state or invariant, security/auth/financial boundary,
cross-process concurrency or lease semantics, schema/protocol migration or
compatibility/rollback surface, or an accepted path crossing a boundary.

Record every **SCOPE EXPANSION** with trigger, evidence, added scope, budget,
side effects, and stop condition. Uncertainty alone does not expand scope;
unrelated defects are backlog findings unless they invalidate the acceptance
claim.

## Portable locations and GitHub deployment

| Purpose | Location |
| --- | --- |
| Adaptive-delegation package | `~/.codex/skills/adaptive-delegation/` |
| Policy source of truth | `~/.codex/skills/adaptive-delegation/config/model-routing.defaults.json` |
| Optional local override | `~/.codex/state/model-routing/policy.local.json` |
| External dispatcher compatibility wrapper | `~/.codex/scripts/adaptive_dispatch_attestation.py` |
| Model-routing attempts | `~/.codex/state/model-routing/attempts.jsonl` |
| Model-routing reviews | `~/.codex/state/model-routing/reviews/` |
| Continuity ledger | `~/.codex/state/adaptive-delegation/continuity.jsonl` |

The standalone repository is the portable source for GitHub deployment.
Deployment fetches the repository and runs `python3 scripts/install.py`; see
[CROSS_PC_TRANSFER.md](CROSS_PC_TRANSFER.md). The
installer copies the package, installs its dispatcher source as the external
compatibility wrapper, and regenerates only package-declared role bindings.
Codex normally detects the skill change automatically; restart only when the
update does not appear.

Never copy authentication, logs, continuity data, rollout/session data, or the
optional local override. Preserve legacy readers; the legacy file remains a
read-compatible fallback only.
