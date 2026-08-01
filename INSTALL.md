# Installation

This guide installs the portable `adaptive-delegation` skill from the
canonical repository:
<https://github.com/ai-dev-methodologies/adaptive-delegation.git>.

## Prerequisites

- Git.
- Python 3.11 or newer.
- A local Codex home. The default is `$CODEX_HOME`, or `~/.codex` when that
  variable is unset.

## Clone and validate

```sh
git clone https://github.com/ai-dev-methodologies/adaptive-delegation.git
cd adaptive-delegation
python3 scripts/install.py --dry-run
```

The dry run validates the package, policy-to-role bindings, and Python source
without writing to the Codex home.

Run the portable checks before installation or after an update:

```sh
python3 -m unittest -v tests.test_install tests.test_dispatcher_gate
python3 -m unittest discover -v -s adaptive-delegation/tests -p 'test_*.py'
```

## Install

Install into the default Codex home with:

```sh
python3 scripts/install.py
```

For another Codex home, pass it explicitly:

```sh
python3 scripts/install.py --codex-home /path/to/.codex
```

The installer atomically updates the managed package and regenerates only the
package-declared adaptive role bindings.

## Installed targets

For a Codex home represented by `$CODEX_HOME`, installation writes:

- `$CODEX_HOME/skills/adaptive-delegation/` — the complete package and policy
  source;
- `$CODEX_HOME/scripts/adaptive_dispatch_attestation.py` — the compatibility
  dispatcher; and
- `$CODEX_HOME/agents/adaptive-*.toml` — the fixed adaptive role bindings.

The package policy source of truth is
`$CODEX_HOME/skills/adaptive-delegation/config/model-routing.defaults.json`.

## Update or reinstall

Pull a repository update, validate it, then rerun the installer:

```sh
git pull --ff-only
python3 scripts/install.py --dry-run
python3 -m unittest -v tests.test_install tests.test_dispatcher_gate
python3 -m unittest discover -v -s adaptive-delegation/tests -p 'test_*.py'
python3 scripts/install.py
```

Running the installer again is the supported reinstall path. It preserves
unmanaged files and shared role files outside the package-declared adaptive
bindings.

## Privacy and local state

The installer does not copy authentication, credentials, audit attempts or
reviews, continuity records, rollout/session data, or local policy overrides.
Keep these machine-local paths out of the repository and transfer process:

- `$CODEX_HOME/auth.json`;
- `$CODEX_HOME/state/model-routing/attempts.jsonl`;
- `$CODEX_HOME/state/model-routing/reviews/`;
- `$CODEX_HOME/state/adaptive-delegation/continuity.jsonl`; and
- `$CODEX_HOME/state/model-routing/policy.local.json`.

The legacy `$CODEX_HOME/.omx-config.json` remains a read-compatible fallback;
it is not the policy source of truth and the installer does not write it.

## Hot-load and restart

Codex normally hot-loads skill changes. If the updated skill is not visible,
restart the Codex process and verify the installed package path above. A
restart is not otherwise required.
