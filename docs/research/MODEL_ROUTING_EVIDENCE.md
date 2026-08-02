# Model-routing evidence dossier

Status: non-deployed maintainer evidence. Captured 2026-08-02.

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

## Official sources

| Source | Relevant fact | Confidence and limitation |
| --- | --- | --- |
| [OpenAI model guidance](https://developers.openai.com/api/docs/guides/latest-model) | Positions Sol for frontier work, Terra for an intelligence/cost balance, and Luna for efficient high-volume work. Recommends representative evaluation. | High authority for product positioning; not an acceptance oracle for this workload. |
| [GPT-5.6 launch](https://openai.com/index/gpt-5-6/) | Reports the family capabilities, common 1.05M context and 128K output limits, and vendor benchmark tables. | High authority for published configuration and vendor results; launch pricing is stale after 2026-07-30. |
| [2026-07-30 price update](https://openai.com/index/advancing-the-price-performance-frontier-with-gpt-5-6/) | Current standard API prices: Sol `$5/$30`, Terra `$2/$12`, Luna `$0.20/$1.20` per million input/output tokens. It also says lower Terra/Luna prices reduce Codex credit consumption. | Highest current pricing evidence. Recheck on every package release. |
| [Model catalog](https://developers.openai.com/api/docs/models) and [comparison page](https://developers.openai.com/api/docs/models/compare) | Confirm model IDs, supported efforts/tools, context, and output limits. At capture time these pages still displayed the older Terra `$2.50/$15` and Luna `$1/$6` prices. | Official-source conflict: use the newer dated price announcement and keep the mismatch visible. |
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
