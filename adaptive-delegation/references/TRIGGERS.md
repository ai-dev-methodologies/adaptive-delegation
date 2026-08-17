# Trigger Examples

This file documents intended activation boundaries for the
`adaptive-delegation` skill. Activation is explicit and opt-in: the current
prompt must begin with `$adaptive-delegation`. Codex loads it through the normal
skill mechanism; the package installs and requires no hook. The skill is
Codex-only and routes Codex native subagents.

## Positive actionable examples

- `$adaptive-delegation: route this bounded implementation with evidence.`
- `$adaptive-delegation validate model selection and report the audit trail.`
- `$adaptive-delegation use token-efficient delegation for the independent check.`
- `$adaptive-delegation apply Luna-first delegation with effort-first escalation.`
- `$adaptive-delegation: continue the preceding task; scope: update the bounded parser and run its targeted tests.`
- `$adaptive-delegation continue the current task with bounded implementation slices.`

Only the prefix form activates. Restating the bounded scope remains useful.

## Actionable natural-language requests

- "Use adaptive-delegation for this bounded transformation and preserve evidence."
- "Please apply adaptive-delegation to the remaining verification task."

These do not activate; reinvoke with the prefix. Generic cost-efficiency
vocabulary without the capability name remains discovery-only.

## Localized discovery vocabulary

Localized vocabulary is declared in the skill frontmatter for discovery only.
It does not activate the skill. Keep this reference file in English so it
remains portable across environments.

## Negative boundaries

- "What is the definition of token efficiency?" — explanation only; no routing request.
- "Translate the phrase `Luna-first delegation`." — translation only; no delegation request.
- "Show a generic example of a model routing audit." — generic reference material only.
- "Run this entire repository audit with unrestricted parallel agents." — does not request bounded adaptive delegation and conflicts with scope control.
- "Change the parent model or global Codex configuration automatically." — outside this skill's authority; the skill cannot mutate the parent model.
- Any product bug fix without the explicit skill token — scoped main-direct behavior remains active.
