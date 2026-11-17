"""Inspect port of MoReBench: evaluating the moral reasoning process of language models with rubric-based LLM-judge scoring"""

from inspect_ai import Task, task
from inspect_ai.solver import generate
from inspect_evals_utils.metadata import load_eval_version

from morebench.dataset import PUBLIC_CONFIG, load_morebench_dataset

# The version comes from eval.yaml, the file beside this module.
EVAL_VERSION = load_eval_version(__file__)


@task
def morebench() -> Task:
    """MoReBench: reasoning and decisions on the 500 public moral dilemmas.

    Each scenario is sent as a single user message that asks for reasoning and a
    decision. The judge scorer is not wired in yet, so the task generates responses
    without scoring them.

    Returns:
        A task that generates one response per scenario.
    """
    return Task(
        dataset=load_morebench_dataset(PUBLIC_CONFIG),
        solver=generate(),
        version=EVAL_VERSION,
    )
