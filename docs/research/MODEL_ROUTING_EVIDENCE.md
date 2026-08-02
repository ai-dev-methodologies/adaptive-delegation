# Model-routing evidence dossier

Status: non-deployed maintainer evidence. Captured 2026-08-02; official
pricing and model guidance rechecked 2026-08-03.

This document preserves the external research behind the provisional Sol,
Terra, and Luna routing policy. It is deliberately separate from the deployed
skill: `SKILL.md` stays short enough for runtime use, while this dossier keeps
the sources, measurements, conflicts, confidence, and review triggers needed
to change policy later.

## Evidence precedence

Use evidence in this order:

1. Local accepted-task and review logs from the real Codex workload.
2. Reproducible task-specific evaluations with a strong acceptance oracle.
3. Independent benchmarks with disclosed tasks or methodology.
4. Official vendor guidance and vendor-reported benchmarks.
5. Practitioner reports, issue threads, and community anecdotes.

External evidence selects hypotheses; it never overrides a contrary local
acceptance result. Before changing a route, read this dossier and the latest
local audit review. Do not activate a model or effort from anecdotes alone.

## Current decision

- Default fresh bounded work to Luna and raise Luna effort before changing
  model tier.
- Use Terra `medium` or `high` after observable Luna failure for ordinary
  bounded work, or as a main-selected direct-latency lane with a measurable
  time constraint and strong oracle.
- Field-test Terra `xhigh` and `max` only after Luna max failure on active
  goal/Ultragoal work that is latency-insensitive, long-horizon, risk
  `low`/`medium`, and has a strong oracle. This is a quota-saving hypothesis,
  not a quality-equivalence claim.
- Use Sol leaf routes when the bounded result still fails materially. Keep
  weak-oracle, ambiguous, high-risk, and long-contract work main-authoritative.
- Run no random or perpetual paired A/B. Record ordinary Terra use as
  `post_luna_failure` or `direct_latency`, then review real accepted outcomes.

## Cost, latency, and capability decision matrix

The price factors below use the 2026-07-30 standard API rates and normalize
both input and output prices to Sol. They are also the package's routing cost
proxy. They are not a conversion formula for a Codex subscription's weekly
quota, although OpenAI states that the lower Terra and Luna prices now consume
fewer Codex credits.

| Route | API price factor vs Sol | Wall-clock expectation | Capability and accepted-task risk | Current use |
| --- | ---: | --- | --- | --- |
| Luna `medium/high` | `0.04` | Usually the lowest-latency starting point; tool or context loops can erase that advantage. | Cheapest bounded execution, but retries can dominate if the packet or oracle is weak. | Default for simple and clear bounded work. |
| Luna `xhigh/max` | `0.04` | More reasoning can take materially longer than lower Luna efforts and may be slower than Terra `medium/high`. | Preserves the cheapest token tier while testing whether effort alone closes the quality gap. | Raise effort before model tier; use `max` first for the declared quota-first long-horizon route. |
| Terra `medium/high` | `0.40` | Variable, not categorically slow. Official scoped-work evidence and an independent snapshot show a defensible faster mid-quality niche. | Costs 10x Luna per token but 60% less than Sol. It is useful only when it avoids more Luna retries or a Sol call. | After observable Luna failure; direct use only for a main-declared latency-sensitive, scoped, strong-oracle task. |
| Terra `xhigh/max` | `0.40` | Expect long elapsed time and more reasoning/tool steps; speed is not the goal. | Can approach Sol on some long-horizon benchmarks at a lower per-token rate, but a later Sol rescue can erase the saving. | Provisional post-Luna quota-first lane for latency-insensitive, low/medium-risk work with a strong oracle. |
| Sol `medium/high` leaf | `1.00` | A stronger one-pass result can be faster than a failed cheaper chain even though each token costs more. | Highest bounded-leaf capability and price. | Only after the configured Luna/Terra evidence path fails. |
| Main Sol `ultra` | `1.00` plus highest main effort | Quality-first and potentially longest; elapsed time is subordinate to authority and ambiguity resolution. | Main owns intent, weak-oracle judgment, high-risk decisions, integration, and final takeover. | Never a leaf; use when the task cannot be safely judged by the cheaper bounded ladder. |

Two totals decide whether Terra is useful:

- **Accepted-task cost** is the sum of every serialized attempt, retry, and
  rescue needed to reach acceptance, not the price of the Terra call alone.
- **Accepted-task latency** is the sum of serialized attempt time, queue/tool
  time, and recovery time. Terra `medium/high` may own a direct-latency niche;
  Terra `xhigh/max` owns a quota-saving hypothesis and is allowed to be slower.

Therefore, “Terra is cheaper but slower” is accurate only for the provisional
`xhigh/max` lane. It is not a family-wide property. Keep Terra only when its
assigned lane improves accepted-task cost, Sol usage, intervention count, or a
declared latency target. If Luna failure followed by Terra failure and Sol
rescue becomes common, narrow or remove that Terra hop.

## Official sources

| Source | Relevant fact | Confidence and limitation |
| --- | --- | --- |
| [OpenAI model guidance](https://developers.openai.com/api/docs/guides/latest-model) | Positions Sol for frontier work, Terra for an intelligence/cost balance, and Luna for efficient high-volume work. Recommends representative evaluation. | High authority for product positioning; not an acceptance oracle for this workload. |
| [GPT-5.6 launch](https://openai.com/index/gpt-5-6/) | Reports the family capabilities, common 1.05M context and 128K output limits, and vendor benchmark tables. | High authority for published configuration and vendor results; launch pricing is stale after 2026-07-30. |
| [2026-07-30 price update](https://openai.com/index/advancing-the-price-performance-frontier-with-gpt-5-6/) | Current standard API prices: Sol `$5/$30`, Terra `$2/$12`, Luna `$0.20/$1.20` per million input/output tokens. It also says lower Terra/Luna prices reduce Codex credit consumption. | Highest current pricing evidence. Recheck on every package release. |
| [Model catalog](https://developers.openai.com/api/docs/models) and [comparison page](https://developers.openai.com/api/docs/models/compare) | Confirm model IDs, supported efforts/tools, context, and output limits. On the 2026-08-03 recheck these pages still displayed the older Terra `$2.50/$15` and Luna `$1/$6` prices. | Official-source conflict: use the newer dated price announcement and keep the mismatch visible. |
| [OpenAI outcome scorecard](https://openai.com/index/a-scorecard-for-the-ai-age/) | States that cost per successful task depends on price, compute used, and the chance of reaching the right result; a frontier model can win when it avoids retries and review. | High-authority support for accepted-task accounting, not a model-specific route benchmark. |
| [GPT-5.6 preview system card](https://deploymentsafety.openai.com/gpt-5-6-preview/gpt-5-6-preview.pdf) | Records safety evaluation context for the family. | Relevant to high-risk authority boundaries, not a routing-quality benchmark. |

### Vendor-reported benchmark snapshot

Values are Sol / Terra / Luna from the launch material. Different benchmarks
exercise different skills; small score gaps do not imply interchangeable
behavior on a specific repository.

| Benchmark | Sol | Terra | Luna | Routing signal |
| --- | ---: | ---: | ---: | --- |
| Agents' Last Exam | 52.7 | 50.4 | 50.3 | Terra and Luna are close on this aggregate. |
| GDPval-AA v2 Elo | 1747.8 | 1593.0 | 1591.8 | Terra and Luna are effectively tied here. |
| Management Consulting Tasks | 43.2 | 37.2 | 35.4 | Terra has a modest intermediate result. |
| Big Finance Bench | 53 | 51 | 36 | Terra can materially exceed Luna on some professional domains. |
| AA Coding | 80.0 | 77.4 | 74.6 | Gradual capability slope, not proof of cost efficiency. |
| SWE-Bench Pro | 64.6 | 63.4 | 62.7 | Small aggregate separation. |
| DeepSWE | 72.7 | 69.6 | 67.2 | Terra is intermediate, but local long-horizon evidence matters more. |
| Terminal benchmark | 88.8 | 87.4 | 84.7 | Supports a possible Terra terminal-work niche. |
| Internal Research Debugging | 68.3 | 67.8 | 50.8 | Strongest vendor signal for Terra on bounded research/debugging. |

## Independent and task-specific evidence

### Artificial Analysis

- [Intelligence versus cost analysis](https://artificialanalysis.ai/articles/gpt-5-6-intelligence-vs-cost-across-sol-terra-luna)
  found Luna and Sol ahead of Terra at many cost/intelligence points. Its cost
  analysis predates the latest price cut, which makes Luna still more favorable.
- [GPT-5.6 launch analysis](https://artificialanalysis.ai/articles/gpt-5-6-has-landed/)
  provides an independent family-level benchmark view.
- The dynamic [OpenAI provider comparison](https://artificialanalysis.ai/providers/openai/)
  captured on 2026-08-02 showed the same index score for Luna `high` and Terra
  `medium` (46), but a substantially shorter total response time for Terra;
  likewise Luna `xhigh`, Terra `high`, and Sol `low` clustered at index 49,
  with Terra `high` fastest in that snapshot. Terra `xhigh`/`max` were largely
  dominated by Sol `medium`/`high` on the general index. The page's displayed
  cost-per-task values appeared to lag the July 30 price cut, so use its
  quality/latency topology, not its cost column, until refreshed.

Inference: Terra `medium/high` has a defensible latency-sensitive niche at
mid-quality. The stale pre-cut cost column cannot rule out a slower,
quota-first Terra `xhigh/max` lane, so local post-Luna field evidence now owns
that decision.

### Coding and terminal benchmarks

| Source | Sample and result | Limitation | Policy implication |
| --- | --- | --- | --- |
| [DeepSWE v1.1](https://deepswe.datacurve.ai/blog/deepswe-v1-1) | 113 long-horizon tasks. Sol `max` 73% ±3, Terra `max` 70% ±3, Luna `max` 67% ±4. Reported average output/steps: 60K/61, 72K/76, 73K/102. | Reported dollar costs predate the July 30 cut; all rows use `max`, not the proposed medium/high lane. | Confirms capability ordering but strengthens Luna-first after the price cut. |
| [Terminal-Bench 2.1](https://www.tbench.ai/leaderboard/terminal-bench/2.1) | Codex Terra `max` 78.4% ±1.3 versus Luna `max` 75.7% ±1.3. | Pre-cut costs; no comparable Sol row in the captured leaderboard slice. | Weak support for Terra on terminal-heavy work, not enough for an automatic max route. |
| [Superconductor custom Rails benchmark](https://www.superconductor.com/blog/gpt-5-6-benchmark) | Custom production tickets: Sol `high` about 77%, Terra `high` 70%, Luna `high` 66%; all GPT-5.6 variants finished around 5–6 minutes. | One codebase and vendor-authored evaluation. | Supports Terra high as a bounded intermediate; Sol remains preferred when quality dominates. |
| [CodeRabbit Sol/Terra benchmark](https://www.coderabbit.ai/blog/gpt-5-6-sol-and-terra-benchmark) | Long coding: Sol 63.7% with 20,968 average output tokens, Terra 40.7% with 55,594. Review: Sol 69.7% actionable pass, Terra 52.5%. | Vendor harness and pre-cut price table. | Terra may fit scoped triage, but long coding and final review should escalate when its result fails. |
| [Small Medium comparison](https://medium.com/@xujfcn/i-paid-twice-as-much-for-gpt-5-6-sol-did-it-beat-gpt-5-6-terra-95c1b1d839f4) | Four proxy/API tasks; both models completed all four, and Terra was faster/cheaper on two testable coding tasks. | Tiny sample through a compatible proxy; no policy-grade inference. | Latency hypothesis only. |

### Human preference evidence

[Prolific HUMAINE](https://www.prolific.com/resources/gpt-5-6-joins-the-humaine-leaderboard-how-sol-terra-and-luna-rank-with-real-people)
blind-tested the family with more than 2,000 participants and nearly 2,900
head-to-head conversations. Terra ranked higher than its siblings on task
performance, but technical assistance was under 3% of the broader conversation
mix. This is useful for user-facing interaction context, not a coding route
oracle.

## Operational incident evidence

Practitioner issue reports show why model escalation must follow an observed
capability failure rather than any failed run:

- [Codex issue 33816](https://github.com/openai/codex/issues/33816): terminal or
  ownership behavior can create failures unrelated to model intelligence.
- [Codex issue 32162](https://github.com/openai/codex/issues/32162): unattended
  search failed across both Terra and Sol in the report.
- [Codex issue 32389](https://github.com/openai/codex/issues/32389): an empty
  final response appeared around a large context size.
- [Codex issue 32406](https://github.com/openai/codex/issues/32406): planning
  loop behavior can consume time without being a capability comparison.
- [Codex issue 33267](https://github.com/openai/codex/issues/33267): a headless
  multi-agent harness failed across both Sol and Terra.

Inference: tool/environment and harness failures must trigger environment
recovery, not `raise_effort` or `raise_model`. Context ceilings require their
own observable classification.

## DCInside practitioner survey

The AI-utilize gallery search pages 1–4 and selected thread comments were read
on 2026-08-02. These are anonymous, self-selected reports without controlled
prompts, version pinning, or repeatable oracles. They are hypothesis generators
only.

| Threads | Reported pattern | Hypothesis to test locally |
| --- | --- | --- |
| [17738](https://gall.dcinside.com/mgallery/board/view/?id=ai_utilize&no=17738), [17539](https://gall.dcinside.com/mgallery/board/view/?id=ai_utilize&no=17539) | Terra was described as a time-saving higher-reasoning option, but its position became ambiguous after Luna's price cut; Luna context retention was a concern. | Compare Terra latency only after a Luna quality/context failure; do not infer a max route. |
| [17873](https://gall.dcinside.com/mgallery/board/view/?id=ai_utilize&no=17873) | On a 50-document synthesis, Luna initially gathered material without inferring the desired synthesis, then produced a strong answer after explicit instruction. Terra was reported adequate for difficult research. | Luna benefits from a precise outcome and strong oracle; retry prompt clarity before model escalation. |
| [17880](https://gall.dcinside.com/mgallery/board/view/?id=ai_utilize&no=17880), [16921](https://gall.dcinside.com/mgallery/board/view/?id=ai_utilize&no=16921) | Users favored Sol for planning/review and Luna for worker execution; some saw Terra as useful when memory/latency mattered. | Keep planning authority at main Sol and push bounded execution to Luna. |
| [18088](https://gall.dcinside.com/mgallery/board/view/?id=ai_utilize&no=18088), [18182](https://gall.dcinside.com/mgallery/board/view/?id=ai_utilize&no=18182) | Some users found Terra high inadequate for design versus Sol medium or saw no reason to use smaller models when quota was abundant. | Terra is not a design default; its value depends on quota and latency constraints. |
| [17499](https://gall.dcinside.com/mgallery/board/view/?id=ai_utilize&no=17499), [15977](https://gall.dcinside.com/mgallery/board/view/?id=ai_utilize&no=15977) | Luna high was reported sufficient for tool-backed structured settlement work; users separated structured, mixed-text, and unstructured work. | Strong tools/oracles can move more work to Luna. |
| [16919](https://gall.dcinside.com/mgallery/board/view/?id=ai_utilize&no=16919), [15930](https://gall.dcinside.com/mgallery/board/view/?id=ai_utilize&no=15930) | Terra sometimes felt more focused than Sol and consumed less quota; another heuristic assigned short context to Luna, longer context to Terra, complex work to Sol. | Track intervention count, context bucket, elapsed time, and quota pressure before changing routes. |
| [15896](https://gall.dcinside.com/mgallery/board/view/?id=ai_utilize&no=15896) | One local automation benchmark favored Terra `xhigh` over slower Sol high, while Luna was reportedly too slow for that case. | Contradictory single-user evidence; reproduce locally before any xhigh experiment. |

## Local evidence and review contract

Current audit records already provide the minimum decision basis: task class,
oracle/risk class, exact route/model/effort, Terra `use_mode`, observable
failure class, next action, integration acceptance, elapsed time, weighted
tokens, and Sol-equivalent cost proxy. Automatic review runs every 25 accepted
attempts, while detailed accepted-attempt retention covers the first 100.

The latest local review available on 2026-08-03 was generated under policy
`adaptive-delegation-luna-terra-sol-v0.5`, before the current `0.6.0` package.
It contained 96 tasks and 41 accepted tasks, but zero accepted Terra tasks
classified as either `post_luna_failure` or `direct_latency`. Older records do
contain Terra attempts, but they lack the current use-mode classification and
cannot decide whether the present Terra lanes should be retained. The current
policy therefore remains a field-test hypothesis, not a locally proven model
ranking.

For later policy work, prefer adding or deriving these workload dimensions
before drawing a Terra conclusion: context-length bucket, context-retention
failure, human intervention count, retry count, measurable latency/SLO, and
Codex quota pressure. Until they are actually recorded, treat related community
claims as unverified.

Retain a Terra route only if representative local tasks show one of these:

- materially lower elapsed time than the adjacent Luna/Sol path while meeting
  the same acceptance oracle;
- fewer total retries or interventions after an observed Luna failure; or
- higher accepted outcomes for a clearly bounded task family without greater
  total Sol-equivalent cost.

For the quota-first `xhigh/max` lane, elapsed time may regress; require lower
Sol usage or lower total Sol-equivalent cost at comparable acceptance quality.
Remove or narrow Terra if it adds an extra hop without improving the metric its
lane owns. Do not wait for a contrived paired A/B campaign; use ordinary
post-Luna evidence accumulated under each use mode.

## Review triggers and expiry

- Recheck official prices and model capabilities on every package release.
- Revisit the provisional route after each 25 accepted-attempt review and after
  a representative mix of both Terra use modes exists.
- Treat dynamic benchmark cost figures as stale when they predate or fail to
  reflect the 2026-07-30 price cut.
- Community evidence expires on the next policy review or 2026-09-30,
  whichever comes first.
- No external source, including this dossier, overrides a current local
  acceptance failure or the Objective Lock's authority boundary.
