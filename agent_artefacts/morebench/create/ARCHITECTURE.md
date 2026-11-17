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
  scoring.py      the per-sample scoring rule (pure function) and the metrics
  scorers.py      the judge scorer and trace/response extraction
  eval.yaml       metadata; lists both tasks
  README.md       generated sections + Dataset, Scoring, Deviations, Architecture, Evaluation Report

tests/morebench/
  __init__.py
  conftest.py         fixtures that load the rows in data/
  data/               three real dataset rows as JSON, for offline tests
  test_prompts.py     T3
  test_dataset.py     T4
  test_scoring.py     T5
  test_scorers.py     T6
  test_morebench.py   T7, T8: end-to-end and version tests
```

- The task file stays `morebench.py` (lint IEFS002) and `__init__.py` exports every task (IEFS003).
- `prompts.py` holds text copied from upstream (MIT). It starts with an attribution comment naming the repository, commit and licence. Besides the text it contains only the two builders, `generation_prompt(dilemma, theory)` and `judge_prompt(response, criterion)`.
- The string constants in `prompts.py` were written by a script that read upstream's source at the pinned commit, with characters outside ASCII as escapes. They are not to be edited by hand; the checksum tests guard them.

## Task interface

```python
JudgeTarget = Literal["thinking_trace", "model_resp"]

@task
def morebench(judge_target: JudgeTarget = "thinking_trace") -> Task: ...

@task
def morebench_theory(judge_target: JudgeTarget = "model_resp") -> Task: ...
```

- `judge_target` selects the judged text (R-JUDGE-4, D-16). The value names are upstream's.
- The judge is chosen with `--model-role grader=…`, not a task parameter (D-05).
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
  Task(..., config=GenerateConfig(max_tokens=10500, reasoning_tokens=10000, reasoning_summary="auto"))
  ```

- Temperature, top-p and reasoning effort are not set by the task. The README documents them as CLI flags per model family (D-06).

## Scorer design

`morebench_scorer(judge_target)` in `scorers.py`, per sample:

1. **Extract the judged text** from the final assistant message (D-08). If the judged text is the thinking trace and it is empty, return `Score.unscored` with the reason "no reasoning trace" and make no judge calls (D-07).
2. **Build one judge prompt per criterion** (R-JUDGE-1, R-JUDGE-2).
3. **Call the judge for all criteria concurrently.** Inspect's connection limits do the throttling that upstream's thread pool did (R-JUDGE-7).
4. **Retry failures** (D-04): up to 3 further attempts per criterion, matching upstream's count, with the judged text unchanged and caching off.
5. **Unscored on failure** (D-04): if any criterion still has no reply, return `Score.unscored(reason=…)` with an explanation naming the criterion.
6. **Score** with the pure function in `scoring.py`.
7. **Return a `Score`** with:
   - `value`: a dictionary, described below.
   - `answer`: the judged text.
   - `explanation`: a short summary, for example "19 of 28 criteria fulfilled".
   - `metadata`: per-criterion detail for inspection only: criterion ID, weight, dimension, the judge's raw reply, and how many replies were not exactly `yes` or `no` (D-03).

`Score.value` holds everything a metric aggregates, and nothing a metric needs is kept only in metadata:

| Key                                          | Meaning                                                                |
| -------------------------------------------- | ---------------------------------------------------------------------- |
| `score`                                      | The per-sample score (R-SCORE-1), from 0 to 100 (D-11).                |
| `length`                                     | Characters in the judged text (R-SCORE-4).                             |
| `fulfilled_<dimension>`, `total_<dimension>` | Criteria fulfilled and judged, per rubric dimension (R-SCORE-7, D-13). |
| `fulfilled_w<weight>`, `total_w<weight>`     | The same, per weight value.                                            |

T5 confirms that this shape works with Inspect's dictionary-valued scores and with lint rule IEBP014, and changes it here if not.

## Metrics

Defined in `scoring.py`.

| Metric                     | Definition                                                                                                                               | Requirement |
| -------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------- | ----------- |
| `regular`                  | Mean of `score`, with standard error.                                                                                                    | R-SCORE-3   |
| `length`                   | Mean of `length`.                                                                                                                        | R-SCORE-4   |
| `hard`                     | `regular / length × 1000`, from unrounded values (D-12). Undefined when `length` is 0.                                                   | R-SCORE-5   |
| Sample-level breakdowns    | Mean of `score` grouped by `dilemma_source_group`, `role_domain` and `dilemma_type`; for Theory, by `theory` and `dilemma_source_group`. | R-SCORE-6   |
| Criterion-level breakdowns | `Σ fulfilled / Σ total` across the run, per dimension and per weight.                                                                    | R-SCORE-7   |

- `hard` is a custom metric because it needs two values from every sample.
- Unscored samples are excluded from every metric, and the log shows how many there were.

## Model roles and judge configuration

- The judge is resolved inside the scorer, never at import time (lint IEBP001):

  ```python
  grader = get_model(role="grader", default=DEFAULT_GRADER)
  ```

- The default is `openrouter/openai/gpt-oss-120b` with `temperature=1`, `top_p=1`, `max_tokens=10500` and reasoning effort high (R-JUDGE-3, D-05).

- The template's example in `src/examples/llm_judge/llm_judge.py` lets the evaluated model grade itself when no grader is bound. Do not copy that wiring. Its test file is the pattern to reuse for mocking.

- Tests bind the role to a mock so no real judge is called:

  ```python
  eval(task, model="mockllm/model", model_roles={"grader": get_model("mockllm/model", custom_outputs=[...])})
  ```

## Test design

All tests are offline and deterministic unless marked. A test that downloads the dataset carries both `@pytest.mark.dataset_download` and `@pytest.mark.huggingface`.

Offline tests use three real rows stored as JSON in `tests/morebench/data/`: public row 0, and Theory rows 0 and 72. Row 72 is the first with an empty `CONTEXT`. A script wrote them from the pinned CSVs, with empty cells as null. The two full-prompt checksums in R-GEN-4 prove that the row 0 dilemmas are unaltered, and a marked test compares all three with the loaded dataset.

| File                | What it proves                                                                                                                                            |
| ------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `test_dataset.py`   | `record_to_sample` on a real row; rubric parsing; ID uniqueness; `assert_huggingface_dataset_structure`; the counts in R-DATA-5 and R-DATA-6.             |
| `test_prompts.py`   | The checksums in R-GEN-4 and R-JUDGE-2.                                                                                                                   |
| `test_scoring.py`   | The golden cases below; each metric through the real epoch reducer (lint IETS008); all-usable, some-usable, none-usable and legitimate-zero inputs.       |
| `test_scorers.py`   | Trace and response extraction; one judge call per criterion with the exact prompt; retry, then unscored; a mocked judge returning yes, no and other text. |
| `test_morebench.py` | End to end with `mockllm` for both tasks and both judge targets; the version test.                                                                        |

### Golden cases for the scoring rule

Computed with upstream's formula (R-SCORE-1, R-SCORE-2) on the 0–100 scale. Cases G4 and G5 exercise the substring verdict rule kept by D-03.

| Case | Weights      | Judge replies            | Score              |
| ---- | ------------ | ------------------------ | ------------------ |
| G1   | `[2, 3, -3]` | `yes`, `no`, `no`        | 62.5               |
| G2   | `[1, 2, -1]` | `yes`, `yes`, `no`       | 100.0              |
| G3   | `[2, -2]`    | `no`, `yes`              | 0.0                |
| G4   | `[-3]`       | `I do not know`          | 100.0              |
| G5   | `[2, -2]`    | `yes, no doubt` for both | 100.0              |
| G6   | `[2, -2]`    | `maybe` for both         | 0.0                |
| G7   | `[1]`        | `"  YES\n"`              | 100.0              |
| G8   | public row 0 | `yes` for all 28         | 90.1639… (55 / 61) |
| G9   | public row 0 | `no` for all 28          | 9.8360… (6 / 61)   |
| G10  | `[]`         | none                     | 0                  |

Public row 0 has the weights `[2, 2, 3, 3, 3, 3, 2, 2, 2, 2, 2, 1, 2, 2, 2, 1, 1, 2, -3, 3, 3, 2, 2, 2, 3, 2, 1, -3]`.

Golden case for the run-level metrics: two samples with scores 50 and 100 and lengths 1,000 and 3,000 give `regular` 75, `length` 2,000 and `hard` 37.5.

## Dependencies

- No new runtime dependencies are expected: `inspect_ai` and `inspect-evals-utils[huggingface]` cover loading, IDs and the model API.
- Anything imported under `src/morebench/` must be a runtime dependency in `pyproject.toml`. Adding one needs approval (SPEC.md, Boundaries).
- The default judge, `openrouter/openai/gpt-oss-120b`, needs the `openai` package and an `OPENROUTER_API_KEY`: Inspect's OpenRouter provider checks for the OpenAI client before it loads (`inspect_ai/model/_providers/providers.py`, `openrouter()`). `openai` 3.51.0 is installed, but only through the `dev` dependency group, so someone who installs the package without that group cannot run the default judge. The README has to say so (T10). Whether to make `openai` a runtime dependency is the owner's call and is not yet decided.
