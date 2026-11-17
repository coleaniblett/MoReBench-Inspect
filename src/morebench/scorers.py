"""The judge scorers, and reading the judged text out of a model's reply.

MoReBench judges two texts from each reply: the thinking trace and the final response.
Each has its own scorer, named after upstream's name for the text, so every metric in
the log says which text it describes. A scorer asks the judge about one rubric
criterion per call and scores the replies with the rule in `scoring.py`. A third
scorer, `no_text`, calls no model: it counts the samples with no text to judge.
"""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Literal

from inspect_ai.model import (
    ChatMessageAssistant,
    ContentReasoning,
    ContentText,
    GenerateConfig,
    Model,
    get_model,
)
from inspect_ai.scorer import Score, Scorer, Target, scorer
from inspect_ai.solver import TaskState
from inspect_ai.util import collect
from inspect_evals_utils.scorers import GRADER_FAILED, NO_RESPONSE, VerdictParseFailure

from morebench.prompts import judge_prompt
from morebench.scoring import (
    is_fulfilled,
    is_standard_reply,
    judge_metrics,
    no_text_share,
    score_value,
    strict_verdict,
)

TRACE_SEPARATOR = "\n"

JudgeTarget = Literal["both", "thinking_trace", "model_resp"]

# The judge (DECISIONS.md D-05): upstream's model and settings, from
# morebench/morebench at e6689bb (MIT), run_best_judge_on_responses.py L23 and
# utils.py L197-L215. Inspect merges these settings beneath a bound `grader` role, so a
# setting the binding names wins and every other one is upstream's (D-22).
GRADER_ROLE = "grader"
DEFAULT_GRADER = "openrouter/openai/gpt-oss-120b"
DEFAULT_GRADER_CONFIG = GenerateConfig(
    temperature=1, top_p=1, max_tokens=10500, reasoning_effort="high"
)

# Further attempts after an empty reply, as upstream retries a None reply:
# run_best_judge_on_responses.py L82-L85 (D-04).
JUDGE_RETRIES = 3

# Explanations for a sample whose judged text is empty (D-07, D-21).
NO_TRACE_EXPLANATION = "no reasoning trace"
NO_RESPONSE_EXPLANATION = "no response"


def reasoning_text(block: ContentReasoning) -> str:
    """Return the readable text of one reasoning block.

    Providers fill the block differently. When it is redacted, `reasoning` holds an
    encrypted payload (OpenAI) or a signature (Anthropic) and the readable text, if
    any, is in `summary`. Otherwise `reasoning` is the trace itself (OpenRouter).
    """
    if block.redacted:
        return block.summary or ""
    return block.reasoning or block.summary or ""


def extract_trace(message: ChatMessageAssistant) -> str:
    """Return the thinking trace of a reply, or an empty string if it has none.

    The texts of the reasoning blocks are joined in order, one per line, and stripped.
    """
    # Follows morebench/morebench at e6689bb (MIT), utils.py L112-L126: each thinking
    # block followed by a newline, then stripped.
    if isinstance(message.content, str):
        return ""
    texts = [
        reasoning_text(block) for block in message.content if isinstance(block, ContentReasoning)
    ]
    return TRACE_SEPARATOR.join(texts).strip()


def extract_response(message: ChatMessageAssistant) -> str:
    """Return the final response of a reply, or an empty string if it has none.

    The text blocks are concatenated with nothing between them and stripped. Reasoning
    is never included.
    """
    # Follows morebench/morebench at e6689bb (MIT), utils.py L112-L122. `message.text`
    # is not used because it puts a newline between text blocks.
    if isinstance(message.content, str):
        return message.content.strip()
    texts = [block.text for block in message.content if isinstance(block, ContentText)]
    return "".join(texts).strip()


@dataclass(frozen=True)
class JudgeReply:
    """The judge's last reply for one criterion.

    Attributes:
        text: The reply, as the judge wrote it.
        attempts: How many calls were made, from 1 to 1 + JUDGE_RETRIES.
        problem: Why the reply is unusable, or None if it is usable.
    """

    text: str
    attempts: int
    problem: str | None


def reply_problem(text: str, strict: bool) -> str | None:
    """Return why a judge reply is unusable, or None if it can be scored.

    An empty reply is unusable (D-04). Under the strict reading, so is a reply that
    reading cannot read (D-22). Under upstream's rule any other reply is usable, even one
    that contains neither `yes` nor `no`: it earns nothing (D-03).
    """
    if not text.strip():
        return "empty reply"
    if strict:
        verdict = strict_verdict(text)
        if isinstance(verdict, VerdictParseFailure):
            return verdict.detail
    return None


async def ask_judge(grader: Model, prompt: str, strict: bool) -> JudgeReply:
    """Ask the judge about one criterion, retrying an unusable reply.

    Retries resend the same prompt with the cache off, so a cached reply is never
    served again. An error from the model API is not caught: Inspect has already
    retried it, and the sample then fails as upstream's row does (D-04).
    """
    text = ""
    problem = None
    for attempt in range(1 + JUDGE_RETRIES):
        if attempt == 0:
            output = await grader.generate(prompt)
        else:
            output = await grader.generate(prompt, cache=False)
        text = output.completion
        problem = reply_problem(text, strict)
        if problem is None:
            return JudgeReply(text=text, attempts=attempt + 1, problem=None)
    return JudgeReply(text=text, attempts=1 + JUDGE_RETRIES, problem=problem)


def reasoning_blocks(message: ChatMessageAssistant) -> int:
    """Count the reasoning blocks in a reply (D-08 expects one)."""
    if isinstance(message.content, str):
        return 0
    return sum(isinstance(block, ContentReasoning) for block in message.content)


async def judge_text(
    state: TaskState,
    grader: Model,
    extract: Callable[[ChatMessageAssistant], str],
    empty_explanation: str,
    strict: bool,
) -> Score:
    """Judge one text of the reply against every rubric criterion and score it.

    Args:
        state: The sample after generation.
        grader: The judge.
        extract: `extract_trace` or `extract_response`.
        empty_explanation: The explanation when the text is empty.
        strict: Read the judge's replies strictly (D-22).
    """
    message = state.output.message
    generation = {
        "stop_reason": state.output.stop_reason,
        "reasoning_blocks": reasoning_blocks(message),
    }
    text = extract(message)
    if not text:
        # D-07 and D-21: nothing to judge, so no judge calls and no score.
        return Score.unscored(
            reason=NO_RESPONSE, answer=text, explanation=empty_explanation, metadata=generation
        )

    criteria: list[dict[str, Any]] = state.metadata["rubric"]
    # One call per criterion, all at once (R-JUDGE-1, R-JUDGE-7).
    replies = await collect(
        *(ask_judge(grader, judge_prompt(text, c["title"]), strict) for c in criteria)
    )
    failed = [
        {"criterion_id": c["id"], "reply": r.text, "problem": r.problem}
        for c, r in zip(criteria, replies, strict=True)
        if r.problem is not None
    ]
    if failed:
        # D-04: never score on the criteria that did get a reply, but keep every reply.
        every_reply = [
            {
                "criterion_id": c["id"],
                "weight": c["weight"],
                "dimension": c["dimension"],
                "reply": r.text,
                "attempts": r.attempts,
                "problem": r.problem,
            }
            for c, r in zip(criteria, replies, strict=True)
        ]
        return Score.unscored(
            reason=GRADER_FAILED,
            answer=text,
            explanation=(
                f"no usable judge reply for {len(failed)} of {len(criteria)} criteria after "
                f"{1 + JUDGE_RETRIES} attempts each; first: criterion "
                f"{failed[0]['criterion_id']} ({failed[0]['problem']})"
            ),
            metadata={
                **generation,
                "strict_verdicts": strict,
                "failed_criteria": failed,
                "replies": every_reply,
            },
        )

    judgements = [reply.text for reply in replies]
    verdicts = [
        {
            "criterion_id": c["id"],
            "weight": c["weight"],
            "dimension": c["dimension"],
            "reply": reply.text,
            "fulfilled": is_fulfilled(c["weight"], reply.text, strict),
        }
        for c, reply in zip(criteria, replies, strict=True)
    ]
    fulfilled = sum(verdict["fulfilled"] for verdict in verdicts)
    return Score(
        value=score_value(criteria, judgements, text, strict),
        answer=text,
        explanation=f"{fulfilled} of {len(criteria)} criteria fulfilled",
        metadata={
            **generation,
            "strict_verdicts": strict,
            "nonstandard_replies": sum(not is_standard_reply(j) for j in judgements),
            "judge_retries": sum(reply.attempts - 1 for reply in replies),
            "verdicts": verdicts,
        },
    )


@scorer(metrics=judge_metrics())
def thinking_trace(strict_verdicts: bool = False) -> Scorer:
    """Judge the thinking trace against the sample's rubric.

    Args:
        strict_verdicts: Read the judge's replies strictly (D-22) instead of with
            upstream's substring rule.
    """

    async def score(state: TaskState, target: Target) -> Score:
        grader = get_model(role=GRADER_ROLE, default=DEFAULT_GRADER, config=DEFAULT_GRADER_CONFIG)
        return await judge_text(state, grader, extract_trace, NO_TRACE_EXPLANATION, strict_verdicts)

    return score


@scorer(metrics=judge_metrics())
def model_resp(strict_verdicts: bool = False) -> Scorer:
    """Judge the final response against the sample's rubric.

    Args:
        strict_verdicts: Read the judge's replies strictly (D-22) instead of with
            upstream's substring rule.
    """

    async def score(state: TaskState, target: Target) -> Score:
        grader = get_model(role=GRADER_ROLE, default=DEFAULT_GRADER, config=DEFAULT_GRADER_CONFIG)
        return await judge_text(
            state, grader, extract_response, NO_RESPONSE_EXPLANATION, strict_verdicts
        )

    return score


@scorer(metrics=[no_text_share()])
def no_text() -> Scorer:
    """Record, for each judged text, whether the reply had none. Makes no model calls.

    A judge scorer leaves a sample with no text to judge unscored (D-07, D-21), and no
    metric sees an unscored sample. This scorer flags those samples, 1 for no text and 0
    for text found, so the run reports their share for each judged text whatever the
    judge target. A sample left unscored because the judge failed (D-04) had text, so it
    is never counted.
    """

    async def score(state: TaskState, target: Target) -> Score:
        message = state.output.message
        missing = {
            "thinking_trace": not extract_trace(message),
            "model_resp": not extract_response(message),
        }
        empty = [text for text, is_missing in missing.items() if is_missing]
        return Score(
            value={text: float(is_missing) for text, is_missing in missing.items()},
            explanation=f"no text for {' and '.join(empty)}" if empty else "both texts found",
        )

    return score


JUDGE_SCORERS = {
    "both": (thinking_trace, model_resp),
    "thinking_trace": (thinking_trace,),
    "model_resp": (model_resp,),
}


def judge_scorers(judge_target: JudgeTarget, strict_verdicts: bool) -> list[Scorer]:
    """Return the scorers for a judge target: one per judged text (D-16).

    Raises:
        ValueError: If the judge target is not one of `JudgeTarget`.
    """
    if judge_target not in JUDGE_SCORERS:
        raise ValueError(f"judge_target must be one of {list(JUDGE_SCORERS)}, not {judge_target!r}")
    return [make(strict_verdicts) for make in JUDGE_SCORERS[judge_target]]
