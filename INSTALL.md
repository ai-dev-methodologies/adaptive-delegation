# Installation

**Codex only:** this installs `adaptive-delegation` for Codex native subagents.
Claude Code and other runtimes are not supported execution targets.

Canonical repository:
<https://github.com/ai-dev-methodologies/adaptive-delegation.git>

## Prerequisites

- Git.
- Python 3.11 or newer.
- A local Codex installation and Codex home.

The installer uses `$CODEX_HOME` when set and otherwise uses `~/.codex`.

## First installation

Clone the repository, validate the package without writing, run the portable
tests, and install:

```sh
git clone https://github.com/ai-dev-methodologies/adaptive-delegation.git
cd adaptive-delegation
python3 scripts/install.py --dry-run
python3 -m unittest -v tests.test_install tests.test_dispatcher_gate
python3 -m unittest discover -v -s adaptive-delegation/tests -p 'test_*.py'
python3 scripts/install.py
```

For a non-default Codex home:

```sh
python3 scripts/install.py --codex-home /path/to/.codex
```

The dry run validates package completeness, Python source, and every
policy-to-role model/effort binding without changing the target.

## Installed targets

For a Codex home represented by `$CODEX_HOME`, installation manages:

- `$CODEX_HOME/skills/adaptive-delegation/` — the complete skill package and
  package policy;
- `$CODEX_HOME/scripts/adaptive_dispatch_attestation.py` — the package
  dispatcher; and
- `$CODEX_HOME/agents/adaptive-*.toml` — exact package-declared Codex roles.

The policy source of truth is
`$CODEX_HOME/skills/adaptive-delegation/config/model-routing.defaults.json`.
Do not add a local routing-policy override.

Each managed file or directory is replaced atomically. The complete install is
not a single cross-directory transaction. If the process is interrupted, rerun
the installer from the same verified revision. Existing Codex-home directory
permissions and unrelated agent roles are preserved. An update removes only
obsolete adaptive roles declared by the previously installed package.

## Install on another PC

Use a fresh clone on the target computer. Do not copy the source computer's
Codex home or hidden runtime-state directories.

```sh
git clone https://github.com/ai-dev-methodologies/adaptive-delegation.git
cd adaptive-delegation
python3 scripts/install.py --dry-run
python3 -m unittest -v tests.test_install tests.test_dispatcher_gate
python3 -m unittest discover -v -s adaptive-delegation/tests -p 'test_*.py'
python3 scripts/install.py
```

Authenticate Codex locally on that computer. Its audit and continuity ledgers
must start locally; they are not installation assets.

## Update or reinstall

```sh
git pull --ff-only
python3 scripts/install.py --dry-run
python3 -m unittest -v tests.test_install tests.test_dispatcher_gate
python3 -m unittest discover -v -s adaptive-delegation/tests -p 'test_*.py'
python3 scripts/install.py
```

Rerunning the installer is the supported repair and reinstall path.

## Roll back

Check out a known-good commit, or a known-good tag when one exists, then rerun
the same dry run, tests, and installer:

```sh
git checkout <known-good-commit-or-tag>
python3 scripts/install.py --dry-run
python3 -m unittest -v tests.test_install tests.test_dispatcher_gate
python3 -m unittest discover -v -s adaptive-delegation/tests -p 'test_*.py'
python3 scripts/install.py
```

Return to the desired branch or revision and repeat those steps to move
forward again.

## Privacy and local state

Never copy, commit, attach, or publish:

- `$CODEX_HOME/auth.json` or other credentials;
- `$CODEX_HOME/state/model-routing/attempts.jsonl`;
- `$CODEX_HOME/state/model-routing/reviews/`;
- `$CODEX_HOME/state/adaptive-delegation/continuity.jsonl`;
- Codex rollout or session records; or
- repository-local hidden runtime-state directories.

The repository `.gitignore` excludes those local state directories, but a raw
filesystem copy can still include them. Prefer `git clone`; if an archive is
required, inspect it before transfer.

To report routing behavior, generate and manually inspect a sanitized summary
as described in [`REPORTING.md`](REPORTING.md). Never upload a raw ledger.

## Skill visibility

Codex normally detects skill changes automatically. Restart the Codex process
only when the installed update is not visible.
