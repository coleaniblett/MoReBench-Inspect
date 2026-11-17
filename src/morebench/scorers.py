"""Reading the judged text out of a model's reply.

MoReBench judges one of two texts from each reply: the thinking trace or the final
response. The judge scorer that uses them is added in a later task.
"""

from inspect_ai.model import ChatMessageAssistant, ContentReasoning, ContentText

TRACE_SEPARATOR = "\n"


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
