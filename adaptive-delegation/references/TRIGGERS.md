# Trigger Examples

This file documents intended activation boundaries for the
`adaptive-delegation` skill. Activation is explicit and opt-in, but the request
does not need to begin with a command. The Sol/high-or-above main interprets an
actionable request anywhere in the current turn and explicitly starts the
controller. The skill is Codex-only and routes Codex native subagents.

## Positive actionable examples

- `$adaptive-delegation: route this bounded implementation with evidence.`
- `$adaptive-delegation validate model selection and report the audit trail.`
- `$adaptive-delegation use token-efficient delegation for the independent check.`
- `$adaptive-delegation apply Luna-first delegation with effort-first escalation.`
- `$adaptive-delegation: continue the preceding task; scope: update the bounded parser and run its targeted tests.`
- `Continue the current task and use adaptive-delegation for the independent implementation slices.`
- `For the remaining review, apply adaptive-delegation and report model cost evidence.`

All forms are valid mid-conversation opt-ins. The `$` directive is a
deterministic shortcut, while natural prose is activated only after the main
judges that it is an actionable request. Restating the bounded scope remains
useful but is not a syntactic requirement.

## Actionable natural-language requests

- "Use adaptive-delegation for this bounded transformation and preserve evidence."
- "Please apply adaptive-delegation to the remaining verification task."

These activate after main judgment. Generic cost-efficiency vocabulary without
the capability name remains discovery-only.

## Localized discovery vocabulary

Localized vocabulary is declared in the skill frontmatter for discovery only.
It does not activate the controller. Keep this reference file in English so it
remains portable across environments.

## Negative boundaries

- "What is the definition of token efficiency?" — explanation only; no routing request.
- "Translate the phrase `Luna-first delegation`." — translation only; no delegation request.
- "Show a generic example of a model routing audit." — generic reference material only.
- "Run this entire repository audit with unrestricted parallel agents." — does not request bounded adaptive delegation and conflicts with scope control.
- "Change the parent model or global Codex configuration automatically." — outside this skill's authority; the skill cannot mutate the parent model.
- Any product bug fix without the explicit skill token — scoped main-direct behavior remains active.
