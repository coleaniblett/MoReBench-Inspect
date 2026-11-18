@AGENTS.md

## Working rules for this port

Lessons from retros. Each rule says what went wrong without it.

- **Test a setting or a model before a decision depends on it.** Before a decision fixes an API setting or names a model, build the request with the installed Inspect, without calling the API, and check the provider's current model list for retirements. Write what was checked into the decision.
  - Why: on 2026-11-16 an approved decision set `reasoning_tokens` in the task, which Inspect refuses on Claude 4.7 and later, and the plan named two Claude models that had been retired for months. Neither had been tried. Both were found only when the provider code was read for a later task.
- **Check a prediction about model behaviour against real output.** A spec entry that predicts how a model, judge or provider will behave either cites the real output that showed it, or says "unverified" and names the check that will confirm it. The first real run checks every unverified entry before a bigger run is started.
  - Why: on 2026-11-17 the T7 runs showed that D-03's approved prediction, that the judge would almost always answer `yes` or `no`, was false for thinking traces: 88% of the judge's trace replies were essays. Judging two of the previous day's probe traces with the real prompt would have shown it for pennies, before the scorer was built on it.

## How to bring things to the owner

These rules take precedence over the "Ask first" list in `SPEC.md` §10 and the "Stop and ask if" lines in `TASKS.md` where they conflict. Without them, the owner was asked to approve 18 decisions in one sitting on 2026-11-16 and approved them all as recommended; four were revised or contradicted within a day.

- **Decide it yourself** when a choice does not change scores, scope or spend, and follows an existing convention. List these under "Decided for you" at the end of your report, so the owner can veto them.
- **Ask** when a choice changes scores, what the eval measures, scope or spend, or cannot be undone. Ask one question at a time, when the answer is needed. Give the question in plain words, what it changes, the evidence, then your recommendation.
- **Never leave more than three items waiting on the owner.** If there are more, rank them and hold the rest.
- **Write plain words first** and put any ID (task, decision, requirement, golden case, lint rule) in brackets after.
