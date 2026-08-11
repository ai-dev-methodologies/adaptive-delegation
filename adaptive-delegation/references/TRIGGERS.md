# Trigger Examples

This file documents intended activation boundaries for the
`adaptive-delegation` skill. Activation is explicit and opt-in: the current
request must begin with `$adaptive-delegation`. The skill is Codex-only and
routes Codex native subagents.

## Positive explicit examples

- `$adaptive-delegation: route this bounded implementation with evidence.`
- `$adaptive-delegation validate model selection and report the audit trail.`
- `$adaptive-delegation use token-efficient delegation for the independent check.`
- `$adaptive-delegation apply Luna-first delegation with effort-first escalation.`
- `$adaptive-delegation: continue the preceding task; scope: update the bounded parser and run its targeted tests.`

The final form is the safe mid-conversation opt-in. The directive need not be
present in the conversation's first message; it must begin the later request
that activates the controller. Restating the bounded scope avoids deriving a
new Objective Lock from ambiguous earlier discussion.

## Discovery phrases that do not activate the skill

- "Use cost-efficient subagents for this bounded transformation and preserve evidence."
- "Can you perform a model routing audit and reduce Sol usage where the oracle is strong?"
- "Please use adaptive delegation for this bounded verification task."

These phrases help users discover the skill but remain scoped main-direct work
unless the user invokes `$adaptive-delegation`.

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
