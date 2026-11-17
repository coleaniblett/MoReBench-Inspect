from inspect_ai.model import ChatMessageAssistant, ContentReasoning, ContentText

from morebench.scorers import extract_response, extract_trace, reasoning_text

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
