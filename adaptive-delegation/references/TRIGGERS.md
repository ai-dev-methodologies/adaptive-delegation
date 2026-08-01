# Trigger Examples

This file documents intended activation boundaries for the
`adaptive-delegation` skill. Explicit invocation is the deterministic choice;
implicit activation is permitted when the request clearly matches a positive
example.

## Positive explicit examples

- `$adaptive-delegation: route this bounded implementation with evidence.`
- `$adaptive-delegation validate model selection and report the audit trail.`
- `$adaptive-delegation use token-efficient delegation for the independent check.`
- `$adaptive-delegation apply Luna-first delegation with effort-first escalation.`

## Positive implicit English examples

- "Use cost-efficient subagents for this bounded transformation and preserve evidence."
- "Can you perform a model routing audit and reduce Sol usage where the oracle is strong?"
- "Choose evidence-attested delegation and take over in the main if the leaf fails."
- "I need token efficiency and a Luna-first route for this multi-step task."
- "Use token effective routing, including the token-effective retry ladder."
- "Please use adaptive delegation for this bounded verification task."

## Positive implicit localized triggers

The localized trigger literals are declared in the skill frontmatter. Keep
this reference file in English so it remains portable across environments.

## Negative boundaries

- "What is the definition of token efficiency?" — explanation only; no routing request.
- "Translate the phrase `Luna-first delegation`." — translation only; no delegation request.
- "Show a generic example of a model routing audit." — generic reference material only.
- "Run this entire repository audit with unrestricted parallel agents." — does not request bounded adaptive delegation and conflicts with scope control.
- "Change the parent model or global Codex configuration automatically." — outside this skill's authority; the skill cannot mutate the parent model.
- A product bug fix with no request for delegation, model selection, cost, evidence, or routing — direct implementation remains outside implicit activation.
