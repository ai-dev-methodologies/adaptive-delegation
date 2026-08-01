# Privacy-safe issue reporting

`adaptive-delegation` is a Codex skill for Codex native subagents. The issue
report command is a local formatter only: it never publishes an issue, opens a
network connection, or changes the ledger.

## Safe workflow

1. Generate the report locally from the validated attempts ledger. From a
   clone of this repository, run:

   ```sh
   python3 adaptive-delegation/scripts/model_routing_audit.py issue-report
   ```

   The command honors `$CODEX_HOME`, selects the latest completed task, and
   prints sanitized Markdown to standard output. To select a different completed
   task, add `--task-id TASK_ID` only when that identifier is safe to place in
   local shell history. The identifier is never included in the report.

2. Inspect the output manually. It contains only allowlisted routing outcomes.
   Remove anything that identifies a private project or user before sharing.
   If the command rejects the ledger, stop and investigate locally; do not
   bypass validation by pasting ledger lines.

3. Paste only the inspected, sanitized Markdown output into a new GitHub issue.
   Open the [routing report issue template](https://github.com/ai-dev-methodologies/adaptive-delegation/issues/new?template=routing-report.md),
   or inspect the repository's
   [routing report template](.github/ISSUE_TEMPLATE/routing-report.md), and
   complete its consent checkboxes.

4. Add the expected behavior and actual behavior in your own words. Include
   only the package version or commit and the sanitized report. Do not attach
   local files.

Never upload or paste `attempts.jsonl`, review files, continuity records,
rollout/session files, prompts, credentials, tokens, secrets, or raw logs.
Do not paste workspace paths, evidence paths, URLs containing credentials or
query/fragment data, or proprietary payloads. If any such value appears in a
report, discard it and report the formatter defect without sharing the value.

`issue-report` is read-only: it never creates a missing ledger or parent
directory. Validation failures use a generic local error and do not echo ledger
values, identifiers, or filesystem paths.

## What maintainers can use

The report intentionally contains no task identifier or deterministic digest of
one. It includes route models and efforts, completion status, failure class,
escalation counts, and (when present) compact oracle and route-assessment enums.
These fields are enough to discuss routing behavior without transferring local
state.
