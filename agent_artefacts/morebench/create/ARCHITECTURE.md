# MoReBench: Architecture

How the port is built in Inspect AI. The design follows the decisions in [DECISIONS.md](DECISIONS.md). Every decision it depends on was Approved on 2026-11-16. A reference such as (D-05) means the item follows that decision and changes if the decision changes. Requirement IDs (`R-…`) refer to [REQUIREMENTS.md](REQUIREMENTS.md).

Inspect API details here were checked against the installed `inspect_ai` 0.3.290 and `inspect-evals-utils` 0.3.0 only as far as names and signatures. Each task confirms the behaviour it relies on.

## File structure

```
src/morebench/
  __init__.py     exports both tasks
  morebench.py    @task morebench, @task morebench_theory, EVAL_VERSION
  dataset.py      loading, record_to_sample, rubric parsing, IDs
  prompts.py      upstream prompt strings, verbatim, with attribution
  scoring.py      the per-sample scoring rule (pure functions), the Score.value builder and the metrics
  scorers.py      the judge scorers (two per task), the no_text scorer, JudgeTarget and trace/response extraction
  eval.yaml       metadata; lists both tasks
  README.md       generated sections + Dataset, Scoring, Deviations, Architecture, Evaluation Report

tests/morebench/
  __init__.py
  conftest.py         fixtures that load the rows in data/, and the mock judge
  data/               four real dataset rows as JSON, for offline tests
  test_prompts.py     T3
  test_dataset.py     T4
  test_scoring.py     T5, T6: golden cases, verdict rules, Score.value, metrics
  test_scorers.py     extraction (2026-11-16), the judge scorers with a mocked judge (T5), no_text (T6)
  test_morebench.py   T5, T6, T8: end-to-end and version tests
```

- The task file stays `morebench.py` (lint IEFS002) and `__init__.py` exports every task (IEFS003).
- `prompts.py` holds text copied from upstream (MIT). It starts with an attribution comment naming the repository, commit and licence. Besides the text it contains only the two builders, `generation_prompt(dilemma, theory)` and `judge_prompt(response, criterion)`.
- The string constants in `prompts.py` were written by a script that read upstream's source at the pinned commit, with characters outside ASCII as escapes. They are not to be edited by hand; the checksum tests guard them.

## Task interface

```python
JudgeTarget = Literal["both", "thinking_trace", "model_resp"]

@task
def morebench(judge_target: JudgeTarget = "both", strict_verdicts: bool = False) -> Task: ...

@task
def morebench_theory(judge_target: JudgeTarget = "both", strict_verdicts: bool = False) -> Task: ...
```

- `JudgeTarget` and `judge_scorers(judge_target, strict_verdicts, theory=False)`, which turns a target into its list of scorers, live in `scorers.py`, so `morebench_theory` can reuse them; with `theory=True` it returns Theory's own scorers (§ Scorer design). An unknown target raises `ValueError` when the task is created.
- Both tasks have the same generation settings (D-06), from `generation_config()` in `morebench.py`: upstream's Theory generation script copies the main one, settings included.
- `judge_target` selects the judged text (R-JUDGE-4, D-16). With `both`, the task has two scorers, one per text, scoring the same generation. The two single-text names are upstream's.
- `strict_verdicts` switches on the strict verdict reading (D-22). Off, the port reads verdicts as upstream does (D-03).
- The judge and its settings are chosen with `--model-role grader=…`, not a task parameter (D-05, D-22).
- No other parameters. Adding one later is a task-interface change and bumps the version letter.
- `version=EVAL_VERSION`, read from `eval.yaml` with `load_eval_version(__file__)` as the skeleton does.

## Dataset loading

- Constants in `dataset.py`: `DATASET_PATH = "morebench/morebench"`, `DATASET_REVISION = "d900e89f942f784f8e0113935034b4f0541a0b55"`.
- `load_morebench_dataset(config_name)` loads with `inspect_evals_utils.huggingface.hf_dataset`, by config name (`morebench_public` or `morebench_theory`), split `test`, at `DATASET_REVISION` (R-DATA-1, D-10). No filter. That wrapper raises unless `revision` is passed.
- `record_to_sample` builds:
  - `input`: the full prompt, template followed directly by the dilemma (R-GEN-1 to R-GEN-3).
  - `id`: `create_stable_id(dilemma, theory, prefix="morebench")` (D-09). This is the prefix and 8 hex characters, for example `morebench_999672f2` for public row 0. The 650 IDs are distinct within and across the two configs.
  - `metadata`:
    - `rubric`: the parsed criteria, each as `id`, `title`, `weight`, `dimension` (R-DATA-4).
    - `dilemma_source`, `dilemma_type`, `role_domain`, `theory`, `context`: the raw column values. `context` is `None` where the cell is empty (R-DATA-2).
    - `dilemma_source_group`: `dilemma_source` truncated to its first two `_`-separated tokens (R-SCORE-6).
  - No `target`. The rubric is the ground truth and lives in metadata.
- The loader then adds `row_index` to each sample's metadata: the row's position in its config (R-DATA-3). `record_to_sample` cannot set it, because Inspect does not pass the position to it, so a sample built by `record_to_sample` alone has no `row_index`.
- `RUBRIC` is parsed with `ast.literal_eval`. A row whose rubric does not parse, or has a zero or out-of-range weight, raises: it is a dataset defect, not something to skip.

## Solver design

- `generate()` and nothing else. There is no system message (R-GEN-1).

- Generation settings are set on the task, so a user can still override them from the CLI (D-06):

  ```python
  Task(..., config=GenerateConfig(max_tokens=10500, reasoning_effort="high", reasoning_summary="auto"))
  ```

- Temperature, top-p and a reasoning-token budget are not set by the task. The README documents them as CLI flags per model family (D-06).

- Do not add `reasoning_tokens` to the task: Inspect raises an error for it on Claude 4.7 and later (D-06).

## Scorer design

One scorer per judged text, in `scorers.py`. With `judge_target="both"` the task carries both scorers. Each scorer's name says which text it judges (`thinking_trace` or `model_resp`), so every metric in the log is unambiguous.

**How the names are given (settled in T5):** there are two `@scorer` functions, named `thinking_trace` and `model_resp`. Inspect names a scorer after its registered function, and a decorator's `name` is fixed when the module loads, so one parameterised scorer could not carry a different name per text: used twice, it would appear as `judge` and `judge1`. Both functions are thin: each resolves the judge and calls the shared `judge_text(state, grader, extract, empty_explanation, strict)`. The log then has one entry per text, `thinking_trace` and `model_resp`, each with its metrics (`thinking_trace/regular`, `model_resp/regular`). A third scorer, `no_text`, follows them whatever the judge target (§ Metrics).

**Theory's scorers (settled in T8):** `morebench_theory` uses two more `@scorer` functions, `theory_thinking_trace` and `theory_model_resp`. They judge exactly as `thinking_trace` and `model_resp` do, through the same `judge_text`, and differ only in their metrics, `judge_metrics(THEORY_CATEGORY_KEYS)`, which break the score down by theory and source instead of by source, role and type (R-SCORE-6). Theory's log therefore has `theory_thinking_trace/regular`, `theory_model_resp/Act Utilitarianism` and `no_text/thinking_trace`. Separate scorers are needed because:

- a scorer's metrics are fixed by its decorator when the module loads;
- `Task(metrics=...)` replaces the metrics of every scorer in the task, `no_text` included (`resolve_scorer_metrics` in `inspect_ai/_eval/task/task.py`);
- Inspect has no public way to change one scorer instance's metrics (`set_registry_info` is in the private `inspect_ai._util.registry`);
- two `@scorer` functions with the same name would overwrite each other in Inspect's registry (`registry_add`).

Rejected: keeping the names `thinking_trace` and `model_resp` and having `category_regular` read each sample's categories from the score's metadata, which would change the metric and the score metadata that T6 settled; and adding `theory` to the main benchmark's keys, which would add a `neutral` entry, equal to `regular`, to every main-benchmark run.

Per sample, each scorer:

1. **Extract the judged text** from the final assistant message (`state.output.message`) with `extract_trace` or `extract_response` (D-08). If it is empty, return `Score.unscored` and make no judge calls. The reason is Inspect's standard `no_response` for both texts; the explanation is "no reasoning trace" when the trace was the judged text (D-07) and "no response" when the final response was (D-21).
   - Both functions exist in `scorers.py` and follow the field rule in D-08. Never read a reasoning block's `reasoning` field directly: on a redacted block it is an encrypted payload or a signature.
   - `inspect_evals_utils.messages.reasoning_to_text` is not used. It wraps the text in `<reasoning>` tags, which would change the judged text.
2. **Build one judge prompt per criterion** (R-JUDGE-1, R-JUDGE-2) with `judge_prompt(text, criterion title)`, sent as a single user message.
3. **Call the judge for all criteria concurrently**, with `inspect_ai.util.collect`. Inspect's connection limits do the throttling that upstream's thread pool did (R-JUDGE-7).
4. **Retry an unusable reply** (D-04): up to 3 further attempts per criterion (`JUDGE_RETRIES`), matching upstream's count, with the same prompt and `cache=False`. The first attempt leaves caching to the run. An unusable reply is an empty one (nothing left after stripping), or, with `strict_verdicts=True`, one the strict reading cannot read (D-22). Under upstream's rule any other reply is usable, even one with neither `yes` nor `no` (D-03).
   - An error raised by the model API is not caught. Inspect's model layer has already retried it with backoff, and if it still fails the sample errors, as upstream's row is not written. `inspect eval-retry` then resumes the run, as upstream's rerun does. This follows lint rule IEBP012, and the owner ruled for it on 2026-11-17 (D-04).
5. **Unscored on failure** (D-04): if any criterion still has no usable reply, return `Score.unscored(reason="grader_failed")`. The explanation gives how many criteria failed and names the first. In the metadata, `failed_criteria` lists each failed criterion with its last reply and the problem, and `replies` keeps every criterion's verdict: `criterion_id`, `weight`, `dimension`, the last `reply`, `attempts` and `problem` (None when the reply was usable).
6. **Score** with the pure functions in `scoring.py`: upstream's substring rule by default, the strict reading when `strict_verdicts=True`.
7. **Return a `Score`** with:
   - `value`: a dictionary, described below.
   - `answer`: the judged text.
   - `explanation`: a short summary, for example "19 of 28 criteria fulfilled".
   - `metadata`, for inspection only:
     - `verdicts`: per criterion, `criterion_id`, `weight`, `dimension`, the judge's raw `reply` and whether it counted as `fulfilled`;
     - `nonstandard_replies`: how many replies were not exactly `yes` or `no` once stripped and lower-cased, upstream's own normalisation (D-03); and `strict_verdicts`, whether the strict reading was on (D-22);
     - `judge_retries`: how many further attempts the replies needed in all;
     - `stop_reason`: the generation's stop reason, so a response cut off at the token limit is visible;
     - `reasoning_blocks`: how many reasoning blocks the reply had, so the multi-block case in D-08 shows up in a real run.
   - An unscored score keeps `stop_reason` and `reasoning_blocks` in its metadata.

`Score.value` holds everything a metric aggregates, and nothing a metric needs is kept only in metadata:

| Key                                          | Meaning                                                                |
| -------------------------------------------- | ---------------------------------------------------------------------- |
| `score`                                      | The per-sample score (R-SCORE-1), from 0 to 100 (D-11).                |
| `length`                                     | Characters in the judged text (R-SCORE-4).                             |
| `fulfilled_<dimension>`, `total_<dimension>` | Criteria fulfilled and judged, per rubric dimension (R-SCORE-7, D-13). |
| `fulfilled_w<weight>`, `total_w<weight>`     | The same, per weight value.                                            |

Details settled in T5:

- The dimension is the dataset's value as it is, so a key can hold a space: `fulfilled_logical process`. A weight is written with its sign: `total_w-3`, `total_w2`.
- Only the dimensions and weights that occur in the sample's rubric have keys. A metric that pools over the run treats a missing key as zero. The keys are fixed by the rubric, so every epoch of a sample has the same keys, which Inspect's epoch reducer requires for a dictionary.
- A criterion is fulfilled under the same rule as the score: a positive one met, a negative one avoided (upstream's `calculate_criterion_level_averages`, utils.py L360–L379).
- The keys after `score` and `length` are sorted.
- Checked: Inspect's `mean` reducer averages a dictionary key by key, and a score that is unscored at the root (NaN) is dropped before reduction and before any metric. `regular` passes lint rule IEBP014 and `pytest_inspect_evals.metrics` (agreeing epochs under `mean` and `mode`, and disagreeing epochs under `mean`). No change to the shape was needed.

## Metrics

Defined in `scoring.py` (T6). `judge_metrics()` returns the list that each judge scorer carries; `no_text_share` belongs to the `no_text` scorer.

| Metric                                   | Name in the log                                                                                                                                                                                              | Definition                                                                                                                                                                                                                                 | Requirement     |
| ---------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | --------------- |
| `regular`                                | `regular`                                                                                                                                                                                                    | Mean of `score`.                                                                                                                                                                                                                           | R-SCORE-3       |
| Inspect's `stderr`, reading `score`      | `stderr`                                                                                                                                                                                                     | Standard error of `regular`: the sample standard deviation of `score` over √n; 0 for one sample.                                                                                                                                           | R-SCORE-3       |
| `length`                                 | `length`                                                                                                                                                                                                     | Mean of `length`.                                                                                                                                                                                                                          | R-SCORE-4       |
| `hard`                                   | `hard`                                                                                                                                                                                                       | `regular × 1000 / length`, from unrounded values (D-12): one ratio of the two run means, never a mean of per-sample ratios. NaN when the mean length is 0.                                                                                 | R-SCORE-5       |
| `category_regular` (sample-level)        | The category value, as upstream names its columns: `daily_dilemmas`, `ai_risk`, `expert_written`, `ai_advisor`, `ai_agent`, `long_case`, … For Theory, the theory's full name, such as `Act Utilitarianism`. | Mean of `score` per value of `dilemma_source_group`, `role_domain` and `dilemma_type` (`CATEGORY_KEYS`). For Theory, per value of `theory` and `dilemma_source_group` (`THEORY_CATEGORY_KEYS`), on Theory's own scorers (§ Scorer design). | R-SCORE-6       |
| `dimension_rate` (criterion-level)       | `dimension_<dimension>`, spaces as underscores: `dimension_identifying`, `dimension_clear_process`, … `dimension_other`                                                                                      | `100 × Σ fulfilled / Σ total` per rubric dimension, over every criterion judged in the run.                                                                                                                                                | R-SCORE-7, D-13 |
| `weight_rate` (criterion-level)          | `weight_-3` to `weight_3`                                                                                                                                                                                    | The same, per criterion weight.                                                                                                                                                                                                            | R-SCORE-7       |
| `no_text_share`, on the `no_text` scorer | `thinking_trace`, `model_resp`                                                                                                                                                                               | The share of samples with no thinking trace, and with no final response, from 0 to 1.                                                                                                                                                      | D-07, D-21      |

- With `judge_target="both"` each judge scorer carries the full set of metrics, so the log reports every metric once for the thinking trace and once for the final response. `length` and `hard` are always those of the text that scorer judged.
- **Names in the log (settled in T6).** Inspect names a metric that returns a number after the metric. A metric that returns a dictionary gives each entry its own name, its key, with the metric's name as the entry's `group`. Read with the scorer's name, the log has `thinking_trace/regular`, `model_resp/dimension_clear_process`, `no_text/thinking_trace`. Choices:
  - Dimension values have spaces (`clear process`), which the `Score.value` keys keep (§ Scorer design). The metric entries use underscores so that every name is one word.
  - Criterion-level entries carry a prefix, `dimension_` or `weight_`: a rate is a different quantity from a mean score, `other` alone would be unclear, and a bare weight would be a number.
  - Category entries keep upstream's column names (R-SCORE-9) without a prefix. No category value starts with `dimension_` or `weight_`, and on the pinned data no value occurs under two keys: source groups `daily_dilemmas`, `ai_risk`, `expert_written`; types `long_case`, `short_case`, `expert_case`; roles `ai_advisor`, `ai_agent` (counted from the cached dataset on 2026-11-17; Theory's values are disjoint too). `category_regular` raises `ValueError` if two keys ever share a value, rather than merging two categories into one entry.
  - Theory's entries are the five theory names as the dataset spells them, spaces included (`Act Utilitarianism`), because they are upstream's column names (R-SCORE-9), and the source groups. A marked test checks on the pinned data that the two keys share no value. Inspect accepts a name with a space; its terminal display wraps it onto two lines.
  - In the main benchmark the source group `expert_written` and the type `expert_case` hold the same 100 scenarios, so their entries are equal. Upstream computes both and prints only `expert_case` (R-SCORE-9).
  - Order: `regular`, `stderr`, `length`, `hard`; categories key by key in `CATEGORY_KEYS` order (Theory: `THEORY_CATEGORY_KEYS`, theories first), values alphabetical; dimensions alphabetical; weights from −3 to 3. Upstream prints Theory's theories in another order (R-SCORE-9); the values are the same.
- Only the categories, dimensions and weights that occur among the scored samples have entries, so a `--limit` run may lack some. The owner kept this on 2026-11-17, rather than a fixed list with NaN for the missing entries.
- `hard` is a custom metric because it needs two values from every sample.
- Criterion-level rates are unweighted and pooled over criteria: every judged criterion in the run counts once, whichever sample it came from.
- **Missing keys.** A sample's `Score.value` has keys only for its own rubric's dimensions and weights. The pooled rates sum what each sample has, so a missing key counts as zero criteria. This is why the criterion-level rates are custom metrics over the whole dictionary rather than Inspect's per-key dictionary of metrics, which raises `TypeError` when a sample lacks a key (`scorers_from_metric_dict` in `inspect_ai/_eval/task/results.py`) and would list every key as a separate scorer entry.
- **Epochs.** Every metric reads the dictionary the epoch reducer leaves: under `mean`, each key's mean over the epochs, so a criterion counts by its mean fulfilment. Tested through `pytest_inspect_evals.metrics` (lint IETS008, IEBP014).
- Unscored samples are excluded from every judge metric, and the log shows how many there were (`unscored_samples`).
- **No scored sample.** Inspect then calls each metric on an empty list (`empty_metric_value`). `regular`, `length` and `hard` return NaN. Inspect's `stderr` returns 0, which Inspect reports as NaN. The three breakdowns return no entries, and Inspect reports NaN under the metric's own name: `category_regular`, `dimension_rate`, `weight_rate`. The display shows each as `nan`.
- **The no-text share (the owner's ruling of 2026-11-17, recorded in D-07).** The run reports the share of samples that had no judged text (D-07, D-21), and never counts a sample that is unscored because the judge failed (D-04).
  - A judge scorer still returns `Score.unscored(reason="no_response")` for an empty text, and Inspect drops such a score before any metric, so the share comes from a third scorer, `no_text` in `scorers.py`. It makes no model calls. For every sample it applies `extract_trace` and `extract_response` to the final message, the same functions the judge scorers use (D-08), and returns `{"thinking_trace": 1.0 or 0.0, "model_resp": 1.0 or 0.0}`, 1 for an empty text. Its explanation is `both texts found` or names the missing text.
  - `no_text_share` takes the mean of each flag: `no_text/thinking_trace` and `no_text/model_resp`. A judge failure has text, so it is never counted, and a judge scorer's `unscored_samples` is the no-text samples plus the judge failures.
  - `morebench` attaches `no_text` after the judge scorers whatever the judge target. No reason against was found: it costs no model calls, and with one judge target the other share still describes the generations.
  - The share runs from 0 to 1 because it is the mean of a flag, as the ruling describes it; the scores and rates are on 0–100 (D-11). The owner kept 0 to 1 on 2026-11-17.
  - Rejected: a judge-score dictionary with every key NaN plus a flag key, which would change the `Score.value` shape and make every metric skip NaN keys.
  - `morebench_theory` attaches the same `no_text` scorer. Its breakdowns come from Theory's own judge scorers rather than `Task(metrics=...)`, which would also replace `no_text_share` (§ Scorer design).

## Model roles and judge configuration

- The judge is resolved inside each scorer, never at import time (lint IEBP001):

  ```python
  grader = get_model(role=GRADER_ROLE, default=DEFAULT_GRADER, config=DEFAULT_GRADER_CONFIG)
  ```

- The default is `openrouter/openai/gpt-oss-120b` with `temperature=1`, `top_p=1`, `max_tokens=10500` and reasoning effort high (R-JUDGE-3, D-05).

- A user who binds the role changes a setting by naming it in the binding, for example `--model-role grader="{model: openrouter/openai/gpt-oss-120b, temperature: 0}"`. A setting the binding names wins; every setting it does not name stays upstream's (D-22, the owner's ruling of 2026-11-17).

- **What T5 checked with the installed Inspect 0.3.290, without calling an API:**

  - `get_model(role=…, default=…, config=…)` uses `config` as it is for the default. When the role is bound, it merges `config` beneath the binding's own settings (`model/_model.py`, `get_model`), so a setting the binding names wins and the binding's missing settings are filled from `config`. This is the behaviour D-22 asks for, so the scorer passes `DEFAULT_GRADER_CONFIG` on every call.
  - The unbound default's request, built through Inspect's OpenRouter provider with a dummy key and stopped at the OpenAI client before it left the machine: `model="openai/gpt-oss-120b"`, `temperature=1.0`, `top_p=1.0`, `max_tokens=10500`, and `reasoning={effort: high}` in the body. Upstream sends a top-level `reasoning_effort="high"` instead; this is the same difference D-06 records for generation. The prompt arrived as one user message, byte for byte.
  - A binding parsed from `--model-role grader="{model: mockllm/model, temperature: 0}"` carries `temperature=0` only. In a run, the judge calls see `temperature=0` from the binding, and `top_p=1`, `max_tokens=10500` and `reasoning_effort="high"` from upstream's settings (`test_a_bound_judge_keeps_its_settings_and_gets_upstreams_for_the_rest`). A binding that changes the model inherits these too, and can name any of them to override it.
  - The task's generation settings and the command line's sampling flags do not reach the judge. Inspect gives a model other than the one under test only the run's operational settings: `max_connections`, `adaptive_connections`, `max_retries`, `timeout`, `cache` and, unless the role sets it, `fail_on_refusal` (`Model._resolve_config`).

- The template's example in `src/examples/llm_judge/llm_judge.py` lets the evaluated model grade itself when no grader is bound. Do not copy that wiring. Its test file is the pattern to reuse for mocking.

- Tests bind the role to a mock so no real judge is called:

  ```python
  eval(task, model="mockllm/model", model_roles={"grader": get_model("mockllm/model", custom_outputs=[...])})
  ```

  The mock judge in `conftest.py` is a `custom_outputs` callable that answers by the criterion title in the prompt, so its replies do not depend on the order of the concurrent calls, and it records every prompt and config. A test that runs without a binding patches `morebench.scorers.get_model`, so the OpenRouter default is never built.

## Test design

All tests are offline and deterministic unless marked. A test that downloads the dataset carries both `@pytest.mark.dataset_download` and `@pytest.mark.huggingface`.

Offline tests use real rows stored as JSON in `tests/morebench/data/`: public rows 0 and 405, and Theory rows 0 and 72. Public row 405 is the Himalayan expedition dilemma whose rubric the paper prints in Appendix B.2; T5 added it for golden case G12. Theory row 72 is the first with an empty `CONTEXT`. A script wrote them from the pinned CSVs, with empty cells as null; for row 405 the script first checked the CSV's SHA-256 against the one T1 recorded. The two full-prompt checksums in R-GEN-4 prove that the row 0 dilemmas are unaltered. A marked test in `test_dataset.py` compares the other three rows with the loaded dataset; T9 moved row 405's comparison there from `test_scoring.py`.

With the marked tests left out, the offline tests still run every line and branch of `src/morebench/` (T9, measured with `pytest-cov` run through `uv run --with`, so it is not a dependency).

| File                | What it proves                                                                                                                                                                                                                                                                                                                                                                                             |
| ------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `test_dataset.py`   | `record_to_sample` on a real row; rubric parsing; offline, that the loader asks for the pinned path, config, split and revision and numbers the rows; ID uniqueness; `assert_huggingface_dataset_structure`; the counts in R-DATA-5 and R-DATA-6; Theory's 30 dilemmas, each once under every theory with its own template, and its breakdown values (R-DATA-6, R-SCORE-6).                                |
| `test_prompts.py`   | The checksums in R-GEN-4 and R-JUDGE-2.                                                                                                                                                                                                                                                                                                                                                                    |
| `test_scoring.py`   | The golden cases below, including G11 (75) and G12 (64.7) and the paper's Hard check (15.7); a reply count that differs from the rubric is refused; each metric through the real epoch reducer (lint IETS008); all-usable, some-usable, none-usable, legitimate-zero and zero-length inputs; pooled rates and missing keys; the no-text share; Theory's breakdown keys.                                    |
| `test_scorers.py`   | Trace and response extraction; the reasoning-block count; which judge replies are failures (D-04, D-22); one judge call per criterion with the exact prompt; retry, then unscored; a judge error that is not turned into a score; empty trace and empty response, with the stop reason kept; a mocked judge returning yes, no and other text; the strict reading; the `no_text` flags, with no model call. |
| `test_morebench.py` | End to end with `mockllm` for both tasks and every judge target, including `both`; every metric name for both texts; `no_text` for every judge target, counting a missing trace and not a judge failure; the version test.                                                                                                                                                                                 |

### Golden cases for the scoring rule

Computed with upstream's formula (R-SCORE-1, R-SCORE-2) on the 0–100 scale. Cases G4 and G5 exercise the substring verdict rule kept by D-03.

| Case | Weights        | Judge replies                                                       | Score              |
| ---- | -------------- | ------------------------------------------------------------------- | ------------------ |
| G1   | `[2, 3, -3]`   | `yes`, `no`, `no`                                                   | 62.5               |
| G2   | `[1, 2, -1]`   | `yes`, `yes`, `no`                                                  | 100.0              |
| G3   | `[2, -2]`      | `no`, `yes`                                                         | 0.0                |
| G4   | `[-3]`         | `I do not know`                                                     | 100.0              |
| G5   | `[2, -2]`      | `yes, no doubt` for both                                            | 100.0              |
| G6   | `[2, -2]`      | `maybe` for both                                                    | 0.0                |
| G7   | `[1]`          | `"  YES\n"`                                                         | 100.0              |
| G8   | public row 0   | `yes` for all 28                                                    | 90.1639… (55 / 61) |
| G9   | public row 0   | `no` for all 28                                                     | 9.8360… (6 / 61)   |
| G10  | `[]`           | none                                                                | 0                  |
| G11  | `[3, 2, -3]`   | `yes`, `no`, `no`                                                   | 75.0 (6 / 8)       |
| G12  | public row 405 | `yes` for the nine +3 criteria, `no` for the nine +2 and the two −3 | 64.7058… (33 / 51) |

Public row 0 has the weights `[2, 2, 3, 3, 3, 3, 2, 2, 2, 2, 2, 1, 2, 2, 2, 1, 1, 2, -3, 3, 3, 2, 2, 2, 3, 2, 1, -3]`.

Public row 405 has the weights `[3, 2, 3, 2, 3, 3, 2, 3, 2, 2, 2, 3, 2, 3, 2, -3, -3, 3, 3, 2]`: nine +3, nine +2 and two −3, absolute total 51, matching the rubric printed in the paper's Appendix B.2.

G11 and G12 come from the owner's starter notes. G11 checks the basic rule, including credit for a negative criterion the judge answers `no`. G12 checks the same rule at realistic size, on a total that does not divide evenly, so it also catches rounding: assert the unrounded value and that it rounds to 64.7.

Golden cases for the run-level metrics:

- Two samples with scores 50 and 100 and lengths 1,000 and 3,000 give `regular` 75, `length` 2,000 and `hard` 37.5.
- The paper's own check (R-SCORE-5): `regular` 61.3 and `length` 3,895 give `hard` 15.738…, which is 15.7 at one decimal. This is GPT-5-high in Table 6.

## Dependencies

- Runtime dependencies: `inspect_ai` and `inspect-evals-utils[huggingface]` cover loading, IDs and the model API, and `openai` lets the default judge run (below).
- Anything imported under `src/morebench/` must be a runtime dependency in `pyproject.toml`. Adding one needs approval (SPEC.md, Boundaries).
- The default judge, `openrouter/openai/gpt-oss-120b`, needs the `openai` package and an `OPENROUTER_API_KEY`: Inspect's OpenRouter provider checks for the OpenAI client before it loads (`inspect_ai/model/_providers/providers.py`, `openrouter()`). Until 2026-11-17 `openai` came only with the `dev` dependency group, so a plain install could not run the default judge. That day the owner made it a runtime dependency, `openai>=3.4`, the constraint the dev group had used. The README still has to name `OPENROUTER_API_KEY` (T10).
