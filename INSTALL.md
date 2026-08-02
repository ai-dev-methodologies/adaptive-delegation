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

## Prompt-driven installation

To delegate the complete install or update to Codex CLI, send the target
developer the prompt in [`CODEX-INSTALL-PROMPT.md`](CODEX-INSTALL-PROMPT.md).
It uses Git and Python directly, compares the installed and source versions,
and contains explicit authorization for the final user-level write only after
the promotion gate passes.

## Version status

The installed skill contains the canonical Semantic Version from
`adaptive-delegation/VERSION`. Before and after installation, compare the
checkout with the target Codex home:

```sh
python3 scripts/version_status.py --codex-home /path/to/.codex
```

The read-only command reports the source and installed versions, package
digests, changed relative paths, and a status such as `not_installed`,
`update_available`, `current`, `same_version_drift`, or
`installed_unversioned`. Read [`CHANGELOG.md`](CHANGELOG.md) for the
human-readable changes between versions.

## First installation

Clone the repository, validate the package without writing, run the portable
tests, then run the mandatory isolated promotion gate. Only after that gate
passes and the user explicitly approves may this workflow write to the user
Codex home:

```sh
git clone https://github.com/ai-dev-methodologies/adaptive-delegation.git
cd adaptive-delegation
python3 scripts/install.py --dry-run
python3 -m unittest -v tests.test_install tests.test_dispatcher_gate tests.test_version_status
python3 -m unittest discover -v -s adaptive-delegation/tests -p 'test_*.py'
python3 -m unittest -v tests.test_isolated_dogfood
python3 scripts/verify_isolated_dogfood.py --auth-source /path/to/read-only-auth.json
# With explicit user approval only:
python3 scripts/install.py
python3 scripts/version_status.py
```

For a non-default Codex home:

```sh
python3 scripts/install.py --codex-home /path/to/.codex
```

The dry run validates package completeness, Python source, and every
policy-to-role model/effort binding without changing the target.

## Mandatory isolated promotion gate

`scripts/verify_isolated_dogfood.py` is a Python 3.11 stdlib-only gate for
current POSIX macOS/Linux environments. It creates a temporary candidate
`CODEX_HOME` and a separate temporary Git fixture, installs only into that
candidate, and starts a fresh `codex exec --ephemeral --json` session with an
objective lock limiting the task to `target.py`.

The auth source is read only: the gate exposes it to the temporary candidate
through a temporary symlink and never copies or changes credentials. The gate
checks that only `target.py` changes, `.strip().lower()` is present, the exact
targeted unittest passes, an adjacent intentional failure remains unchanged
and failing, the fresh command exits zero, its output does not reference the
user Codex home, and before/after fingerprints of managed user files/state
match. Artifacts are removed by default; use `--keep-artifacts` only to retain
a failed fixture and its owner-only `fresh-output.jsonl` for local
investigation. Treat that output as private session evidence and never publish
it.

This is a same-user release-quality guard, not a security boundary. It never
installs globally or creates a global canary. User-level installation is a
separate, later approval step.

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
python3 -m unittest -v tests.test_install tests.test_dispatcher_gate tests.test_version_status
python3 -m unittest discover -v -s adaptive-delegation/tests -p 'test_*.py'
python3 scripts/verify_isolated_dogfood.py --auth-source /path/to/read-only-auth.json
# With explicit user approval only:
python3 scripts/install.py
python3 scripts/version_status.py
```

Authenticate Codex locally on that computer. Its audit and continuity ledgers
must start locally; they are not installation assets.

## Update or reinstall

Before updating, finalize every pending attempt created by the installed
terminal/receipt/audit schema. The v2/`0.3.0` cutover intentionally does not
finalize or backfill pending v1/`0.2.0` chains. If one remains after updating,
preserve it as historical evidence and re-execute the bounded work with a new
task ID, attempt index 1, dispatch ID, packet, and v2/`0.3.0` chain.

Package 0.5.0 changes the policy fingerprint and adds a quota-first,
latency-insensitive goal route: Luna max -> Terra xhigh -> Terra max -> Sol
high. The existing latency-sensitive Terra medium/high route remains. Finalize pending older
attempts before updating. If an attempt remains pending, preserve it as
historical evidence and restart the bounded work with a new task ID, attempt
index 1, dispatch ID, and packet after installing 0.5.0. Packets now require
an explicit `terminal_outcome` and `lane_id`; Objective Lock v3 carries the stable terminal
outcome/authority layer while method/data source/stage/test plan move to a
replaceable path/iteration envelope. Cross-policy continuation still fails
closed. Terra `xhigh`/`max` are restricted to the quota-first goal route after
observable Luna failure; ordinary Terra use is passively logged by `use_mode`
and compared by accepted-task outcomes without paired A/B.

```sh
git pull --ff-only
python3 scripts/version_status.py
python3 scripts/install.py --dry-run
python3 -m unittest -v tests.test_install tests.test_dispatcher_gate tests.test_version_status
python3 -m unittest discover -v -s adaptive-delegation/tests -p 'test_*.py'
python3 scripts/verify_isolated_dogfood.py --auth-source /path/to/read-only-auth.json
# With explicit user approval only:
python3 scripts/install.py
python3 scripts/version_status.py
```

Rerunning the installer is the supported repair and reinstall path.

## Roll back

Check out a known-good commit, or a known-good tag when one exists, then rerun
the same dry run, tests, and installer:

```sh
git checkout <known-good-commit-or-tag>
python3 scripts/install.py --dry-run
python3 -m unittest -v tests.test_install tests.test_dispatcher_gate tests.test_version_status
python3 -m unittest discover -v -s adaptive-delegation/tests -p 'test_*.py'
python3 scripts/verify_isolated_dogfood.py --auth-source /path/to/read-only-auth.json
# With explicit user approval only:
python3 scripts/install.py
python3 scripts/version_status.py
```

Return to the desired branch or revision and repeat those steps to move
forward again.

An older installer cannot know role names introduced by a newer revision.
After installing an older revision, compare
`$CODEX_HOME/agents/adaptive-*.toml` with that revision's
`adaptive-delegation/config/model-routing.defaults.json` `role_bindings`, and
remove only adaptive role files that the installed revision does not declare.

## Privacy and local state

Never copy, commit, attach, or publish:

- `$CODEX_HOME/auth.json` or other credentials;
- `$CODEX_HOME/state/model-routing/attempts.jsonl`;
- `$CODEX_HOME/state/model-routing/reviews/`;
- `$CODEX_HOME/state/adaptive-delegation/continuity.jsonl`;
- `$CODEX_HOME/state/adaptive-delegation/dispatch_attestation.jsonl`;
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
