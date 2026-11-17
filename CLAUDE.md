@AGENTS.md

## Working rules for this port

Lessons from retros. Each rule says what went wrong without it.

- **Test a setting or a model before a decision depends on it.** Before a decision fixes an API setting or names a model, build the request with the installed Inspect, without calling the API, and check the provider's current model list for retirements. Write what was checked into the decision.
  - Why: on 2026-11-16 an approved decision set `reasoning_tokens` in the task, which Inspect refuses on Claude 4.7 and later, and the plan named two Claude models that had been retired for months. Neither had been tried. Both were found only when the provider code was read for a later task.
