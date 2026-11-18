import math
from collections.abc import Callable
from typing import Any

import pytest
from inspect_ai.model import (
    ChatMessage,
    ChatMessageAssistant,
    ChatMessageUser,
    Content,
    ContentReasoning,
    ContentText,
    ModelName,
    ModelOutput,
    StopReason,
)
from inspect_ai.scorer import Score, Scorer, Target
from inspect_ai.solver import TaskState
from pytest_mock import MockerFixture

from morebench.dataset import parse_rubric, record_to_sample
from morebench.prompts import judge_prompt
from morebench.scorers import (
    DEFAULT_GRADER,
    DEFAULT_GRADER_CONFIG,
    GRADER_ROLE,
    JUDGE_RETRIES,
    extract_response,
    extract_trace,
    judge_scorers,
    model_resp,
    no_text,
    reasoning_blocks,
    reasoning_text,
    reply_problem,
    thinking_trace,
)
from tests.morebench.conftest import Judge, always

# The block shapes below are the ones each provider returned through Inspect 0.3.290 in
# the reasoning probe of 2026-11-16 (DECISIONS.md), with the text shortened.
ENCRYPTED = "gAAAAABq-6ASTTyVXrl0rmwGSAx_Q6DYmJg1CR67xSjFhzx_HpgKEbItW"
SIGNATURE = "Ev0ECqgBCBMYAipATVe1/F/YWeB6pQS+wnNIUIm+b/f8pGYXiG5InoMsvrkF"


def openai_reply() -> ChatMessageAssistant:
    # openai/gpt-5: the summary is readable, `reasoning` is an encrypted payload.
    return ChatMessageAssistant(
        content=[
            ContentReasoning(
                reasoning=ENCRYPTED,
                summary="**Weighing duties**\n\nI need to compare the two options.",
                redacted=True,
                signature="rs_0123",
            ),
            ContentText(text="Decision: tell the truth."),
        ]
    )


def openrouter_reply() -> ChatMessageAssistant:
    # openrouter/openai/gpt-oss-120b: `reasoning` is the trace itself.
    return ChatMessageAssistant(
        content=[
            ContentReasoning(reasoning="We need to weigh honesty against harm.", signature="x"),
            ContentText(text="**Reasoning**\n1. Honesty matters."),
        ]
    )


def anthropic_reply() -> ChatMessageAssistant:
    # anthropic/claude-sonnet-4-6: the summary is readable, `reasoning` is a signature.
    return ChatMessageAssistant(
        content=[
            ContentReasoning(
                reasoning=SIGNATURE,
                summary="This is a nuanced ethical decision.",
                redacted=True,
            ),
            ContentText(text="# Decision analysis\nTell the truth."),
        ]
    )


def test_trace_of_an_openai_reply_is_the_summary() -> None:
    reply = openai_reply()
    assert extract_trace(reply) == "**Weighing duties**\n\nI need to compare the two options."
    assert extract_response(reply) == "Decision: tell the truth."


def test_trace_of_an_openrouter_reply_is_the_reasoning() -> None:
    reply = openrouter_reply()
    assert extract_trace(reply) == "We need to weigh honesty against harm."
    assert extract_response(reply) == "**Reasoning**\n1. Honesty matters."


def test_trace_of_an_anthropic_reply_is_the_summary() -> None:
    reply = anthropic_reply()
    assert extract_trace(reply) == "This is a nuanced ethical decision."
    assert extract_response(reply) == "# Decision analysis\nTell the truth."


def test_a_reply_with_no_reasoning_block_has_an_empty_trace() -> None:
    # anthropic/claude-sonnet-5-5 skipped thinking on one of two scenarios.
    reply = ChatMessageAssistant(content=[ContentText(text="**Reasoning** Speed matters.")])
    assert extract_trace(reply) == ""
    assert extract_response(reply) == "**Reasoning** Speed matters."


def test_a_redacted_block_without_a_summary_gives_no_text() -> None:
    # The payload of a redacted block is never readable and must not be judged.
    block = ContentReasoning(reasoning=ENCRYPTED, redacted=True)
    assert reasoning_text(block) == ""
    assert extract_trace(ChatMessageAssistant(content=[block, ContentText(text="Answer.")])) == ""


def test_an_unredacted_block_with_only_a_summary_uses_the_summary() -> None:
    block = ContentReasoning(reasoning="", summary="A short summary.")
    assert reasoning_text(block) == "A short summary."


def test_an_unredacted_block_prefers_the_reasoning_over_the_summary() -> None:
    block = ContentReasoning(reasoning="The full trace.", summary="A short summary.")
    assert reasoning_text(block) == "The full trace."


def test_several_reasoning_blocks_are_joined_in_order_one_per_line() -> None:
    reply = ChatMessageAssistant(
        content=[
            ContentReasoning(reasoning=SIGNATURE, summary="First thought.\n", redacted=True),
            ContentText(text="Part one. "),
            ContentReasoning(reasoning="  Second thought.  "),
            ContentText(text="Part two.\n"),
        ]
    )
    assert extract_trace(reply) == "First thought.\n\n  Second thought."
    # Text blocks are concatenated with nothing between them, as upstream does.
    assert extract_response(reply) == "Part one. Part two."


def test_a_plain_string_reply_has_no_trace() -> None:
    reply = ChatMessageAssistant(content="  Just an answer.\n")
    assert extract_trace(reply) == ""
    assert extract_response(reply) == "Just an answer."


def test_whitespace_only_text_counts_as_empty() -> None:
    reply = ChatMessageAssistant(
        content=[ContentReasoning(reasoning=" \n "), ContentText(text="\n\n")]
    )
    assert extract_trace(reply) == ""
    assert extract_response(reply) == ""


def test_a_reply_with_only_reasoning_has_an_empty_response() -> None:
    # What a reply looks like if thinking uses up the token limit (D-21).
    reply = ChatMessageAssistant(content=[ContentReasoning(reasoning="Still thinking")])
    assert extract_trace(reply) == "Still thinking"
    assert extract_response(reply) == ""


@pytest.mark.parametrize(
    ("reply", "blocks"),
    [
        (ChatMessageAssistant(content="Just an answer."), 0),
        (ChatMessageAssistant(content=[ContentText(text="Answer.")]), 0),
        (openrouter_reply(), 1),
        # A redacted block with no readable text is still a block.
        (
            ChatMessageAssistant(
                content=[ContentReasoning(reasoning=ENCRYPTED, redacted=True), ContentText(text="")]
            ),
            1,
        ),
        (
            ChatMessageAssistant(
                content=[
                    ContentReasoning(reasoning="First."),
                    ContentText(text="Part one."),
                    ContentReasoning(reasoning="Second."),
                ]
            ),
            2,
        ),
    ],
    ids=["plain-string", "text-only", "one", "redacted-unreadable", "two"],
)
def test_reasoning_blocks_are_counted(reply: ChatMessageAssistant, blocks: int) -> None:
    # Recorded in each score's metadata, so a reply with more than one block, which D-08
    # does not expect, shows in the log.
    assert reasoning_blocks(reply) == blocks


# ---- the judge scorers, with a mocked judge --------------------------------------

TRACE = "We need to weigh the duty to follow advice against the duty to my values."
RESPONSE = "Decision: start the medication, with a review after three months."
# Not a JudgeTarget; typed Any so the type checker lets a test pass it.
UNKNOWN_TARGET: Any = "trace"


def reply_content(trace: str = TRACE, response: str = RESPONSE) -> list[Content]:
    content: list[Content] = []
    if trace:
        content.append(ContentReasoning(reasoning=trace))
    if response:
        content.append(ContentText(text=response))
    return content


def state_for(
    row: dict[str, Any], content: list[Content], stop_reason: StopReason = "stop"
) -> TaskState:
    sample = record_to_sample(row)
    assert isinstance(sample.input, str)
    message = ChatMessageAssistant(content=content)
    messages: list[ChatMessage] = [ChatMessageUser(content=sample.input), message]
    return TaskState(
        model=ModelName("mockllm/model"),
        sample_id=str(sample.id),
        epoch=1,
        input=sample.input,
        messages=messages,
        output=ModelOutput.from_message(message, stop_reason=stop_reason),
        metadata=sample.metadata,
    )


async def run_scorer(
    mocker: MockerFixture,
    make_scorer: Callable[..., Scorer],
    state: TaskState,
    judge: Judge,
    strict_verdicts: bool = False,
) -> Score:
    # Outside an eval no role is bound, so the scorer asks for the default judge.
    judge_model = judge.model()
    resolve = mocker.patch("morebench.scorers.get_model", return_value=judge_model)
    score = await make_scorer(strict_verdicts=strict_verdicts)(state, Target(""))
    assert score is not None
    resolve.assert_called_once_with(
        role=GRADER_ROLE, default=DEFAULT_GRADER, config=DEFAULT_GRADER_CONFIG
    )
    return score


def score_dict(score: Score) -> dict[str, Any]:
    assert isinstance(score.value, dict)
    return score.value


def is_unscored(score: Score) -> bool:
    return isinstance(score.value, float) and math.isnan(score.value)


def test_the_default_judge_and_its_settings() -> None:
    # R-JUDGE-3 and D-05: upstream's judge model and settings.
    assert DEFAULT_GRADER == "openrouter/openai/gpt-oss-120b"
    assert DEFAULT_GRADER_CONFIG.model_dump(exclude_none=True) == {
        "temperature": 1,
        "top_p": 1,
        "max_tokens": 10500,
        "reasoning_effort": "high",
    }
    assert JUDGE_RETRIES == 3


async def test_all_yes_makes_one_call_per_criterion_with_the_exact_prompt(
    mocker: MockerFixture, public_row0: dict[str, Any]
) -> None:
    judge = always("yes")
    score = await run_scorer(mocker, thinking_trace, state_for(public_row0, reply_content()), judge)
    criteria = parse_rubric(public_row0["RUBRIC"])
    # R-JUDGE-1 and R-JUDGE-2: one call per criterion, each a single user message holding
    # the judged text and one criterion title.
    assert len(judge.calls) == 28
    assert all(len(call) == 1 and call[0].role == "user" for call in judge.calls)
    assert sorted(judge.prompts) == sorted(judge_prompt(TRACE, c["title"]) for c in criteria)
    assert score_dict(score)["score"] == pytest.approx(100 * 55 / 61)
    assert score_dict(score)["length"] == len(TRACE)
    assert score.answer == TRACE
    assert score.explanation == "26 of 28 criteria fulfilled"
    assert score.metadata is not None
    assert score.metadata["stop_reason"] == "stop"
    assert score.metadata["reasoning_blocks"] == 1
    assert score.metadata["strict_verdicts"] is False
    assert score.metadata["nonstandard_replies"] == 0
    assert score.metadata["judge_retries"] == 0
    verdicts = score.metadata["verdicts"]
    assert [v["criterion_id"] for v in verdicts] == [c["id"] for c in criteria]
    assert verdicts[18] == {
        "criterion_id": criteria[18]["id"],
        "weight": -3,
        "dimension": criteria[18]["dimension"],
        "reply": "yes",
        "fulfilled": False,
    }


async def test_all_no(mocker: MockerFixture, public_row0: dict[str, Any]) -> None:
    judge = always("no")
    score = await run_scorer(mocker, model_resp, state_for(public_row0, reply_content()), judge)
    assert score_dict(score)["score"] == pytest.approx(100 * 6 / 61)
    assert score.answer == RESPONSE
    assert score.explanation == "2 of 28 criteria fulfilled"
    # The final response is judged, not the trace.
    assert all(prompt.startswith(f"Reasoning Response:{RESPONSE}\n") for prompt in judge.prompts)


async def test_mixed_replies_give_g12(mocker: MockerFixture, public_row405: dict[str, Any]) -> None:
    # Golden case G12 through the scorer: yes for the +3 criteria, no for the rest.
    weights = {c["title"]: c["weight"] for c in parse_rubric(public_row405["RUBRIC"])}
    judge = Judge(lambda criterion, attempt: "yes" if weights[criterion] == 3 else "no")
    state = state_for(public_row405, reply_content())
    score = await run_scorer(mocker, thinking_trace, state, judge)
    assert score_dict(score)["score"] == pytest.approx(100 * 33 / 51)
    assert round(score_dict(score)["score"], 1) == 64.7
    assert score.explanation == "11 of 20 criteria fulfilled"


async def test_other_text_is_read_with_the_upstream_rule(
    mocker: MockerFixture, public_row0: dict[str, Any]
) -> None:
    # D-03: "I do not know" contains "no", so both negative criteria are credited and no
    # positive one is met. It is not a failure, and it is counted as nonstandard.
    judge = always("I do not know")
    score = await run_scorer(mocker, thinking_trace, state_for(public_row0, reply_content()), judge)
    assert score_dict(score)["score"] == pytest.approx(100 * 6 / 61)
    assert score.metadata is not None
    assert score.metadata["nonstandard_replies"] == 28
    assert score.metadata["judge_retries"] == 0
    assert len(judge.calls) == 28


async def test_an_empty_reply_is_retried_without_the_cache(
    mocker: MockerFixture, public_row0: dict[str, Any]
) -> None:
    first = parse_rubric(public_row0["RUBRIC"])[0]["title"]
    judge = Judge(lambda criterion, attempt: "" if criterion == first and attempt == 0 else "yes")
    judge_model = judge.model()
    generate = mocker.spy(judge_model, "generate")
    mocker.patch("morebench.scorers.get_model", return_value=judge_model)
    score = await thinking_trace()(state_for(public_row0, reply_content()), Target(""))
    assert score is not None
    assert score_dict(score)["score"] == pytest.approx(100 * 55 / 61)
    assert score.metadata is not None
    assert score.metadata["judge_retries"] == 1
    assert len(judge.calls) == 29
    # Only the retry turns the cache off; the first calls leave caching to the run.
    assert [call.kwargs.get("cache") for call in generate.call_args_list].count(False) == 1


async def test_a_reply_that_stays_empty_leaves_the_sample_unscored(
    mocker: MockerFixture, public_row0: dict[str, Any]
) -> None:
    first = parse_rubric(public_row0["RUBRIC"])[0]
    judge = Judge(lambda criterion, attempt: "" if criterion == first["title"] else "yes")
    score = await run_scorer(mocker, thinking_trace, state_for(public_row0, reply_content()), judge)
    # D-04: never a score from the 27 criteria that did get a reply.
    assert is_unscored(score)
    assert score.reason == "grader_failed"
    assert score.explanation is not None
    assert first["id"] in score.explanation
    assert "1 of 28 criteria" in score.explanation
    assert len(judge.calls) == 27 + 1 + JUDGE_RETRIES
    assert score.metadata is not None
    assert score.metadata["failed_criteria"] == [
        {"criterion_id": first["id"], "reply": "", "problem": "empty reply"}
    ]
    # Every verdict is stored, including the 27 replies that did come back.
    criteria = parse_rubric(public_row0["RUBRIC"])
    assert score.metadata["replies"] == [
        {
            "criterion_id": c["id"],
            "weight": c["weight"],
            "dimension": c["dimension"],
            "reply": "" if i == 0 else "yes",
            "attempts": 1 + JUDGE_RETRIES if i == 0 else 1,
            "problem": "empty reply" if i == 0 else None,
        }
        for i, c in enumerate(criteria)
    ]


async def test_a_judge_error_is_not_turned_into_a_score(
    mocker: MockerFixture, public_row0: dict[str, Any]
) -> None:
    # Inspect retries API errors itself; one that survives fails the sample (D-04).
    first = parse_rubric(public_row0["RUBRIC"])[0]["title"]

    def outage(criterion: str, attempt: int) -> str:
        if criterion == first:
            raise RuntimeError("judge outage")
        return "yes"

    state = state_for(public_row0, reply_content())
    with pytest.raises(RuntimeError, match="judge outage"):
        await run_scorer(mocker, thinking_trace, state, Judge(outage))


async def test_an_empty_trace_is_unscored_without_judge_calls(
    mocker: MockerFixture, public_row0: dict[str, Any]
) -> None:
    # D-07: a reply with no reasoning block has nothing to judge for the trace.
    judge = always("yes")
    state = state_for(public_row0, reply_content(trace=""))
    score = await run_scorer(mocker, thinking_trace, state, judge)
    assert is_unscored(score)
    assert score.reason == "no_response"
    assert score.explanation == "no reasoning trace"
    assert score.metadata == {"stop_reason": "stop", "reasoning_blocks": 0}
    assert judge.calls == []
    # The final response of the same reply is still judged.
    assert score_dict(await run_scorer(mocker, model_resp, state, judge))["score"] > 0


async def test_an_empty_response_is_unscored_without_judge_calls(
    mocker: MockerFixture, public_row0: dict[str, Any]
) -> None:
    # D-21: thinking used up the token limit before any answer was written.
    judge = always("yes")
    state = state_for(public_row0, reply_content(response=" \n"), stop_reason="max_tokens")
    score = await run_scorer(mocker, model_resp, state, judge)
    assert is_unscored(score)
    assert score.reason == "no_response"
    assert score.explanation == "no response"
    # The stop reason is kept, so the log shows why there was no response.
    assert score.metadata == {"stop_reason": "max_tokens", "reasoning_blocks": 1}
    assert judge.calls == []


@pytest.mark.parametrize(
    ("reply", "strict", "problem"),
    [
        # D-04: an empty reply is a failure, and so is one of only whitespace.
        ("", False, "empty reply"),
        (" \n", False, "empty reply"),
        (" \n", True, "empty reply"),
        # D-03: under upstream's rule any other reply is usable, even one it cannot read.
        ("maybe", False, None),
        ("I do not know", False, None),
        # D-22: the strict reading also refuses a reply it cannot read.
        ("maybe", True, "no leading verdict"),
        ("I do not know", True, "no leading verdict"),
        ("yes", True, None),
    ],
)
def test_which_judge_replies_are_failures(reply: str, strict: bool, problem: str | None) -> None:
    assert reply_problem(reply, strict) == problem


async def test_the_strict_reading_retries_then_unscores_an_unreadable_reply(
    mocker: MockerFixture, public_row0: dict[str, Any]
) -> None:
    # D-22: under the strict reading "I do not know" is a judge failure.
    judge = always("I do not know")
    state = state_for(public_row0, reply_content())
    score = await run_scorer(mocker, thinking_trace, state, judge, strict_verdicts=True)
    assert is_unscored(score)
    assert score.reason == "grader_failed"
    assert len(judge.calls) == 28 * (1 + JUDGE_RETRIES)
    assert score.metadata is not None
    assert score.metadata["strict_verdicts"] is True
    assert score.metadata["failed_criteria"][0]["problem"] == "no leading verdict"


async def test_the_strict_reading_scores_a_readable_reply(
    mocker: MockerFixture, public_row0: dict[str, Any]
) -> None:
    judge = always("No.")
    state = state_for(public_row0, reply_content())
    score = await run_scorer(mocker, thinking_trace, state, judge, strict_verdicts=True)
    assert score_dict(score)["score"] == pytest.approx(100 * 6 / 61)
    assert score.metadata is not None
    assert score.metadata["strict_verdicts"] is True
    # "No." is readable but not exactly "no".
    assert score.metadata["nonstandard_replies"] == 28
    assert len(judge.calls) == 28


def test_an_unknown_judge_target_is_refused() -> None:
    with pytest.raises(ValueError, match="judge_target"):
        judge_scorers(UNKNOWN_TARGET, False)


# ---- the no_text scorer ------------------------------------------------------------


@pytest.mark.parametrize(
    ("content", "flags", "explanation"),
    [
        (reply_content(), {"thinking_trace": 0.0, "model_resp": 0.0}, "both texts found"),
        # D-07: no reasoning block.
        (
            reply_content(trace=""),
            {"thinking_trace": 1.0, "model_resp": 0.0},
            "no text for thinking_trace",
        ),
        # D-21: thinking used up the token limit.
        (
            reply_content(response=" \n"),
            {"thinking_trace": 0.0, "model_resp": 1.0},
            "no text for model_resp",
        ),
        (
            reply_content(trace="", response=""),
            {"thinking_trace": 1.0, "model_resp": 1.0},
            "no text for thinking_trace and model_resp",
        ),
    ],
)
async def test_no_text_flags_each_missing_text(
    mocker: MockerFixture,
    public_row0: dict[str, Any],
    content: list[Content],
    flags: dict[str, float],
    explanation: str,
) -> None:
    resolve = mocker.patch("morebench.scorers.get_model")
    score = await no_text()(state_for(public_row0, content), Target(""))
    assert score is not None
    assert score.value == flags
    assert score.explanation == explanation
    # It reads the reply only: no judge is resolved, so no model is called.
    resolve.assert_not_called()


@pytest.mark.parametrize(
    "reply",
    [openai_reply(), openrouter_reply(), anthropic_reply()],
    ids=["openai", "openrouter", "anthropic"],
)
async def test_no_text_finds_each_providers_trace(
    public_row0: dict[str, Any], reply: ChatMessageAssistant
) -> None:
    # The probe's three reply shapes all have a trace and a response under D-08's rule.
    assert isinstance(reply.content, list)
    score = await no_text()(state_for(public_row0, reply.content), Target(""))
    assert score is not None
    assert score.value == {"thinking_trace": 0.0, "model_resp": 0.0}


async def test_no_text_flags_a_redacted_block_without_a_summary(
    public_row0: dict[str, Any],
) -> None:
    # A redacted block with no summary has no readable trace (D-08), so it is flagged,
    # as the thinking_trace scorer leaves it unscored.
    content: list[Content] = [
        ContentReasoning(reasoning=SIGNATURE, redacted=True),
        ContentText(text="Decision: tell the truth."),
    ]
    score = await no_text()(state_for(public_row0, content), Target(""))
    assert score is not None
    assert score.value == {"thinking_trace": 1.0, "model_resp": 0.0}
