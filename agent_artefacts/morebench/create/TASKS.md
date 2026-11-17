# MoReBench: Tasks

The port, split into tasks that each fit one session. Each task is a self-contained prompt: it names what to read, what to change and how to check the result. Run one task per fresh session, in order.

To start a task:

> Read `agent_artefacts/morebench/create/SPEC.md`, then do task T4 in `TASKS.md`.

## Status

Update this table at the end of each task.

| Task | Title                                  | GL `create-eval` phase | Status          |
| ---- | -------------------------------------- | ---------------------- | --------------- |
| T0   | Sign off the decisions (owner)         | 1.5, 2.7               | Done 2026-11-16 |
| T1   | Verify the spec against upstream       | 1                      | Done 2026-11-16 |
| T2   | Scaffold                               | 3                      | Done 2026-11-16 |
| T3   | Prompts                                | 4.2                    | Done 2026-11-16 |
| T4   | Dataset loading                        | 4.1                    | Done 2026-11-16 |
| T5   | Scoring rule and metrics               | 4.3                    | Not started     |
| T6   | Judge scorer                           | 4.3                    | Started         |
| T7   | Assemble `morebench` and smoke-test it | 4.4–4.8                | Started         |
| T8   | Add `morebench_theory`                 | 4                      | Not started     |
| T9   | Test coverage and lint pass            | 5, 6.1–6.2             | Not started     |
| T10  | README                                 | 6.3                    | Not started     |
| T11  | Parity run and evaluation report       | 6.4                    | Not started     |
| T12  | Validity review and submission prep    | 6.4                    | Not started     |

## Rules for every task

1. **Read** `SPEC.md` in full, then only the sections listed under the task's **Load**. Do not load the rest of the spec.
2. **Check the decisions** listed under **Needs**. If any is not Approved in `DECISIONS.md`, stop and ask before writing the behaviour that depends on it.
3. **Stay in the files** listed under **Touch**. If the task turns out to need another file, say so before editing it.
4. **Close the task** with these four steps, in order:
   1. *Checks.* Run all checks (SPEC.md §5) and report the actual results.
   2. *Self-check.* For each requirement and decision the task cites, state where it is met (file and line), or that it is not met and why.
   3. *Spec sync.* If anything learned contradicts or extends the spec, correct the spec file, add a line to the changelog in SPEC.md §13, and update the status table above.
   4. *Report.* Say what was done, what was not, and what the owner needs to decide. Then stop. Do not start the next task.

______________________________________________________________________

## T0 — Sign off the decisions (owner)

- **Goal:** every decision the implementation depends on is Approved.
- **Who:** the owner, with an agent recording the outcome.
- **Load:** `DECISIONS.md`, starting from "Open questions for the owner".
- **Touch:** `DECISIONS.md`; `ARCHITECTURE.md` where a ruling changes the design; SPEC.md §13.
- **Steps:**
  1. Rule on the Open decisions that block early tasks: D-03, D-06, D-07, D-11, D-20.
  2. Approve or change each Proposed decision.
  3. Update statuses, and update `ARCHITECTURE.md` (including golden cases G4 and G5 if D-03 changes).
- **Done when:** no decision needed by T2 to T8 is Open or Proposed. D-19 may stay Open until T11.

## T1 — Verify the spec against upstream

- **Goal:** confirm every requirement from the primary sources, independently of the session that wrote the spec.
- **Load:** `REQUIREMENTS.md`, all of it.
- **Touch:** `REQUIREMENTS.md`; `DECISIONS.md` if a corrected fact changes a decision; SPEC.md §13. No code.
- **Steps:**
  1. Download the upstream files at the pinned commit and both CSVs at the pinned revision into a temporary folder outside the repo. Read them as text. Do not execute upstream code.
  2. For each `R-` item, check the quoted text, the numbers and the line link.
  3. Recompute the counts in R-DATA-5 to R-DATA-7 and the checksums in R-GEN-4 and R-JUDGE-2.
  4. Check R-GEN-5, R-SCORE-8 and the Reported results tables against paper v2 (Appendix E.1, §3.2, Appendix G).
  5. Correct any mismatch in the spec and list each correction.
- **Self-check:** a table of every `R-` ID marked verified or corrected.
- **Done when:** every ID is marked.
- **Stop and ask if:** a correction contradicts an Approved decision.

## T2 — Scaffold

- **Goal:** turn the template skeleton into the MoReBench package without changing behaviour.
- **Needs:** D-20.
- **Load:** `REQUIREMENTS.md § Sources and pins`; `ARCHITECTURE.md § File structure`, `ARCHITECTURE.md § Dependencies`.
- **Touch:** `src/morebench/eval.yaml`; the title and description of `src/morebench/README.md`; docstrings in `src/morebench/morebench.py`.
- **Steps:**
  1. Run all checks before changing anything and record the baseline.
  2. Fill in `eval.yaml`: a real title, description, the paper's arXiv link, and the group from D-20. Leave `version` at `1-A` and the task list as it is.
  3. Find out which provider package the default judge (`openrouter/openai/gpt-oss-120b`) needs at run time and whether it is installed. Record the answer in `ARCHITECTURE.md § Dependencies`.
  4. Regenerate the README sections.
- **Done when:** all checks pass and `eval.yaml` describes MoReBench.
- **Stop and ask if:** a dependency is missing.

## T3 — Prompts

- **Goal:** upstream's prompt text exists in the package, byte for byte, with tests that prove it.
- **Needs:** D-14.
- **Load:** `REQUIREMENTS.md § Generation` (R-GEN-1 to R-GEN-4); `REQUIREMENTS.md § Judging` (R-JUDGE-2); `ARCHITECTURE.md § File structure`.
- **Touch:** `src/morebench/prompts.py`, `tests/morebench/test_prompts.py`.
- **Steps:**
  1. Copy the neutral template, the theory template, the five theory definitions and the judge instruction from upstream at the pinned commit. Copy the bytes; do not retype.
  2. Add the attribution comment (repository, commit, MIT licence).
  3. Add two small builders: generation prompt from dilemma and theory, and judge prompt from response and criterion. An unknown theory raises `ValueError`.
  4. Test every checksum in R-GEN-4 and R-JUDGE-2. For the two full-prompt checksums, use the real row text.
- **Done when:** all eight generation checksums and the judge checksum pass.
- **Stop and ask if:** a checksum cannot be matched. Do not adjust the expected value.

## T4 — Dataset loading

- **Goal:** both dataset configs load at the pinned revision into Inspect samples.
- **Needs:** D-09, D-10.
- **Load:** `REQUIREMENTS.md § Dataset`; `ARCHITECTURE.md § Dataset loading`, `ARCHITECTURE.md § Test design`.
- **Touch:** `src/morebench/dataset.py`, `tests/morebench/test_dataset.py`.
- **Steps:**
  1. Add the path and revision constants.
  2. Write the rubric parser and `record_to_sample`, using the T3 builder for `input`.
  3. Write one loader that takes the config name.
  4. Test `record_to_sample` and the parser on a real row, offline.
  5. Add marked tests against the real dataset: structure, row and criteria counts, weight range, ID uniqueness, and the theory filter assertion from D-10.
- **Done when:** the counts in R-DATA-5 and R-DATA-6 are asserted by tests and pass.
- **Stop and ask if:** a row fails to parse or an ID collides.

## T5 — Scoring rule and metrics

- **Goal:** the per-sample score and every run-level metric, as pure code with no model calls.
- **Needs:** D-02, D-03, D-07, D-11, D-12, D-13, D-21.
- **Load:** `REQUIREMENTS.md § Scoring and metrics`; `ARCHITECTURE.md § Scorer design` (the `Score.value` table only); `ARCHITECTURE.md § Metrics`, `ARCHITECTURE.md § Test design`.
- **Touch:** `src/morebench/scoring.py`, `tests/morebench/test_scoring.py`.
- **Steps:**
  1. Port the scoring rule, with the upstream line reference.
  2. Write the helper that turns one sample's judgements into the `Score.value` dictionary.
  3. Write `regular`, `length`, `hard`, the two kinds of breakdown, and the share of samples with no judged text (D-07, D-21). Settle how that share is produced and record it in `ARCHITECTURE.md § Metrics`.
  4. Test every golden case and the run-level golden case.
  5. Test each metric through the real epoch reducer, and with all-usable, some-usable, none-usable and legitimate-zero inputs, and with zero length.
- **Done when:** all golden cases pass and the eval lint has no finding against `scoring.py`.
- **Stop and ask if:** the `Score.value` shape has to change. Update `ARCHITECTURE.md` first.

## T6 — Judge scorer

- **Goal:** a scorer that judges one response against its rubric and returns the T5 score.
- **Needs:** D-04, D-05, D-07, D-08, D-15, D-21.
- **Load:** `REQUIREMENTS.md § Judging`; `REQUIREMENTS.md § Generation` (R-GEN-6 and R-GEN-7 only); `ARCHITECTURE.md § Scorer design`, `ARCHITECTURE.md § Model roles and judge configuration`, `ARCHITECTURE.md § Test design`.
- **Touch:** `src/morebench/scorers.py`, `tests/morebench/test_scorers.py`.
- **Steps:**
  1. Trace and response extraction. Done on 2026-11-16: `extract_trace` and `extract_response` exist with tests. Use them as they are.
  2. Resolve the judge through the `grader` role with the default from D-05.
  3. Judge all criteria concurrently with the T3 judge prompt.
  4. Add the retry and the unscored path from D-04, and the empty-text paths from D-07 and D-21.
  5. Test with a mocked judge: all yes, all no, mixed, other text, a failure that recovers on retry, a failure that does not, an empty trace. Assert the number of judge calls and the exact prompt sent.
- **Done when:** the tests pass with no real model call.
- **Stop and ask if:** Inspect returns reasoning content in a form D-08 does not cover.

## T7 — Assemble `morebench` and smoke-test it

- **Goal:** `morebench` runs end to end, offline in tests and once against real models.
- **Needs:** D-06, D-16, D-18.
- **Load:** `REQUIREMENTS.md § Generation` (R-GEN-5 and R-GEN-6); `ARCHITECTURE.md § Task interface`, `ARCHITECTURE.md § Solver design`.
- **Touch:** `src/morebench/morebench.py`, `src/morebench/__init__.py`, `src/morebench/eval.yaml`, `tests/morebench/test_morebench.py`.
- **Steps:**
  1. Wire the scorer and the `judge_target` parameter into the task. The dataset, `generate()` and the generation settings were wired on 2026-11-16, and the placeholder records are gone.
  2. `dataset_samples: 500` is set in `eval.yaml`. Regenerate the README sections after adding the parameter.
  3. Add end-to-end tests with a mock model and a mock judge, for both judge targets. Keep the version test.
  4. What each Inspect provider sends was recorded on 2026-11-16: see "The reasoning probe" and D-06 in `DECISIONS.md`. Nothing more to do here.
  5. **Checkpoint.** Give the owner the `--limit 1` command for one real model. After it has run, read the log together and confirm: the prompt is the expected text; a thinking trace was captured; the number of judge calls equals the number of criteria; the judge replies are `yes` or `no`. Record in D-08 how many reasoning blocks the model returned.
- **Done when:** all checks pass and the smoke run has been reviewed.
- **Stop and ask if:** the smoke run shows an empty trace, a truncated response or malformed judge replies.

## T8 — Add `morebench_theory`

- **Goal:** the Theory benchmark runs the same way.
- **Needs:** D-16.
- **Load:** `REQUIREMENTS.md § Dataset` (R-DATA-6 and R-DATA-7); `REQUIREMENTS.md § Scoring and metrics` (R-SCORE-6 and R-SCORE-9); `REQUIREMENTS.md § Task variants`; `ARCHITECTURE.md § Task interface`, `ARCHITECTURE.md § Metrics`.
- **Touch:** `src/morebench/morebench.py`, `src/morebench/__init__.py`, `src/morebench/eval.yaml`, `tests/morebench/test_dataset.py`, `tests/morebench/test_morebench.py`.
- **Steps:**
  1. Add the task with its own default judge target and its breakdowns by theory and source.
  2. Add it to `eval.yaml` with `dataset_samples: 150` and regenerate the README sections.
  3. Add dataset tests for the theory config and end-to-end tests.
  4. **Checkpoint.** A `--limit 1` real run, reviewed as in T7.
- **Done when:** all checks pass and the smoke run has been reviewed.

## T9 — Test coverage and lint pass

- **Goal:** nothing untested that carries logic, and no unexplained lint finding.
- **Load:** `ARCHITECTURE.md § Test design`.
- **Touch:** `tests/morebench/`; source files only for lint fixes that do not change behaviour.
- **Steps:**
  1. Run GL's `/inspect-evals:ensure-test-coverage` skill if it is loaded. Its coverage command needs `pytest-cov`, which is not installed: ask before adding it.
  2. Run `uv run inspect-evals-lint morebench` and list every finding with a recommendation.
  3. Fill the gaps found.
- **Done when:** all checks pass and each remaining warning has the owner's decision.

## T10 — README

- **Goal:** the eval's README documents what it is, how it scores and where it differs from upstream.
- **Load:** `DECISIONS.md`, all of it; `REQUIREMENTS.md § Sources and pins`, `REQUIREMENTS.md § Dataset`, `REQUIREMENTS.md § Scoring and metrics`; `ARCHITECTURE.md § File structure`.
- **Touch:** `src/morebench/README.md`.
- **Steps:**
  1. Regenerate the generated sections. Do not edit them by hand.
  2. Write Dataset and Scoring. Name the default judge, how to override it, and how many judge calls a sample makes.
  3. Build the deviations table from `DECISIONS.md`: every Deviation, and every Kept quirk.
  4. Give the flags that reproduce the paper's settings for each model family (D-06).
  5. Link the official implementation at the pinned commit. Write the Architecture section.
- **Done when:** all checks pass, the README has no TODO marker, and the deviations table matches `DECISIONS.md`.

## T11 — Parity run and evaluation report

- **Goal:** show how close the port is to the paper, and write the evaluation report.
- **Needs:** D-19.
- **Load:** `REQUIREMENTS.md § Reported results`; `DECISIONS.md` D-05, D-06, D-19.
- **Touch:** `src/morebench/README.md`; `DECISIONS.md`.
- **Steps:**
  1. Follow GL's `/inspect-evals:eval-report-workflow` skill. Start with a five-sample run to estimate cost.
  2. **Checkpoint.** Give the owner the cost estimate and the full commands. The owner runs them.
  3. Read the logs and compare with the paper's tables, at one decimal.
  4. Run the trajectory analysis with `/inspect-evals:check-trajectories-workflow`.
  5. Write the Evaluation Report section: results table, exact commands, dated model names, eval version, comparison with the paper, and an explanation of any gap.
- **Done when:** the report is in the README and success criterion 6 in SPEC.md §11 is met or its gap explained.
- **Stop and ask if:** a result is outside the tolerance set in D-19.

## T12 — Validity review and submission prep

- **Goal:** the repo is ready for GL review and the inspect_evals register.
- **Load:** nothing beyond `SPEC.md`.
- **Touch:** the repo root `README.md`; files changed by the template update.
- **Steps:**
  1. Run GL's `/inspect-evals:eval-validity-review` skill and act on its findings with the owner.
  2. Remove the template examples with `uvx copier update --defaults --data include_examples=false`, then `uv sync`. Delete the Examples section of the root README by hand.
  3. Walk through inspect_evals' `EVALUATION_CHECKLIST.md` and list anything unmet.
  4. Draft the register submission.
- **Done when:** all checks pass and every success criterion in SPEC.md §11 holds.
