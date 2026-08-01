# Token-Efficiency Continuity

Use `~/.codex/state/adaptive-delegation/continuity.jsonl` to carry
accepted decisions between sessions without reloading raw logs. Before routing,
read at most the latest 3 records matching workspace/objective_key; reuse
still-valid decisions/evidence paths and invalidate them only with newer direct
evidence. Each new record includes a complete carry_forward snapshot, so older
raw logs are unnecessary.

At acceptance or handoff, exactly one designated recorder appends one record:
the independent Checker when present, else sole verified executor. Never use
multiple writers for one record. The ledger is append only; corrections append
a new record with supersedes and never rewrite accepted history. No duplicate
record_id or objective+fingerprint result is permitted.

Every UTF-8 JSON line <=4096 bytes has these required fields:
schema_version, record_id, recorded_at, status, workspace, objective_key,
source_fingerprint, implementation_envelope, decisions, changes, routing,
verification, evidence_paths, side_effects, carry_forward, next_action,
stop_condition, supersedes. Decisions contain decision/rationale/alternatives;
changes contain path/summary. Evidence is paths/compact results only: never
store full prompts, raw logs, transcript bodies, credentials, tokens, secrets, private data.

One-line template (compact values are illustrative):
`{"schema_version":1,"record_id":"id","recorded_at":"time","status":"accepted","workspace":"/w","objective_key":"k","source_fingerprint":"f","implementation_envelope":{},"decisions":[{"decision":"d","rationale":"r","alternatives":[]}],"changes":[{"path":"p","summary":"s"}],"routing":{},"verification":{},"evidence_paths":[],"side_effects":[],"carry_forward":{},"next_action":"n","stop_condition":"s","supersedes":null}`

token_budget is optional/advisory: its absence never makes Native V2 ineligible
and never triggers external rerouting. Only explicitly hard-cap-required
objectives use the typed external path; Native V2 remains the default.

For Native Luna, record the selected fixed `agent_type`, its verified installed
model/effort binding, the matching effort argument, and `fork_turns="none"`.
Absence of Luna from an optional model-override enum is not a rejection when
that fixed role is available. Record typed direct only after the role/surface
is unavailable or rejected, runtime evidence mismatches, or a hard cap requires
the parent-monitored path.

Future model-selection validation requests automatically read
`~/.codex/state/model-routing/attempts.jsonl` and the latest reviews under
`~/.codex/state/model-routing/reviews/` in addition to the latest three
relevant continuity records. Use those records as compact evidence and do not
reload unrelated raw logs. Never store prompt payloads, transcript payloads,
credential payloads, or their raw contents in the continuity ledger, attempt
ledger, or review artifacts; retain only compact decisions, outcomes, and
evidence paths.

For a Native admission rejection, `routing` persists the fallback scope as
`surface_identity + schema_fingerprint`, including `child_count=0` and
`child_tokens=0`; re-evaluate that fallback when the schema fingerprint
changes. For integration, persist only the allowlisted receipt outcome: exact
`desired=explicit=effective` role/model/effort, trusted rollout session id,
launch-bound role config, successful finish, independent Checker pass, sha256
evidence digest, and truthful token observation. Completion alone never
integrates; missing or mismatched proof remains blocked. Native quantitative
caps are unavailable/advisory without trusted live parent monitoring, and the
typed direct path records `parent_enforced` or `quantitative_caps_enforced`
only when that monitoring proves them. Network remains off unless explicitly
requested.
