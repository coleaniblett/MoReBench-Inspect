# MoReBench: draft register submission

**Status: draft only. Nothing has been submitted, and no issue, pull request or form has been opened.** Written in T12 on 2026-11-18.

The process below is the one in inspect_evals' [`register/README.md`](https://github.com/UKGovernmentBEIS/inspect_evals/blob/f79b8be47d54e1165f9c82df77c3e3bc47b2894a/register/README.md), read at `main` commit `f79b8be` on 2026-11-18. Check it again before submitting: the register is in beta and its process changes.

## How the register works

1. The contributor opens a **Register Eval Submission** issue on inspect_evals. The form asks for three things: an arXiv URL, a source URL, and optional extra maintainers.
2. A bot checks the submission, takes the eval's metadata from the arXiv paper, and opens a pull request that adds `register/<id>/eval.yaml`.
3. Once that pull request is open, the contributor uploads logs of **two models running every sample** to the inspect_evals log store and says so on the pull request. A maintainer checks them before merging.

The bot's automated checks:

- the repository is public on GitHub;
- the commit is a full 40-character SHA that exists on the remote;
- the id and task names do not collide with an existing eval.

For a new entry, an agent review also checks:

- that each `@task` exists at its path;
- that the task file builds a `Task` with a dataset and a scorer;
- that the title and description match the code;
- security.

It also runs `inspect-evals-lint` with the `single-eval` preset. That lint result is for information only.

**One task per issue.** This repo has two tasks in one file, so it needs two issues, each with a line anchor.

## Before submitting

| #   | What                                                                                                                                                                                                                                                                                                                                                                                                                                                                             | Status                                                     |
| --- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------- |
| 1   | **The commit to pin.** The source URL must name a commit that exists on the public remote. `main` has T5 to T12 (pull requests #5 and #6). Merge the `t11/parity-run` pull request, then use `main`'s full SHA in both source URLs, and in `source.repository_commit` below.                                                                                                                                                                                                     | Merge, then pin                                            |
| 2   | **Which repository.** The git remote is `https://github.com/coleaniblett/MoReBench-Inspect`, which is public. `pyproject.toml` `[project.urls]` names `https://github.com/Generality-Labs/morebench`, which does not exist (HTTP 404 on 2026-11-18). That URL comes from the template answer `github_owner: Generality-Labs`. The owner chose the remote on 2026-11-23, and `pyproject.toml` now names it, as the draft below does.                                              | Done 2026-11-23; see [CHECKLIST.md](CHECKLIST.md), item U3 |
| 3   | **Logs of two models on every sample.** That is all 500 `morebench` scenarios and all 150 `morebench_theory` rows, each on two models. T11 ran one model on every sample on 2026-11-23: gpt-oss-120b, both tasks, both texts, at medium effort, for about $3.60 at that day's list price (README, Evaluation Report). A second model is still needed. The register asks for logs to be de-identified before upload, for example by removing local paths that contain a username. | One of two models done                                     |
| 4   | **Evaluation report.** It is optional in the register entry (`evaluation_report`), and is rendered as a results table. The README's Evaluation Report now has the gpt-oss-120b results to fill it from.                                                                                                                                                                                                                                                                          | Ready to fill                                              |
| 5   | **Register lint preview.** `uv run inspect-evals-lint --preset single-eval --all` on this branch: 25 passed, 1 warning (IECQ007, deferred), 14 skipped, 2 suppressed (IEBP015, D-03). The register's lint badge does not count suppressed checks as passing.                                                                                                                                                                                                                     | Done in T12                                                |
| 6   | **Duplicates.** No register entry or internal inspect_evals eval is named MoReBench or covers moral reasoning; the nearest name in `register/` is `moru`. Listing taken 2026-11-18.                                                                                                                                                                                                                                                                                              | Done in T12                                                |

Two things from T10 that do not affect the register:

- **Relative links in the README.** `src/morebench/README.md` links to `DECISIONS.md` and `ARCHITECTURE.md` by relative path. The register does not copy the README. Its generated page links back to the repository at the pinned commit, where those links work. They break only if the README is copied out of the repository.
- **A retired model in the Usage section.** The generated Usage section's `.env` example names `anthropic/claude-opus-4-1-20250805`, which is retired. That text comes from the template's README generator in `inspect_evals_utils`, so it cannot be fixed here; it is a report for Generality Labs. The register's page has its own usage section, so it is not affected.

## Issue 1 of 2: `morebench`

Form fields:

- **arXiv URL:** `https://arxiv.org/abs/2510.16380v2`
- **Source URL:** `https://github.com/coleaniblett/MoReBench-Inspect/blob/<40-char SHA>/src/morebench/morebench.py#L23`
  - Line 23 is `def morebench(` on `t12/validity-review`. Check the line at the pinned commit.
- **Maintainers:** leave blank. The submitter is added automatically.

If the form has room for a note:

> An Inspect port of MoReBench (Chiu et al., arXiv 2510.16380 v2), from the authors' code at `morebench/morebench` branch `eval`, commit `e6689bbb9d742c48ea78ea07acd7931eba05b213`, and the dataset `morebench/morebench` at revision `d900e89f942f784f8e0113935034b4f0541a0b55`. This task covers the 500 public scenarios. The same file defines a second task, `morebench_theory`, which is submitted in a separate issue. The judge defaults to the original's, `openrouter/openai/gpt-oss-120b`, through the `grader` role. The README lists every deviation from the original.

## Issue 2 of 2: `morebench_theory`

Form fields:

- **arXiv URL:** `https://arxiv.org/abs/2510.16380v2`
- **Source URL:** `https://github.com/coleaniblett/MoReBench-Inspect/blob/<40-char SHA>/src/morebench/morebench.py#L56`
  - Line 56 is `def morebench_theory(` on `t12/validity-review`. Check the line at the pinned commit.
- **Maintainers:** leave blank.

If the form has room for a note:

> MoReBench-Theory from the same paper and code: 150 rows, 30 dilemmas each posed under five named ethical theories. Same file, judge and scoring as `morebench`, submitted in a separate issue. The score is also broken down by theory.

## What the bot's pull request should contain

The bot writes the register entries itself. These drafts follow [`register/example_eval.yaml`](https://github.com/UKGovernmentBEIS/inspect_evals/blob/f79b8be47d54e1165f9c82df77c3e3bc47b2894a/register/example_eval.yaml) and the repo's `src/morebench/eval.yaml`, so the bot's output can be checked against them. `id` comes from the directory name and is not set in the file. `contributors` and `tags` are deprecated and left out.

`register/morebench/eval.yaml`:

```yaml
full_title: "MoReBench: Procedural and Pluralistic Moral Reasoning"
common_title: "MoReBench"
paper_title: "MoReBench: Evaluating Procedural and Pluralistic Moral Reasoning in Language Models, More than Outcomes"
description: |
  Evaluates the moral reasoning process of language models. A model is given a moral
  dilemma and asked for its reasoning and decision. A judge model then checks the
  response against 20 to 47 weighted, expert-written rubric criteria, one criterion per
  call, and the score is the share of rubric weight earned.
arxiv: "https://arxiv.org/abs/2510.16380v2"
metadata:
  fast: false  # each sample makes one judge call per criterion for each judged text, 40 to 94 calls
tasks:
  - name: morebench
    task_path: src/morebench/morebench.py
source:
  repository_url: https://github.com/coleaniblett/MoReBench-Inspect
  repository_commit: <40-char SHA>
  comment: "Port of morebench/morebench (branch eval) at e6689bbb9d742c48ea78ea07acd7931eba05b213."
# evaluation_report: added from T11's runs.
```

`register/morebench_theory/eval.yaml` is the same, with these changes:

```yaml
full_title: "MoReBench-Theory: Moral Reasoning Within Named Ethical Theories"
common_title: "MoReBench-Theory"
description: |
  MoReBench's theory subset: 30 moral dilemmas, each posed under five named ethical
  theories, 150 rows in all. The model reasons within the named theory, and a judge
  checks the response against weighted, expert-written rubric criteria, one per call.
  The score is the share of rubric weight earned, also broken down by theory.
tasks:
  - name: morebench_theory
    task_path: src/morebench/morebench.py
```

`morebench_theory`'s `full_title` and `description` are new wording. The repo's `eval.yaml` has one title and description for both tasks.
