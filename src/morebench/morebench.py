"""Inspect port of MoReBench: evaluating the moral reasoning process of language models with rubric-based LLM-judge scoring"""

from inspect_ai import Task, task
from inspect_ai.model import GenerateConfig
from inspect_ai.solver import generate
from inspect_evals_utils.metadata import load_eval_version

from morebench.dataset import PUBLIC_CONFIG, THEORY_CONFIG, load_morebench_dataset
from morebench.scorers import JudgeTarget, judge_scorers, no_text

# The version comes from eval.yaml, the file beside this module.
EVAL_VERSION = load_eval_version(__file__)

# Generation settings (DECISIONS.md D-06). The token limit is the paper's. Effort high
# is what the original sends to OpenAI and OpenRouter. No reasoning-token budget is set
# here: Inspect raises an error for one on Claude 4.7 and later.
MAX_TOKENS = 10500
REASONING_EFFORT = "high"
REASONING_SUMMARY = "auto"


@task
def morebench(judge_target: JudgeTarget = "both", strict_verdicts: bool = False) -> Task:
    """MoReBench: reasoning and decisions on the 500 public moral dilemmas.

    Each scenario is sent as a single user message that asks for reasoning and a
    decision. The model is given 10,500 tokens and reasoning effort high, and asked
    for reasoning summaries where a provider returns only those. A judge then checks
    the judged text against each rubric criterion, one call per criterion. The judge
    is the `grader` model role, by default `openrouter/openai/gpt-oss-120b` with the
    original's settings.

    Args:
        judge_target: Which text the judge reads: `both` (the default), scored once
            for the thinking trace and once for the final response from the same
            generation; or only `thinking_trace` or `model_resp`.
        strict_verdicts: Read the judge's replies strictly, accepting only a reply
            that leads with yes or no, instead of with the original's substring rule.
            A reply the strict reading cannot read leaves the sample unscored.

    Returns:
        A task with one scorer per judged text, and a `no_text` scorer that reports
        the share of samples with no thinking trace and with no final response.
    """
    return Task(
        dataset=load_morebench_dataset(PUBLIC_CONFIG),
        solver=generate(),
        # The no-text share for both texts, whatever the judge target (D-07, D-21).
        scorer=[*judge_scorers(judge_target, strict_verdicts), no_text()],
        config=generation_config(),
        version=EVAL_VERSION,
    )


@task
def morebench_theory(judge_target: JudgeTarget = "both", strict_verdicts: bool = False) -> Task:
    """MoReBench-Theory: reasoning within a named ethical framework, on 150 scenarios.

    The 150 rows are 30 dilemmas, each set once under each of five theories: act
    utilitarianism, Kantian deontology, Aristotelian virtue ethics, Scanlonian
    contractualism and Gauthierian contractarianism. The prompt names the row's theory
    and gives its definition. Generation and judging are as in `morebench`; the score is
    also broken down by theory and by dilemma source.

    Args:
        judge_target: Which text the judge reads: `both` (the default), scored once
            for the thinking trace and once for the final response from the same
            generation; or only `thinking_trace` or `model_resp`.
        strict_verdicts: Read the judge's replies strictly, accepting only a reply
            that leads with yes or no, instead of with the original's substring rule.
            A reply the strict reading cannot read leaves the sample unscored.

    Returns:
        A task with one scorer per judged text, `theory_thinking_trace` and
        `theory_model_resp`, and a `no_text` scorer that reports the share of samples
        with no thinking trace and with no final response.
    """
    return Task(
        dataset=load_morebench_dataset(THEORY_CONFIG),
        solver=generate(),
        # The no-text share for both texts, whatever the judge target (D-07, D-21).
        scorer=[*judge_scorers(judge_target, strict_verdicts, theory=True), no_text()],
        config=generation_config(),
        version=EVAL_VERSION,
    )


def generation_config() -> GenerateConfig:
    """Return the generation settings both tasks use (D-06)."""
    # Upstream's Theory generation script copies the main one, settings included
    # (REQUIREMENTS.md § Sources and pins).
    return GenerateConfig(
        max_tokens=MAX_TOKENS,
        reasoning_effort=REASONING_EFFORT,
        reasoning_summary=REASONING_SUMMARY,
    )
