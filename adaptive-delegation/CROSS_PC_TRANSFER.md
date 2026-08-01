# Adaptive Delegation Cross-PC Transfer

Transfer the complete adaptive-delegation package as one portable unit. On the
target PC, use `~` for that user’s home directory; never reuse the source
machine’s absolute home path.

## Install the package

Clone or copy this repository to the target PC, then run:

```sh
python3 scripts/install.py
```

The installer copies the complete package to
`$CODEX_HOME/skills/adaptive-delegation/` (default
`~/.codex/skills/adaptive-delegation/`), installs the package-owned dispatcher
under `$CODEX_HOME/scripts/`, and regenerates the policy-declared adaptive role
bindings under `$CODEX_HOME/agents/`. Use `--codex-home` for a non-default
Codex home.

The package policy SSOT is:

```text
~/.codex/skills/adaptive-delegation/config/model-routing.defaults.json
```

The target PC may create its own optional local override at
`~/.codex/state/model-routing/policy.local.json`; never copy that file from
another PC. The package default remains authoritative. Keep any target-local
`~/.codex/.omx-config.json` available to legacy readers, but treat it only as
a read-compatible fallback: do not promote it to policy SSOT and do not
rewrite it as part of this transfer.

## Keep external and machine-local state external

The installed global dispatcher remains an external compatibility surface, but
its source is distributed inside this package and the installer regenerates it
locally. It is not a second policy source. The same applies to generated
adaptive role bindings: install them from the package templates instead of
copying another machine’s generated files.

Never copy:

- authentication, credentials, tokens, or `~/.codex/auth.json`;
- model-routing attempts `~/.codex/state/model-routing/attempts.jsonl`;
- model-routing review files under `~/.codex/state/model-routing/reviews/`;
- the continuity ledger `~/.codex/state/adaptive-delegation/continuity.jsonl`;
- dispatch ledgers or other logs;
- rollout/session records such as `~/.codex/sessions/**/rollout-*.jsonl`;
- the optional local override `~/.codex/state/model-routing/policy.local.json`.

Authenticate locally and let the target runtime create its own state. Legacy
OMX readers remain supported without making `.omx-config.json` authoritative;
preserving that compatibility does not require copying its machine-specific
contents.

## Local setup and verification

Run `python3 scripts/install.py --dry-run` before or after installation to
validate the package, policy-to-role bindings, and Python sources. Use the
target PC’s local paths and credentials; never move runtime state with the
package. Codex normally detects skill changes automatically; restart only if
the installed update is not visible.

The policy continues to be Luna-first and effort-first. The package config
controls the Luna high/xhigh/max and Terra xhigh/max ladders, one same-model
reasoning retry per stage, leaf-Ultra prohibition, and main Sol/ultra takeover
authority. Relative price notes remain user-provided changes versus prior
prices, not absolute or official API-price claims.

## Copy-ready prompt

```text
Set up the complete adaptive-delegation package on this PC.

Clone https://github.com/ai-dev-methodologies/adaptive-delegation.git and run
python3 scripts/install.py. Use --codex-home only when this PC uses a
non-default Codex home. Do not reuse the source PC's absolute path.

Install the global compatibility dispatcher and adaptive role bindings from
the package through that installer; do not copy generated files from another
machine.

Never copy auth or credentials, model-routing attempts or reviews, continuity
or dispatch logs, rollout/session JSONL, generated ~/.codex/agents/*.toml, or
~/.codex/state/model-routing/policy.local.json. Preserve any local
~/.codex/.omx-config.json for read-compatible legacy OMX readers only; the
package config is the policy SSOT and the legacy file is not written or
authoritative.

Authenticate locally, validate the package and config locally, and report any
failure without copying machine-specific state.
```
