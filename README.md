# Adaptive Delegation

This standalone repository contains the portable
`adaptive-delegation` skill. It routes bounded implementation and verification
work through a Luna-first, effort-first ladder, requires observable evidence,
and lets the main take over when a leaf cannot provide a trustworthy result.

Use `$adaptive-delegation` explicitly when deterministic activation matters.
Implicit activation is also allowed for matching requests. The skill metadata
contains the two supported localized trigger literals, while the reference
examples remain in English; see
[`adaptive-delegation/references/TRIGGERS.md`](adaptive-delegation/references/TRIGGERS.md).

For a complete developer installation path, see
[`INSTALL.md`](INSTALL.md).

Activation first verifies that the current main authority is exactly
`gpt-5.6-sol` with `reasoning_effort` set to `high`, `xhigh`, `max`, or `ultra`.
If not, it launches no child because the skill cannot mutate the parent model.

## Evidence and routing

The default route is Luna-first and effort-first. Leaf `ultra` is forbidden;
the main may take over at `gpt-5.6-sol/ultra`. Failure classification uses only
observable tests, contradictions, missed constraints, truncation or context
evidence, runtime/tool errors, and oracle strength.

Native Luna is selected through an installed fixed Luna `agent_type`; the role
binding supplies the exact model while the call passes matching effort and
`fork_turns="none"`. Luna's absence from the optional model-override enum is not
a Native rejection. Use the typed direct dispatcher only when the fixed role or
surface is unavailable/rejected, runtime evidence mismatches, or a hard cap is
required. Never silently substitute Terra.

Central routing attempts are append-only in
`~/.codex/state/model-routing/attempts.jsonl`, with reviews in
`~/.codex/state/model-routing/reviews/`. When asked to validate model
selection, audit logs are read automatically before reporting a result.

The policy records Luna as a user-provided 80% reduction versus its prior
price and Terra as a user-provided 20% reduction versus its prior price. These
are relative changes, not absolute prices or official pricing claims. Routing
is provisional and evidence-seeking.

## Install from GitHub

Python 3.11 or newer is required. Clone the repository and run the installer:

```sh
git clone https://github.com/ai-dev-methodologies/adaptive-delegation.git
cd adaptive-delegation
python3 scripts/install.py
```

The default target is `$CODEX_HOME`, or `~/.codex` when `CODEX_HOME` is unset.
Use `--codex-home /path/to/.codex` for another target and `--dry-run` to
validate the package without writing. The installer atomically replaces the
managed skill package, installs the compatibility dispatcher, and regenerates
only the adaptive role bindings declared by the package policy.

Codex detects skill changes automatically. Restart only if the changed skill
does not become visible after installation.

The installer never copies authentication, audit logs, continuity records,
rollout/session data, or local policy overrides. Those remain machine-local.

## Verify an installation

```sh
python3 scripts/install.py --dry-run
python3 -m unittest -v tests.test_install tests.test_dispatcher_gate
python3 -m unittest discover -v -s adaptive-delegation/tests -p 'test_*.py'
```

The main-authority gate is fail-closed but uses declared current-session
context; it is not cryptographic proof and cannot mutate the parent model.

## Maintenance

Repository-local governance is in
[`AGENTS.md`](AGENTS.md). The copy-paste maintenance handoff prompt is
[`prompts/maintain-adaptive-delegation.md`](prompts/maintain-adaptive-delegation.md).
Both point maintainers to the canonical package source, policy, continuity
rules, bounded Maker/Checker review, portable verification, and privacy
boundaries. Update repository files first; installed `~/.codex` copies are
deployment targets only.

The canonical source repository is
<https://github.com/ai-dev-methodologies/adaptive-delegation.git>.
