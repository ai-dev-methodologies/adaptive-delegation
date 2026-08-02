# Codex Installation and Update Prompt

This repository is installed and updated by Codex CLI through Git and Python;
it is not distributed through npm or another package registry.

Send the prompt below to a fresh Codex CLI session on the target computer. The
prompt explicitly authorizes installation into that developer's resolved Codex
home only after the isolated promotion gate passes. Replace `SOURCE_REF` when
an immutable tag or commit is required; `main` selects the current published
repository state.

```text
Install or update the Codex-only Adaptive Delegation skill from:
https://github.com/ai-dev-methodologies/adaptive-delegation.git

SOURCE_REF=main

I explicitly authorize installation into my resolved Codex home after every
required validation and the isolated promotion gate pass. Do not use npm,
Homebrew, or another package manager. Do not copy credentials, logs, audit
state, continuity state, or session data.

Execute this workflow to completion without asking about routine reversible
steps:

1. Clone the repository into a fresh temporary or dedicated checkout, or fetch
   and cleanly switch an existing canonical checkout to SOURCE_REF. Do not
   discard unrelated local changes; use a fresh checkout if the existing one is
   dirty. Record `git rev-parse HEAD` and use that resolved commit for the
   remainder of this installation.
2. Read README.md, INSTALL.md, CHANGELOG.md, and
   adaptive-delegation/VERSION before changing the Codex home.
3. Resolve the target Codex home from CODEX_HOME when set, otherwise use
   $HOME/.codex. In the shell run
   `TARGET_CODEX_HOME="${CODEX_HOME:-$HOME/.codex}"; export TARGET_CODEX_HOME`.
   Start with `AUTH_SOURCE=""`, then set
   `AUTH_SOURCE="$TARGET_CODEX_HOME/auth.json"` only if it is an existing
   readable file. Never print or read credential contents. If no readable auth
   source exists, stop before validation and report that local Codex
   authentication is required; do not install.
4. Run this read-only comparison first:
   python3 scripts/version_status.py --codex-home "$TARGET_CODEX_HOME"
   Report the source version, installed version, comparison status, and changed
   relative paths. If the installed version is older, summarize applicable
   CHANGELOG.md entries. If it is unversioned, say that the exact prior release
   cannot be identified and use the reported file differences.
5. Run the installer dry-run and required tests exactly:
   python3 scripts/install.py --codex-home "$TARGET_CODEX_HOME" --dry-run
   python3 -m unittest -v tests.test_install tests.test_dispatcher_gate tests.test_isolated_dogfood tests.test_version_status
   python3 -m unittest discover -v -s adaptive-delegation/tests -p 'test_*.py'
6. Run the mandatory isolated promotion gate with the target computer's
   existing Codex authentication file as a read-only auth source:
   python3 scripts/verify_isolated_dogfood.py --auth-source "$AUTH_SOURCE" --user-codex-home "$TARGET_CODEX_HOME"
   Never copy or display the authentication file. The gate must leave the
   target Codex home fingerprint unchanged.
7. If any validation or promotion check fails, do not install. Diagnose only
   within this repository and report the exact blocker.
8. After every check passes, install with:
   python3 scripts/install.py --codex-home "$TARGET_CODEX_HOME"
9. Run version_status.py again. Completion requires status=current, matching
   source and installed versions, matching package digests, a clean repository
   checkout, and no mutation of unrelated Codex roles or local state.
10. Report the installed version, source commit, target Codex home, validations
    run, and any required Codex restart. Do not include secrets or raw logs.

Stop when the verified installed package matches the requested source. Do not
modify unrelated projects, global policy files, or runtime state.
```

## Compare without installing

For a read-only update check, send this shorter prompt:

```text
Check whether my installed Codex-only Adaptive Delegation skill differs from
https://github.com/ai-dev-methodologies/adaptive-delegation.git at main.
Clone or fetch the repository without changing my Codex home, read CHANGELOG.md,
and run python3 scripts/version_status.py against my resolved Codex home. Report
source version, installed version, status, changed relative paths, and relevant
changelog entries. Do not install, modify, or delete anything.
```
