# Local logging and monitoring

Adaptive Delegation is hook-free. Normal explicit skill activation creates no
controller state and requires no monitor. Observe only artifacts produced by a
native child or by an optional dispatcher/audit helper that the active task
explicitly uses.

## Data boundaries

Resolve the runtime home from `CODEX_HOME`, otherwise `~/.codex`.

| Artifact | Meaning | Handling |
| --- | --- | --- |
| `$RUNTIME_HOME/state/model-routing/attempts.jsonl` | Optional dispatcher attempt history | Keep local; use aggregate tooling |
| `$RUNTIME_HOME/state/model-routing/reviews/` | Optional cumulative routing reviews | Read the latest applicable snapshot |
| `$RUNTIME_HOME/state/adaptive-delegation/` | Optional dispatcher, receipt, or continuity state | Keep local; never publish raw files |
| `$RUNTIME_HOME/sessions/**` | Codex-owned conversation and tool history | Private host data, not acceptance evidence |
| Project working tree | Actual authorized implementation | Verify under the project contract |

Historical `$RUNTIME_HOME/state/adaptive-delegation/controller/` records from
hook-based releases may remain readable by aggregate health tooling. Their
presence does not indicate that the current package installed or activated a
hook, and new explicit activation must not require them.

## Read-only health

Use the packaged aggregate command only when routing evidence exists:

```sh
python3 adaptive-delegation/scripts/model_routing_audit.py health
```

The command must not create, append, repair, backfill, or finalize state.
Missing optional review, continuity, dispatch, or historical-controller sources
may produce `partial`; malformed required sources produce `degraded`. Never
print raw prompts, task/session identifiers, local paths, or ledger lines.

## Temporary monitoring

A bounded monitor may confirm:

1. the expected native `adaptive-*` child was created;
2. its role/model/effort match the selected fixed binding;
3. the child returned the declared acceptance evidence; and
4. an optional dispatcher attempt closed only after integration acceptance.

Monitoring is read-only and ephemeral. It must not create a daemon, schedule,
hook, polling configuration, retry, child, issue, or routing record. Stop when
the declared observation passes or the bounded window expires.

## Interpretation

- Child-process success is not integration acceptance.
- No dispatcher `pre_decision` is expected for normal direct native routing.
- `pre_decision` without a result is pending, not accepted.
- Missing token measurement is unavailable, never observed zero.
- Continuity is optional and reuse-driven; its absence is not a failure.
- A foreign host hook failure is path-local evidence. Do not mutate that host's
  phase or state as an adaptive recovery step.

## Privacy and publication

Do not commit or publish runtime state, credentials, Codex rollouts, prompts,
transcripts, or raw evidence. Use the allowlisted formatter in
[`../REPORTING.md`](../REPORTING.md) for public reports and record every
submitted Report ID so already-covered fingerprints are excluded.

See [`DELEGATION-FLOW.md`](DELEGATION-FLOW.md) for role ownership and evidence
flow.
