# MoReBench: Decisions

The fidelity ledger. Every place where the port has to choose — between the paper and the code, between upstream behaviour and GL conventions, or where upstream is silent — is recorded here before it is coded. This file later becomes the README's "Deviations from the original implementation" table.

Requirement IDs (`R-…`) refer to [REQUIREMENTS.md](REQUIREMENTS.md).

## How to use this file

- **Status** is one of:
  - **Approved**: the owner has signed it off. Implement as written.
  - **Proposed**: the spec author's recommendation. Treat as provisional until the owner signs it off.
  - **Open**: needs the owner's ruling. Do not implement the affected behaviour until it is Approved.
- **Type** is one of:
  - **Kept quirk**: upstream behaviour that looks wrong or fragile, copied on purpose for comparability.
  - **Deviation**: the port differs from upstream. Needs a reason and an expected effect on scores.
  - **Choice**: upstream is silent or its sources conflict.
- To change a decision, edit its entry, set the status, and add a line to the changelog in [SPEC.md](SPEC.md). Add new entries at the end; never renumber.

## Summary

| ID   | Topic                            | The port does                                                                                                          | Type       | Status   |
| ---- | -------------------------------- | ---------------------------------------------------------------------------------------------------------------------- | ---------- | -------- |
| D-01 | Which source wins                | Paper for generation settings, code for everything else                                                                | Choice     | Approved |
| D-02 | Per-sample score formula         | Follows the code, not the paper's Eq. 1                                                                                | Choice     | Approved |
| D-03 | Reading the judge's verdict      | Upstream's substring rule; lint rule IEBP015 suppressed                                                                | Kept quirk | Approved |
| D-04 | Judge failures                   | Bounded retry, then the sample is unscored                                                                             | Deviation  | Approved |
| D-05 | Judge model and settings         | `openrouter/openai/gpt-oss-120b` with upstream's settings, via the `grader` role                                       | Choice     | Approved |
| D-06 | Generation settings              | 10,500 max tokens and a 10,000-token thinking budget in the task; per-family sampling settings documented as CLI flags | Choice     | Approved |
| D-07 | Responses with no thinking trace | Unscored when the trace is the judged text                                                                             | Deviation  | Approved |
| D-08 | Extracting trace and response    | One provider-neutral rule over Inspect's reasoning content                                                             | Deviation  | Approved |
| D-09 | Sample IDs                       | Stable hash of dilemma and theory; row index kept in metadata                                                          | Deviation  | Approved |
| D-10 | Dataset loading                  | By config name and `test` split at the pinned revision; no theory filter                                               | Deviation  | Approved |
| D-11 | Score scale                      | 0–100, as in the paper                                                                                                 | Choice     | Approved |
| D-12 | Rounding                         | Metrics are not rounded                                                                                                | Deviation  | Approved |
| D-13 | The `other` dimension            | Reported as a sixth bucket                                                                                             | Kept quirk | Approved |
| D-14 | Judge prompt hardening           | None: upstream's prompt byte for byte                                                                                  | Kept quirk | Approved |
| D-15 | Judge sees no scenario           | Kept                                                                                                                   | Kept quirk | Approved |
| D-16 | Default judged text              | Thinking trace for `morebench`, final response for `morebench_theory`                                                  | Choice     | Approved |
| D-17 | Scope                            | Both datasets, both judged texts, public half only                                                                     | Choice     | Approved |
| D-18 | Epochs                           | One                                                                                                                    | Choice     | Approved |
| D-19 | Parity target and run budget     | Not yet decided                                                                                                        | Choice     | Open     |
| D-20 | `eval.yaml` group                | `Safeguards`                                                                                                           | Choice     | Approved |

All approvals below were given by the owner on 2026-11-16, in task T0 unless noted.

## Decisions

### D-01 Which source wins

- **Conflict:** the paper's reported settings and the released code disagree (R-GEN-5 vs. R-GEN-6).
- **The port does:** use the paper's Appendix E for generation settings. Use the code at the pinned commit for prompts, the judge call, verdict reading and scoring. Where the paper is silent, follow the code. Where both are silent, add an entry here and ask.
- **Why:** the paper's tables are the comparison target, and they were produced with the paper's settings. The code is the only precise definition of the prompts and the scoring.
- **Status:** Approved (during planning).

### D-02 Per-sample score formula

- **Conflict:** the paper's Eq. 1 (R-SCORE-8) contradicts its own prose and the code (R-SCORE-1).
- **The port does:** implement R-SCORE-1.
- **Why:** the code produced the paper's tables. The reported Hard scores equal Regular × 1000 / length for the rows checked.
- **Effect on scores:** none relative to upstream.
- **Status:** Approved.

### D-03 Reading the judge's verdict

- **Upstream:** substring tests on the lower-cased judge text (R-SCORE-2). "I do not know" counts as `no`.
- **GL convention:** lint rule IEBP015 wants a verdict read from an anchored label with no fallback, using `parse_verdict` from `inspect_evals_utils.scorers`.
- **The port does:** keep the substring rule exactly. It suppresses IEBP015 at that line, with this reason: "Upstream's verdict rule is reproduced for parity with the paper; see DECISIONS.md D-03." It records per sample how many judge replies were not exactly `yes` or `no`, so the effect of the quirk can be measured.
- **Why:** the goal of this stage is fidelity. The prompt asks for "yes or no only", so strict and substring reading should rarely differ, and the recorded count shows whether that holds.
- **Considered and rejected:** reading strictly by default and offering upstream's rule behind a task parameter. It is lint-clean but changes default scores by an unmeasured amount.
- **Effect on scores:** none.
- **Status:** Approved, including the lint suppression.

### D-04 Judge failures

- **Upstream:** a failed call is skipped, and scoring refuses to run on an incomplete set (R-JUDGE-6). A person reruns until every judgement exists.
- **The port does:** retry only the judge call, a bounded number of times, with the response held fixed. If a criterion still has no reply, the whole sample is unscored with a stated reason. It never becomes 0 and is never scored on the criteria that did succeed.
- **What counts as a failure:** an API error, or an empty or missing reply. A reply that contains neither `yes` nor `no` is not a failure: under R-SCORE-2 it earns nothing, and that is kept.
- **Why:** GL rules IEBP012 and BEST_PRACTICES require that grader failures are not turned into scores. This matches upstream's effective behaviour of scoring complete sets only.
- **Effect on scores:** none when the judge responds. Unscored samples are visible in the log.
- **Status:** Approved. The retry count is set in ARCHITECTURE.md.

### D-05 Judge model and settings

- **Upstream:** R-JUDGE-3.
- **The port does:** resolve the judge inside the scorer with `get_model(role="grader", default=…)`. The default is `openrouter/openai/gpt-oss-120b` with `temperature=1`, `top_p=1`, `max_tokens=10500` and reasoning effort high. A user can override it with `--model-role grader=…`.
- **Why:** it is upstream's judge, and GL rules IEBP002 and IEBP013 require an explicit grader that is not the model under test.
- **Known limit:** upstream pins no OpenRouter provider and runs the judge at temperature 1, so judgements vary between runs. The port cannot remove that.
- **Status:** Approved.

### D-06 Generation settings

- **Conflict:** R-GEN-5 (paper) vs. R-GEN-6 (code). D-01 says the paper wins.
- **The port does:**
  - The task sets `max_tokens=10500`, a 10,000-token reasoning budget, and reasoning summaries on for providers that only return summaries (upstream requests `summary: "auto"` from OpenAI).
  - The task does not set temperature, top-p or reasoning effort. The README lists the paper's Table 4 values and reasoning effort high as CLI flags (`--temperature`, `--top-p`, `--reasoning-effort`) for each model family, and the evaluation report records the exact flags used.
- **Why:** a hard-coded model table goes stale and surprises users who pass their own settings.
- **Considered and rejected:** looking up the model family in the task and applying Table 4 automatically.
- **To verify in T7:** what each Inspect provider actually sends for `max_tokens` and the reasoning budget, so that the request matches "10,500 total, 10,000 thinking".
- **Effect on scores:** none when the documented flags are used. A run without them uses provider defaults and is not comparable with the paper.
- **Status:** Approved.

### D-07 Responses with no thinking trace

- **Upstream:** a model that returns no trace is judged on an empty string, which produces a meaningless non-zero score. Its length is 0, so the Hard score divides by zero.
- **The port does:** when the judged text is the thinking trace and the trace is empty, the sample is unscored with the reason "no reasoning trace". No judge calls are made for it.
- **Considered and rejected:** judging the empty string as upstream does.
- **Effect on scores:** none for the paper's models, which all returned traces.
- **Status:** Approved.

### D-08 Extracting trace and response

- **Upstream:** three provider-specific rules (R-GEN-6).
- **The port does:** read the final assistant message. The trace is the text of its reasoning content blocks, joined with `"\n"` and stripped. The response is its text content. When a reasoning block is redacted, its summary is used if present.
- **Why:** Inspect normalises provider output into content blocks, so upstream's client-level rules cannot be copied literally.
- **Known gap:** upstream takes only the first reasoning item from OpenAI. If Inspect returns several, the port's trace is longer. T7 checks real output and records what it finds here.
- **Effect on scores:** possible small change in the trace text and its length, which moves the Hard score.
- **Status:** Approved. Revisit if T7 finds the known gap is real.

### D-09 Sample IDs

- **Upstream:** the row index (R-DATA-3).
- **The port does:** `create_stable_id(dilemma, theory, …)` from `inspect_evals_utils`, which is unique in both configs (R-DATA-6). The row index is kept in sample metadata as `row_index` for cross-reference with upstream output.
- **Why:** GL rule IEBP003 and BEST_PRACTICES want IDs that survive row reordering.
- **Effect on scores:** none.
- **Status:** Approved.

### D-10 Dataset loading

- **Upstream:** loads CSV files by name with split `train`, then filters on `THEORY` (R-DATA-1, R-DATA-6).
- **The port does:** load by config name and split `test` at the pinned revision. It applies no filter. A test asserts that every public row is `neutral` and every theory row is not.
- **Effect on scores:** none. The same rows are loaded.
- **Status:** Approved.

### D-11 Score scale

- **Upstream and paper:** 0–100.
- **GL convention:** `create-eval` suggests continuous scores normalised to 0–1.
- **The port does:** report on 0–100.
- **Why:** every number then compares directly with the paper's tables, and the Hard score (which the paper reports as, for example, 15.7) keeps its meaning.
- **Status:** Approved.

### D-12 Rounding

- **Upstream:** rounds the overall score to one decimal and the length to an integer, then computes Hard from the rounded values (R-SCORE-3 to R-SCORE-5).
- **The port does:** return unrounded metrics, and compute Hard from the unrounded mean score and mean length.
- **Why:** Inspect metrics are conventionally unrounded, and rounding is a display concern.
- **Effect on scores:** at most a change in the last reported digit. Parity checks compare at one decimal.
- **Status:** Approved.

### D-13 The `other` dimension

- **Upstream:** the code reports whatever dimension values the data holds, including `other` (R-DATA-5). The paper lists five dimensions.
- **The port does:** report all six.
- **Status:** Approved.

### D-14 Judge prompt hardening

- **GL convention:** BEST_PRACTICES recommends delimiting the submission and placing instructions after it.
- **The port does:** use R-JUDGE-2 byte for byte.
- **Why:** any change to the judge prompt changes scores.
- **Status:** Approved.

### D-15 Judge sees no scenario

- **Upstream:** R-JUDGE-1.
- **The port does:** the same.
- **Status:** Approved.

### D-16 Default judged text

- **Upstream:** `thinking_trace` for the main script, `model_resp` for Theory (R-JUDGE-4).
- **The port does:** a `judge_target` task parameter with those defaults.
- **Status:** Approved.

### D-17 Scope

- **The port does:** both datasets and both judged texts, with the main benchmark working end to end before Theory is added. Only the public half of the benchmark exists to port (R-DATA-8).
- **Status:** Approved (during planning).

### D-18 Epochs

- **Upstream:** one generation per scenario. The paper reports no repeats.
- **The port does:** one epoch by default.
- **Status:** Approved.

### D-19 Parity target and run budget

- **Facts:** a full run makes 11,450 judge calls per model per judged text on the main benchmark and 3,835 on Theory. The judge is non-deterministic (D-05). Several of the paper's models may have been retired or changed since the paper.
- **GL expectations:** `eval-report-workflow` budgets the full dataset or $5 per model, whichever is cheaper. The inspect_evals register asks for logs from two models on all samples.
- **To decide before T11:**
  - which models to run, and on how many samples;
  - how close to the paper counts as a match. Recommendation: measure run-to-run spread on a subset first and set the tolerance from it;
  - the spending limit.
- **Recommendation for models:** include gpt-oss-120b as a model under test. It has open weights, so it is the least likely to have drifted.
- **Status:** Open. In T0 the owner chose to leave it open until T11, when a five-sample cost estimate exists. Nothing before T11 depends on it.

### D-20 `eval.yaml` group

- **Facts:** the template default is `Knowledge`. The allowed groups are Assistants, Coding, Cybersecurity, Knowledge, Mathematics, Multimodal, Reasoning, Safeguards, Scheming and Writing. inspect_evals lists the closest existing benchmark, MORU ("Moral Reasoning under Uncertainty"), under `Safeguards` (its `eval.yaml` on `main`, checked 2026-11-16).
- **The port does:** `group: Safeguards`.
- **Why:** GL's `create-eval` skill says to follow inspect_evals' grouping where one exists.
- **Considered and rejected:** `Reasoning`, which describes what MoReBench measures but differs from how inspect_evals files moral-reasoning evals.
- **Status:** Approved.

## Open questions for the owner

1. D-19: models, tolerance and budget for the parity run. (blocks T11)
