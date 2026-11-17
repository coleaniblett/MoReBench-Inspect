# MoReBench

An Inspect port of [MoReBench](https://arxiv.org/abs/2510.16380), which evaluates the moral reasoning process of language models. A model is given a moral dilemma and asked for its reasoning and decision. A judge model then checks the response against 20 to 47 weighted, expert-written rubric criteria, and the score is the share of rubric weight earned.

<!-- Contributors: Automatically Generated -->
Contributed by [@ColeANiblett](https://github.com/ColeANiblett)
<!-- /Contributors: Automatically Generated -->

<!-- Usage: Automatically Generated -->
## Usage

First, install dependencies:

```bash
uv sync
```

Then run evaluations:

```bash
uv run inspect eval morebench/morebench --model openai/gpt-5-nano
```

You can also import tasks as Python objects:

```python
from inspect_ai import eval
from morebench import morebench
eval(morebench)
```

If your directory name doesn't match your package name but you have registered your eval task, you can also run:

```bash
uv run inspect eval morebench --model openai/gpt-5-nano
```

After running evaluations, view logs with:

```bash
uv run inspect view
```

If you don't want to specify `--model` each time, create a `.env` file:

```bash
INSPECT_EVAL_MODEL=anthropic/claude-opus-4-1-20250805
ANTHROPIC_API_KEY=<anthropic-api-key>
```
<!-- /Usage: Automatically Generated -->

<!-- Options: Automatically Generated -->
## Options

You can control a variety of options from the command line. For example:

```bash
uv run inspect eval morebench/morebench --limit 10
uv run inspect eval morebench/morebench --max-connections 10
uv run inspect eval morebench/morebench --temperature 0.5
```

See `uv run inspect eval --help` for all available options.
<!-- /Options: Automatically Generated -->

<!-- Parameters: Automatically Generated -->
## Parameters

### `morebench`

- `judge_target` (Literal['both', 'thinking_trace', 'model_resp']): Which text the judge reads: `both` (the default), scored once for the thinking trace and once for the final response from the same generation; or only `thinking_trace` or `model_resp`. (default: `'both'`)
- `strict_verdicts` (bool): Read the judge's replies strictly, accepting only a reply that leads with yes or no, instead of with the original's substring rule. A reply the strict reading cannot read leaves the sample unscored. (default: `False`)
<!-- /Parameters: Automatically Generated -->

## Dataset

Describe the dataset here: where it comes from, how many samples it has, and how a record becomes a `Sample`.

## Scoring

Describe the scorer here: what counts as correct, and which metrics the task reports.

## Deviations from the original implementation

| What changed | Why | Expected effect on scores |
| --- | --- | --- |
| Nothing yet. | | |

## Architecture

Add a diagram of the task here: dataset, solver, scorer, and any sandbox or judge model.
