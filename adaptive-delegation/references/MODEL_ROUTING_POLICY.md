# Model Routing Policy

This document explains the package-default policy in
`config/model-routing.defaults.json`. That JSON is the policy source of truth;
this document explains its evidence basis and operating rules without
overriding it. An optional local override may be read, while the legacy OMX
configuration is read-compatible fallback only and is never authoritative or
written by this policy.

## Evidence basis

Routing decisions must be supported by observable evidence: acceptance tests,
test contradictions, missed constraints, truncation or context-ceiling
signals, runtime or tool errors, and the strength of the acceptance oracle.
Hidden reasoning is not evidence and must not be used to invent a failure
class. When a case is ambiguous, record the observation before turning it into
a rule. A pre-decision record captures the planned route and evidence; a
post-result record captures the observed result, classification, and next
action. Records are append-only in
`~/.codex/state/model-routing/attempts.jsonl`.

Current public Codex guidance provides the qualitative starting point for the
defaults:

- [Models](https://learn.chatgpt.com/docs/models) describes Sol for complex,
  open-ended, high-value work; Terra as the everyday reasoning workhorse; and
  Luna for clear, repeatable, high-volume work with a known acceptance shape.
- The same guide recommends using the lowest reasoning effort that produces
  the needed result and increasing it for work that needs more planning,
  analysis, or checking. It describes Max as extra reasoning time for a single
  hard task, while Ultra uses subagents for divisible parallel work.
- [Subagents](https://learn.chatgpt.com/docs/agent-configuration/subagents)
  notes that each subagent performs its own model and tool work, so delegation
  consumes more tokens than a comparable single-agent run. It recommends
  bounded independent work and distilled results, especially for read-heavy
  exploration, tests, triage, and summarization.

Those sources support Luna-first bounded routing, result-driven effort
adjustment, and keeping Ultra at the orchestrating main rather than a leaf.
They do **not** establish numeric quality equivalence between models, a
universal break-even point, or the user-provided Luna/Terra price reductions.
The exact thresholds and ladders below are therefore provisional hypotheses
that must be evaluated through the local audit ledger and acceptance oracles.

The policy is provisional and evidence-seeking. Reevaluate after every
attempt. Use one same-model reasoning-effort retry per stage at most, then
reassess the evidence and route. An accepted result is not proof that the
route was optimal; accepted-attempt reviews and the configured metrics are
used to update the evidence base.

## Defaults and ladders

The default strategy is Luna-first and effort-first:

| Work shape | Default route |
| --- | --- |
| Simple lookup or extraction | `gpt-5.6-luna/medium` |
| Clear implementation or transformation | `gpt-5.6-luna/high` |
| Bounded complex implementation or verification | `gpt-5.6-luna/xhigh` |
| Former Terra bounded | `gpt-5.6-luna/xhigh` |
| Former Sol bounded with a strong oracle | `gpt-5.6-luna/max` |
| Weak oracle, ambiguous/high-risk, or long contract | main-authoritative `gpt-5.6-sol/ultra` |

Effort is increased before changing model tier when the failure evidence is
reasoning insufficiency and the task remains within the current model's
capability and context envelope. The configured same-model retry limit is one
per stage. A context ceiling or capability ceiling increases model tier;
scope or retrieval overbreadth narrows the envelope and retries the same
route; a tool or environment failure repairs the environment and retries the
same route.

The configured ladders are:

- Former Terra bounded: `luna/xhigh -> luna/max -> terra/xhigh -> terra/max -> main-takeover sol/ultra`.
- Former Sol bounded with a strong oracle: `luna/max -> terra/max -> sol/high -> main-takeover sol/ultra`.
- Weak oracle, ambiguous/high-risk, or long contract: `main-authoritative sol/ultra`, with optional `luna/xhigh` scout-only work.

The main may take over when the weak-oracle condition means a leaf cannot
truthfully establish acceptance, or when the ladder reaches its takeover
step. Main takeover is authoritative `gpt-5.6-sol/ultra`; a leaf may never
use `ultra`. `gpt-5.6-sol/high` is a ladder step only where the configured
strong-oracle ladder permits it, not a leaf-`ultra` exception.

The package records Luna as a **user-provided 80% reduction versus its prior
price** and Terra as a **user-provided 20% reduction versus its prior price**.
These are relative changes supplied by the user, not absolute prices and not
official API-price claims. A price-change observation is an audit trigger; it
does not turn those labels into price facts.

## Native role selection

Prefer Native Luna by choosing an installed fixed Luna `agent_type`, verifying
its TOML model/effort binding, passing the same effort and `fork_turns="none"`,
and validating trusted runtime model/effort evidence. The role selection is an
explicit model choice. Luna need not appear in the optional `model` override
enum, so its absence there is not evidence that Native Luna is unsupported.

Use an explicit `model` override only on a surface that supports it and accepts
the exact requested value. Use typed direct only when the fixed role or Native
surface is unavailable/rejected, trusted runtime evidence mismatches, or the
task requires a hard parent-enforced cap. Never substitute Terra merely because
the optional override enum omits Luna.

## Observable failure taxonomy and actions

Classify only what can be observed at the task boundary:

| Failure class | Observable signal | Action |
| --- | --- | --- |
| `reasoning_insufficiency` | The route remains in scope, but a check or contradiction shows the current effort was insufficient. | Increase effort on the same model once, then reevaluate. |
| `context_ceiling` | Truncation, context exhaustion, or a directly observed context limit. | Increase model tier according to the applicable ladder. |
| `scope_or_retrieval_overbreadth` | The task envelope or retrieved material is too broad for the bounded acceptance claim. | Narrow the envelope or retrieval, then retry the same route. |
| `tool_or_environment` | A runtime, tool, dependency, or environment error prevents a meaningful attempt. | Repair the environment, then retry the same route. |
| `capability_ceiling` | Direct evidence shows the current model cannot satisfy the required capability. | Increase model tier according to the applicable ladder. |
| `weak_oracle` | Acceptance cannot be independently established because the oracle is ambiguous, unavailable, or too weak for the risk. | Main-authoritative takeover at `gpt-5.6-sol/ultra`; leaf work can be scout-only if useful. |

Do not relabel a missed requirement as reasoning insufficiency when the
evidence shows an overbroad scope, context ceiling, tool failure, capability
ceiling, or weak oracle. Do not escalate model tier merely because a result is
uncertain without an observable signal. A failure, escalation, direct-Sol
use, or model-price change receives an immediate review.

## Audit records and review cadence

Each attempt has a `pre_decision` record before routing and a `post_result`
record after the attempt. The records identify the selected model and effort,
task shape, bounded envelope, evidence observed, outcome, failure class if
any, escalation or retry action, and next decision. They contain compact
metadata and evidence paths, not hidden reasoning or payloads.

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
`~/.codex/state/model-routing/reviews/` and must link to compact ledger
evidence rather than copying sensitive payloads.

The primary efficiency metrics are:

For typed direct execution, weighted tokens are
`ceil(input_tokens / 4) + output_tokens`; Codex input usage already includes
cached input. The raw CLI `tokens used` display is therefore not the enforcement
number. `cost_proxy` applies the configured user-provided relative price factor
to weighted tokens and is not a provider bill or official absolute price.

- first-pass acceptance rate;
- effort-escalation rate and model-escalation rate;
- exact effort-only transition, model transition, same-route retry, and main
  takeover counts derived from consecutive task attempts;
- Sol-rescue rate;
- avoidable-premium-call rate;
- false-cheap-route rate;
- elapsed time per accepted task;
- weighted tokens per accepted task;
- cost proxy per accepted task.
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
