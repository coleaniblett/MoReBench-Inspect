"""Inspect port of MoReBench: evaluating the moral reasoning process of language models with rubric-based LLM-judge scoring"""

from inspect_ai import Task, task
from inspect_ai.model import GenerateConfig
from inspect_ai.solver import generate
from inspect_evals_utils.metadata import load_eval_version

from morebench.dataset import PUBLIC_CONFIG, load_morebench_dataset

# The version comes from eval.yaml, the file beside this module.
EVAL_VERSION = load_eval_version(__file__)

# Generation settings (DECISIONS.md D-06). The token limit is the paper's. Effort high
# is what the original sends to OpenAI and OpenRouter. No reasoning-token budget is set
# here: Inspect raises an error for one on Claude 4.7 and later.
MAX_TOKENS = 10500
REASONING_EFFORT = "high"
REASONING_SUMMARY = "auto"


@task
def morebench() -> Task:
    """MoReBench: reasoning and decisions on the 500 public moral dilemmas.

    Each scenario is sent as a single user message that asks for reasoning and a
    decision. The model is given 10,500 tokens and reasoning effort high, and asked
    for reasoning summaries where a provider returns only those. The judge scorer is
    not wired in yet, so the task generates responses without scoring them.

    Returns:
        A task that generates one response per scenario.
    """
    return Task(
        dataset=load_morebench_dataset(PUBLIC_CONFIG),
        solver=generate(),
        config=GenerateConfig(
            max_tokens=MAX_TOKENS,
            reasoning_effort=REASONING_EFFORT,
            reasoning_summary=REASONING_SUMMARY,
        ),
        version=EVAL_VERSION,
    )
