# Model Routing Policy

This is the policy reference for the Codex-only `adaptive-delegation` skill
and its Codex native subagents. Claude Code is unsupported.

This document explains the package-default policy in
`config/model-routing.defaults.json`. That JSON is the policy source of truth;
this document explains its evidence basis and operating rules without
overriding it. Repository files are canonical; installed files are deployment
targets and are not additional policy sources.

## Primary invariant: portable Objective Lock

Before the first child launch, derive one self-contained Objective Lock from
the current user request and repository evidence. Its v2 fields are objective,
`non_goals`, read/write/network authority, intended behavior, acceptance
evidence, verification ceiling, known side effects, and stop condition. No
valid lock means no child launch. A user-global or project `AGENTS.md` may
further restrict the task but is not required by the installed skill.

Delegate bounded independent work aggressively when it materially improves
speed, token efficiency, or verification quality. Every Maker, Checker, retry,
effort/model escalation, and main takeover inherits the exact lock. Run the
smallest acceptance proof and stop when it passes. Additional reviews,
repository-wide analysis, repeated validation, optional model consultations,
and adjacent improvements remain outside the lock unless a new explicitly
authorized task adds them.

The main session is not exempt: planning, repository inspection, routing
preflight, package inspection, verification, retries, and integration remain
inside the same authority and verification ceiling. For a fresh bounded task,
load the skill once, skip continuity, inspect only the live spawn surface plus
the selected config binding and role TOML, and do not reverse-engineer package
source unless a concrete admission failure requires a specific diagnostic.

## Evidence basis

Routing decisions must be supported by observable evidence: acceptance tests,
test contradictions, missed constraints, truncation or context-ceiling
signals, runtime or tool errors, and the strength of the acceptance oracle.
Hidden reasoning is not evidence and must not be used to invent a failure
class. When a case is ambiguous, record the observation before turning it into
a rule. A pre-decision record captures the planned route and evidence; a
post-result record captures the observed result, classification, and next
action. The resolved runtime home is `$CODEX_HOME` when it is set, otherwise
`~/.codex`; records are append-only in
`$RUNTIME_HOME/state/model-routing/attempts.jsonl`. The audit paths in the
policy JSON are relative to that resolved runtime home; they are not shell
templates.

The qualitative starting point is the package's installed Codex role catalog:
Luna handles clear bounded work, Sol `medium` and `high` are bounded leaf
escalations, and Sol `ultra` remains the authoritative main takeover. Effort is
raised before model tier when observable evidence supports that transition.
These are package policy choices, not universal quality equivalence claims.
The exact thresholds and ladders remain provisional hypotheses evaluated
through local audit outcomes and acceptance oracles.

As of 2026-08-02, [OpenAI's model guidance](https://developers.openai.com/api/docs/guides/latest-model)
positions Sol for frontier capability, Terra for a balance of intelligence and
cost, and Luna for efficient high-volume work. It recommends representative
evaluation rather than a universal escalation ladder. A current
[independent coding comparison](https://artificialanalysis.ai/agents/coding-agents/comparisons/codex-vs-cursor-cli)
places Luna `max` ahead of Terra `xhigh` on its measured quality/cost frontier
and makes Sol `medium` the next material capability step. That result is useful
evidence, not a guarantee for every workload. The package therefore removes
Terra from automatic escalation and will revisit the decision from sanitized
real-use logs and representative acceptance results.

The policy is provisional and evidence-seeking. Reevaluate after every
attempt. Use one same-model reasoning-effort retry per stage at most, then
reassess the evidence and route. An accepted result is not proof that the
route was optimal; accepted-attempt reviews and the configured metrics are
used to update the evidence base.

## Defaults and ladders

The default strategy is Luna-first, effort-first within Luna, then bounded Sol
leaf escalation:

| Work shape | Default route |
| --- | --- |
| Simple lookup or extraction | `gpt-5.6-luna/medium` |
| Clear implementation or transformation | `gpt-5.6-luna/high` |
| Bounded complex implementation or verification | `gpt-5.6-luna/xhigh` |
| Weak oracle, ambiguous/high-risk, or long contract | main-authoritative `gpt-5.6-sol/ultra` |

Effort is increased before changing model tier when the failure evidence is
reasoning insufficiency and the task remains within the current model's
capability and context envelope. The configured same-model retry limit is one
per stage. Reasoning, context/budget, and capability ceilings advance exactly
one configured ladder step: `raise_effort` when the next step retains the
model, `raise_model` when it changes model tier, and `main_takeover` when the
next step returns to the main authority. Scope or retrieval overbreadth narrows
the envelope and retries the same route; a tool or environment failure repairs
the environment and retries the same route.

`weak_oracle` is the deliberate exception to adjacent-step escalation: its
`main_takeover` action moves directly from any current leaf step to the final
main-authority step. `raise_model` can never select that main-authority step.

The configured ladders are:

- Simple lookup or extraction: `luna/medium -> luna/high -> luna/xhigh -> luna/max -> sol/medium -> main-takeover sol/ultra`.
- Clear implementation or transformation: `luna/high -> luna/xhigh -> luna/max -> sol/medium -> sol/high -> main-takeover sol/ultra`.
- Bounded complex implementation or verification: `luna/xhigh -> luna/max -> sol/medium -> sol/high -> main-takeover sol/ultra`.
- Bounded complex work with a strong oracle: `luna/xhigh -> luna/max -> sol/medium -> sol/high -> main-takeover sol/ultra`.
- Weak-oracle, ambiguous/high-risk, or long-contract work: main-authoritative `sol/ultra` only.

The main may take over when the weak-oracle condition means a leaf cannot
truthfully establish acceptance, or when the ladder reaches its takeover
step. Main takeover is authoritative `gpt-5.6-sol/ultra`; a leaf may never use
`ultra`. Fixed Sol `medium` and `high` leaf roles change capability only and do
not inherit main authority.

The runtime validates the exact role/model/effort for every route. It rejects
unknown first routes, skipped ladder steps, repeated exhausted routes,
counter/history mismatches, and silent substitutions. Checker routes are also
package-declared exact Codex roles; they do not participate in the Maker
escalation ladder.

The package records [OpenAI's published GPT-5.6 API token prices](https://openai.com/index/gpt-5-6/)
as of 2026-08-02: Sol `$5/$30`, Terra `$2.50/$15`, and Luna `$1/$6` per
million input/output tokens. Because both input and output ratios are stable,
the routing cost proxy normalizes them to Sol-equivalent factors of `1.0`,
`0.5`, and `0.2`. Model-relative price factors are never aggregated across
models as if they were provider invoices. Effort can change token use and
latency, so compare total cost per accepted task, not price per token alone.

Terra `max` remains a dormant compatibility binding for a possible future
versioned A/B experiment. It appears in no automatic ladder and cannot be
selected by the current default, failure-action, or human-override contract.
Historical Terra audit records remain readable. Any future activation must
define a representative oracle and compare accepted-task quality, latency,
weighted tokens, and Sol-equivalent cost before changing the fixed ladders.

## Native role selection

Prefer Native routing by choosing the installed fixed `agent_type` for the
selected Luna or Sol leaf route, verifying its TOML model/effort binding,
passing the same effort and `fork_turns="none"`, and validating local runtime
model/effort metadata. The role selection is an explicit model choice. The
selected model need not appear in the optional `model` override enum, so its
absence there is not evidence that the fixed Native route is unsupported.

Use an explicit `model` override only on a surface that supports it and accepts
the exact requested value. Use typed direct only when the fixed role or Native
surface is unavailable/rejected, validated runtime metadata mismatches, or the
task requires a hard parent-enforced cap. Never substitute another model merely
because the optional override enum omits the selected fixed role's model.

Corrected and fallback launch envelopes must match the dispatched packet's
canonical digest, not only its dispatch identifier and routing triple. This
keeps objective, write scope, network access, resource caps, and budget bound to
the audited launch.

## Observable failure taxonomy and actions

Classify only what can be observed at the task boundary:

| Failure class | Observable signal | Action |
| --- | --- | --- |
| `reasoning_insufficiency` | The route remains in scope, but a check or contradiction shows the current effort was insufficient. | Advance one configured ladder step, preserving the model while an effort step remains. |
| `context_ceiling` | Weighted token-budget exhaustion, truncation, context exhaustion, or a directly observed context limit. | Advance one configured ladder step without skipping effort/model stages. |
| `scope_or_retrieval_overbreadth` | The task envelope or retrieved material is too broad for the bounded acceptance claim. | Narrow the envelope or retrieval, then retry the same route. |
| `tool_or_environment` | A runtime, tool, dependency, or environment error prevents a meaningful attempt. | Repair the environment, then retry the same route. |
| `capability_ceiling` | Direct evidence shows the current route cannot satisfy the required capability. | Advance one configured ladder step; use main takeover only at the declared final step. |
| `weak_oracle` | Acceptance cannot be independently established because the oracle is ambiguous, unavailable, or too weak for the risk. | Main-authoritative takeover at `gpt-5.6-sol/ultra`; leaf work can be scout-only if useful. |

Do not relabel a missed requirement as reasoning insufficiency when the
evidence shows an overbroad scope, context ceiling, tool failure, capability
ceiling, or weak oracle. Do not escalate model tier merely because a result is
uncertain without an observable signal. A failure, escalation, direct-Sol
use, or model-price change receives an immediate review.

## Audit records and review cadence

Each attempt has a `pre_decision` record before routing. A failed execution or
policy gate records its terminal `post_result` immediately. A successful child
execution remains an incomplete audit attempt until the separate integration
finalization succeeds; only then is the accepted `post_result` appended. This
prevents an execution-only success from being frozen as a rejected result that
later finalization cannot replace in the append-only ledger. Within one
installed terminal/receipt/audit schema, receipt-gate and pre-gate failures
remain pending for a corrected submission.

Schema updates do not bridge an incomplete trust chain. Finalize v1
terminal/receipt plus linked `0.2.0` pending attempts before updating. After the
update they remain historical evidence but are non-finalizable and must not be
rewritten or backfilled. Re-execution starts a new task ID at attempt index 1
with a new dispatch ID and packet, v2 execution/terminal/receipt, and linked
`0.3.0` records.

The records
identify the selected model and effort, task shape, bounded envelope, evidence
observed, outcome, failure class if any, escalation or retry action, and next
decision. This local ledger contains machine-local identifiers and evidence
references and must be treated as sensitive. It contains no prompt or
transcript bodies and must never be uploaded; use the allowlisted
`issue-report` formatter for public reporting.

When a decision needs detailed evidence, use the optional structured fields
rather than prose:

- `pre_decision_detail` records `boundedness`, `context_pressure`,
  `constraint_count`, finite `task_shape_signals`, finite
  `expected_oracle_types`, and finite
  `cheaper_route_not_chosen_because` values.
- `post_result_detail` records finite `observable_result_signals`, one to eight
  bounded `evidence_references`, a `route_assessment` of `correct`,
  `too-cheap`, `too-premium`, or `inconclusive`, and a finite `next_action`
  including same-route retry, scope narrowing, environment retry, effort/model
  escalation, or main takeover where applicable.
- Optional `token_observation` and `elapsed_observation` values distinguish
  exact, estimated/lower-bound, and unavailable measurements. Reviews exclude
  unavailable measurements from per-accepted-task denominators and report
  their coverage counts instead of treating an unknown value as zero cost.

Evidence references identify a local test/report/receipt/rollout path or stable
ID only. They reject URI schemes, user-info, query strings, fragments, control
characters, duplicates, and oversized values. Never place prompts,
transcripts, raw logs, credentials, request/response bodies, or secret-bearing
URLs in the audit ledger. Existing `0.1.0` records without the optional detail
objects remain valid.

For the first **100 accepted attempts**, retain detailed accepted-attempt
evidence sufficient to compare route, effort, oracle strength, result, and
cost/efficiency observations. After that configured threshold, retain the
required compact audit fields and continue reviewing according to the cadence.
Review accepted attempts at every **25 accepted attempts**. Review
immediately for every failure, escalation, direct-Sol route, and model-price
change, plus every non-`correct` route assessment, regardless of the periodic
count. The audit CLI creates these triggered reviews automatically unless an
explicit maintenance import disables auto-review. Reviews live under
`$RUNTIME_HOME/state/model-routing/reviews/` and must link to compact ledger
evidence rather than copying sensitive payloads.

The primary efficiency metrics are:

For typed direct execution, weighted tokens are
`ceil(input_tokens / 4) + output_tokens`; Codex input usage already includes
cached input. The raw CLI `tokens used` display is therefore not the enforcement
number. Model-relative price factors are never aggregated as a common cost.
Reviews segment current records by schema version, policy fingerprint, model,
and effort; legacy records remain readable but do not drive current-policy
recommendations.

- first-pass acceptance rate;
- effort-escalation rate and model-escalation rate;
- exact effort-only transition, model transition, same-route retry, and main
  takeover counts derived from consecutive task attempts;
- Sol-rescue rate;
- avoidable-premium-call rate;
- false-cheap-route rate;
- elapsed time per accepted task;
- weighted tokens per accepted task;
- tokens and calls by model/effort within a policy-fingerprint segment;
- route-assessment counts and next-action counts.

Supporting audit counts and thresholds are:

- attempt record count by `pre_decision` and `post_result`;
- accepted-attempt count, with detailed evidence through accepted attempt 100;
- periodic review count and due points at every 25 accepted attempts;
- failure count by each configured class, including
  `scope_or_retrieval_overbreadth`;
- retry count and same-model reasoning retry count, capped at one per stage;
- reevaluation count, expected after every attempt;
- escalation count and ladder step reached;
- direct-Sol count;
- model-price-change count;
- outcome, selected model, reasoning effort, task shape, oracle strength, and
  evidence/acceptance result for each attempt;
- for rejected child admissions, `child_count=0` and `child_tokens=0` when
  that fallback record applies.

These metrics are audit observations, not claims that an unavailable runtime
cap or hidden process was enforced. Native quantitative caps are unavailable
or advisory without trusted live parent monitoring. Network remains off unless
the packet explicitly permits it.

## Decision rule

Start with the narrowest applicable Luna default. Validate the acceptance
oracle and envelope before spending more model capability. On an observable
failure, apply the taxonomy action and reevaluate; increase effort before
changing tier when the failure is reasoning insufficiency. Move along the
configured ladder only when evidence supports escalation. If the oracle is
weak or the risk/contract is too high for a leaf to verify, keep authority at
the main and use `gpt-5.6-sol/ultra`; never assign `ultra` to a leaf.

Model or reasoning escalation changes capability, not authority or scope. Each
route, including main takeover, inherits the packet's canonical Objective Lock
and stops when its acceptance evidence is proved. The lock digest excludes
route, model, effort, attempt index, and resource budget, so capability changes
cannot silently redefine the task. Linked `0.3.0` audit transitions require the
same Objective Lock version and digest. Objective Lock v1 and legacy `0.1.0`
and `0.2.0` records remain readable, but a task history cannot cross schema or
Objective Lock versions.

A weak oracle is a reason to retain authority at the main and repair the
oracle or report an inconclusive result, not permission to redesign adjacent
systems or accept solely because the model is stronger. Broader work requires
a new, explicitly authorized task or packet.
