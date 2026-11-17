from typing import Any

import pytest
from inspect_ai import eval
from inspect_ai.dataset import MemoryDataset
from pytest_inspect_evals.assertions import assert_eval_success
from pytest_mock import MockerFixture

from morebench import morebench
from morebench.dataset import PUBLIC_CONFIG, record_to_sample
from morebench.morebench import EVAL_VERSION
from morebench.prompts import NEUTRAL_TEMPLATE


def test_version_comes_from_eval_yaml() -> None:
    assert EVAL_VERSION == "1-A"


def test_generation_settings(mocker: MockerFixture, public_row0: dict[str, Any]) -> None:
    # DECISIONS.md D-06.
    mocker.patch(
        "morebench.morebench.load_morebench_dataset",
        return_value=MemoryDataset([record_to_sample(public_row0)]),
    )
    config = morebench().config
    assert config.max_tokens == 10500
    assert config.reasoning_effort == "high"
    assert config.reasoning_summary == "auto"
    # A budget makes Inspect raise an error on Claude 4.7 and later.
    assert config.reasoning_tokens is None
    # Sampling settings are left to the command line.
    assert config.temperature is None
    assert config.top_p is None


def test_end_to_end_with_mock_model(mocker: MockerFixture, public_row0: dict[str, Any]) -> None:
    # Offline: the loader is replaced by one real row. There is no scorer yet, so this
    # checks that the prompt reaches the model and a response comes back.
    load = mocker.patch(
        "morebench.morebench.load_morebench_dataset",
        return_value=MemoryDataset([record_to_sample(public_row0)]),
    )
    [log] = eval(tasks=morebench(), model="mockllm/model")
    load.assert_called_once_with(PUBLIC_CONFIG)
    assert_eval_success(log, require_scorer=False, expected_sample_count=1)
    assert log.samples is not None
    [sample] = log.samples
    assert sample.id == "morebench_999672f2"
    assert sample.input == NEUTRAL_TEMPLATE + public_row0["DILEMMA"]
    # One user message and no system message (R-GEN-1), then the model's reply.
    assert [message.role for message in sample.messages] == ["user", "assistant"]
    assert sample.output.completion


@pytest.mark.dataset_download
@pytest.mark.huggingface
def test_end_to_end_with_mock_model_on_the_real_dataset() -> None:
    [log] = eval(tasks=morebench(), model="mockllm/model", limit=5)
    assert_eval_success(log, require_scorer=False, expected_sample_count=5)
    assert log.eval.dataset.samples == 500
    assert log.samples is not None
    for sample in log.samples:
        assert isinstance(sample.input, str)
        assert sample.input.startswith(NEUTRAL_TEMPLATE)
        assert set(sample.metadata) >= {
            "rubric",
            "dilemma_source",
            "dilemma_type",
            "role_domain",
            "theory",
            "row_index",
        }
