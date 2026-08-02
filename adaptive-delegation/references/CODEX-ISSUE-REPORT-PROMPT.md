# Codex prompt: publish one deduplicated feedback issue

Send the prompt below to Codex after using `adaptive-delegation` locally. It
authorizes one narrowly scoped public issue in the canonical repository. It
does not authorize uploading raw logs or changing the skill installation.

```text
Use the installed $adaptive-delegation issue-report workflow to turn my local
routing experience into at most one public GitHub issue in
ai-dev-methodologies/adaptive-delegation.

This request authorizes creation of exactly one issue only after all of the
following checks pass:

1. Resolve RUNTIME_HOME from CODEX_HOME, otherwise use ~/.codex. Run the
   installed model_routing_audit.py issue-report command. Do not read, print,
   summarize, attach, or upload attempts.jsonl or any other raw state file.
2. Use only the sanitizer's Markdown output. Confirm that it contains one
   adr1-* Report ID and no path, prompt, task/session identifier, credential,
   proprietary payload, or raw evidence. If validation fails, stop without
   creating or updating an issue.
3. Before creating anything, use GitHub CLI against the canonical repository
   and inspect all issue pages through the GitHub API for the exact Report ID
   marker. Do not rely only on indexed search.
4. If that Report ID already exists, create no issue. Use the existing issue
   URL in the local record-submission command instead.
5. If it does not exist, create exactly one issue. Keep the Report ID in the
   body, include only the sanitized report plus non-sensitive expected and
   actual behavior from this request, and use the routing-report template's
   consent language. Do not attach local files.
6. Only after GitHub returns the canonical issue URL, immediately run
   record-submission with that Report ID and URL. If this local receipt step
   fails, search for the same Report ID and retry the receipt; never create a
   replacement issue.
7. Re-run record-submission with the same values and require an idempotent
   success. Report the issue URL and receipt result. If issue-report says that
   no unsubmitted completed task remains, report that no new issue was needed.

Preserve the local issue-report-state.jsonl file across skill updates. Never
copy it into the repository or send it to GitHub. Future issue-report requests
must exclude attempt fingerprints already covered by submitted receipts.
```

The public Report ID is random and reusable while a report is pending. The
local state stores only that ID, public issue metadata, and SHA-256
fingerprints used for duplicate exclusion; it stores no raw task or attempt
identifier.
