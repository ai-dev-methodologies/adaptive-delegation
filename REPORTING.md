# Privacy-safe, duplicate-aware issue reporting

`adaptive-delegation` is a Codex skill for Codex native subagents. Local
routing history can improve the skill through GitHub issues, but raw runtime
state must remain on the computer that created it.

For prompt-driven publication, send Codex the packaged
[`CODEX-ISSUE-REPORT-PROMPT.md`](adaptive-delegation/references/CODEX-ISSUE-REPORT-PROMPT.md).
It authorizes at most one canonical issue, checks GitHub for the exact Report
ID before creation, and records the returned issue URL locally.

## Local state and duplicate boundary

The workflow keeps two separate owner-only files under the resolved Codex
runtime home:

- `state/model-routing/attempts.jsonl` is the raw append-only routing ledger.
  The reporter only reads it.
- `state/model-routing/issue-report-state.jsonl` is the issue management point.
  It records prepared random Report IDs, local-only SHA-256 attempt
  fingerprints, report-body digests, and submitted canonical issue URLs.

The issue state contains no raw task or attempt identifier. Once a Report ID is
recorded as submitted, later reports exclude its attempt fingerprints. A
pending report keeps the same random Report ID across retries, so Codex can
find an issue created before a local receipt failure instead of publishing a
duplicate. The installer does not overwrite either file.

Preserve the issue state on its originating computer, but never copy it into
this repository or upload it. Deleting it removes the local duplicate memory.

## Manual workflow

1. Resolve the runtime home and prepare one report:

   ```sh
   RUNTIME_HOME="${CODEX_HOME:-$HOME/.codex}"
   export RUNTIME_HOME
   python3 "$RUNTIME_HOME/skills/adaptive-delegation/scripts/model_routing_audit.py" issue-report
   ```

   The command selects the latest pending report first; otherwise it selects
   the latest completed task that has unsubmitted attempt history. To select a
   different completed task, add `--task-id TASK_ID` only when that identifier
   is safe to place in local shell history. The identifier is never included
   in the report or issue state.

2. Inspect the allowlisted Markdown. It contains a random `adr1-*` Report ID,
   route outcomes, and no task/session identifier, path, prompt, evidence text,
   command, credential, or private URL. If the formatter rejects the input,
   stop; never bypass it by copying ledger lines.

3. Before issue creation, inspect all issue pages in
   `ai-dev-methodologies/adaptive-delegation` for the exact Report ID marker.
   Use the GitHub API rather than relying only on indexed search. If the marker
   exists, reuse that issue URL. Otherwise create exactly one issue from the
   [routing report template](.github/ISSUE_TEMPLATE/routing-report.md), keeping
   the Report ID in the body.

4. After GitHub returns a canonical issue URL, record it locally:

   ```sh
   python3 "$RUNTIME_HOME/skills/adaptive-delegation/scripts/model_routing_audit.py" \
     record-submission \
     --report-id 'adr1-REPLACE_WITH_REPORT_ID' \
     --issue-url 'https://github.com/ai-dev-methodologies/adaptive-delegation/issues/123'
   ```

   Repeating the exact command is idempotent. A different URL for the same
   Report ID fails closed. If publication succeeds but receipt recording
   fails, search for the Report ID and retry this command; do not create
   another issue.

5. On a later request, run `issue-report` normally. It will return the next
   pending or unsubmitted history, or report that no unsubmitted completed task
   remains. It never resends fingerprints covered by a submitted receipt.

Never upload or paste `attempts.jsonl`, `issue-report-state.jsonl`, review
files, continuity records, rollout/session files, prompts, credentials, tokens,
secrets, or raw logs. Do not paste workspace paths, evidence paths, URLs with
credentials/query/fragment data, or proprietary payloads.

## What maintainers can use

The public report includes a random duplicate-recovery ID, route models and
efforts, completion status, failure class, escalation counts, and compact
oracle or route-assessment enums when present. It contains no deterministic
digest of a task identifier. These fields support routing-policy discussion
without transferring local execution state.
