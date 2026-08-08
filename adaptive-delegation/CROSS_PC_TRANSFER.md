# Cross-PC installation

**Codex only:** install this package into a Codex home. Claude Code and other
runtimes are not supported execution targets.

Use a fresh clone on the target computer:

```sh
git clone https://github.com/ai-dev-methodologies/adaptive-delegation.git
cd adaptive-delegation
python3 scripts/install.py --dry-run
python3 -m unittest -v tests.test_install tests.test_dispatcher_gate
python3 -m unittest discover -v -s adaptive-delegation/tests -p 'test_*.py'
python3 scripts/install.py
```

Use `--codex-home /path/to/.codex` only when the target computer uses a
non-default Codex home. Never reuse the source computer's absolute home path.

The installer deploys only the runtime allowlist to
`$CODEX_HOME/skills/adaptive-delegation/`, the dispatcher to
`$CODEX_HOME/scripts/`, and exact package-declared roles to
`$CODEX_HOME/agents/`. The package config remains the only routing-policy source
of truth. Repository tests, deployment-only documentation, maintainer
references, bytecode, and caches stay in the checkout.

When intentionally installing an older revision, compare its declared
`role_bindings` with `$CODEX_HOME/agents/adaptive-*.toml` and remove only
adaptive role files absent from that revision. Older installers cannot know
role names introduced later.

## Do not transfer runtime state

Authenticate Codex independently on the target computer. Never copy:

- authentication, credentials, or tokens;
- model-routing attempts or reviews;
- the adaptive-delegation continuity ledger;
- dispatcher, rollout, or session logs;
- generated agent-role files from another Codex home; or
- repository-local hidden runtime-state directories.

These directories are ignored by Git, but a raw filesystem copy or archive can
still include them. Prefer `git clone`; otherwise inspect the archive before
transfer.

## Verify the target computer

The dry run and tests above prove package completeness, Python syntax,
policy-to-role bindings, route-transition validation, receipt fail-closed
behavior, and installer portability without using state from the source
computer. Codex normally detects the skill after installation; restart only if
the skill is not visible.

The current policy is Luna-first and effort-first. After observable Luna
acceptance/quality failure, scoped implementation/transformation uses Terra
medium and bounded complex/debug/review uses Terra high before Sol leaf routes.
Any bounded slice that is latency-insensitive, long-horizon, low/medium risk,
and has a strong oracle uses Luna max, then Terra xhigh/max, before Sol high.
Goal/Ultragoal labels are not route inputs.
Every leaf route resolves to an installed fixed Codex role, leaf `ultra` is
forbidden, and unresolved or weak-oracle work returns to the main
`gpt-5.6-sol/ultra` authority. The main gate uses declared session context and
cannot mutate the parent model.

Automatic escalation is Luna `medium/high/xhigh/max` as applicable, then Terra
`medium` or `high` by task shape, then Sol `medium` and (for implementation or
complex work) Sol `high`, followed by main Sol `ultra` takeover. The separate
quota-first long-horizon path uses Terra `xhigh`/`max` only after Luna max failure.
Ordinary runs passively record `use_mode=post_luna_failure` or `direct_latency`
for accepted-task outcome audits; no paired A/B is run.

## Report a target-PC result

Keep raw ledgers on the target computer. From the repository clone, generate an
allowlisted local summary:

```sh
python3 adaptive-delegation/scripts/model_routing_audit.py issue-report
```

Inspect the output and follow the installed
`references/CODEX-ISSUE-REPORT-PROMPT.md` or the repository's `REPORTING.md`.
Publish only the sanitized summary and non-sensitive reproduction details.
After publication, record the canonical issue URL with `record-submission` so
later reports exclude already-shared attempt fingerprints. Preserve the local
`state/model-routing/issue-report-state.jsonl` management ledger across package
updates, but never upload or copy it to another computer.

## Copy-ready setup request

```text
Install the Codex-only adaptive-delegation skill on this computer from
https://github.com/ai-dev-methodologies/adaptive-delegation.git.

Use a fresh clone, run the installer dry run and both documented unittest
commands, then run python3 scripts/install.py. Use --codex-home only when this
computer has a non-default Codex home.

Do not copy authentication, logs, issue-report state, continuity data,
rollout/session state, generated role files, or hidden runtime-state
directories from another computer. Keep the package config as the only
routing-policy source. Report failures with the privacy-safe, duplicate-aware
issue-report workflow, never with raw ledgers.
```
