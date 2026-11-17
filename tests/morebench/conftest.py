import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from inspect_ai.model import ChatMessage, GenerateConfig, Model, ModelOutput, get_model
from inspect_ai.tool import ToolChoice, ToolInfo

# Real rows of the pinned dataset (CC BY 4.0), written by script from the CSVs at
# revision d900e89f. Empty cells are null, as `datasets` loads them.
DATA_DIR = Path(__file__).parent / "data"


def load_row(name: str) -> dict[str, Any]:
    return json.loads((DATA_DIR / f"{name}.json").read_text(encoding="utf-8"))


@pytest.fixture
def public_row0() -> dict[str, Any]:
    """Row 0 of morebench_public."""
    return load_row("morebench_public_row0")


@pytest.fixture
def public_row405() -> dict[str, Any]:
    """Row 405 of morebench_public: the Himalayan expedition, printed in the paper's Appendix B.2."""
    return load_row("morebench_public_row405")


@pytest.fixture
def theory_row0() -> dict[str, Any]:
    """Row 0 of morebench_theory (Scanlonian Contractualism)."""
    return load_row("morebench_theory_row0")


@pytest.fixture
def theory_row72() -> dict[str, Any]:
    """Row 72 of morebench_theory: the first row whose CONTEXT cell is empty."""
    return load_row("morebench_theory_row72")


class Judge:
    """A mock judge that replies by criterion and attempt, and records every call.

    `reply` gets the criterion title, read from the prompt, and how many times that
    prompt was sent before, and returns the judge's text. Used as mockllm's
    `custom_outputs`, it answers correctly however the concurrent calls are ordered.
    """

    def __init__(self, reply: Callable[[str, int], str]) -> None:
        self.reply = reply
        self.calls: list[list[ChatMessage]] = []
        self.configs: list[GenerateConfig] = []

    def __call__(
        self,
        input: list[ChatMessage],
        tools: list[ToolInfo],
        tool_choice: ToolChoice,
        config: GenerateConfig,
    ) -> ModelOutput:
        prompt = input[-1].text
        attempt = self.prompts.count(prompt)
        self.calls.append(input)
        self.configs.append(config)
        criterion = prompt.rsplit("Rubric Criterion:", 1)[1]
        return ModelOutput.from_content("mockllm/model", self.reply(criterion, attempt))

    @property
    def prompts(self) -> list[str]:
        return [call[-1].text for call in self.calls]

    def model(self, config: GenerateConfig | None = None) -> Model:
        """A mockllm model that answers with this judge, with its own settings."""
        return get_model(
            "mockllm/model", config=config or GenerateConfig(), custom_outputs=self, memoize=False
        )


def always(text: str) -> Judge:
    """A mock judge that gives the same reply to every criterion."""
    return Judge(lambda criterion, attempt: text)
