# Brainstorm — AI AP Operations Manager

> This is the inbox. Raw ideas go here; once processed into GOALS/TODO they get cleared.

## Unprocessed Ideas

<!-- Add raw ideas here as they come. Mark with [AI] if AI-suggested. -->

[AI] Consider a "confidence score" on every LLM extraction field — low-confidence fields
     get highlighted in the analyst workbench for mandatory human review rather than
     silently passing through. This prevents silent extraction errors becoming match errors.

[AI] The duplicate invoice detection strategy should handle cross-currency duplicates
     (same invoice submitted in USD and EUR by vendor). Store normalized amount in base
     currency for comparison.

[AI] For the rule version system, consider a "shadow mode" before publishing a new rule:
     run new rule in parallel with old rule for 2 weeks, compare outcomes, then decide
     whether to promote. This reduces risk of a bad rule polluting production.

[AI] Vendor onboarding flow: when a new vendor submits their first invoice, system should
     flag it for enhanced review regardless of match outcome (fraud prevention).
