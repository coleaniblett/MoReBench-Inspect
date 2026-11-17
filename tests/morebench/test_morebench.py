import math
from typing import Any

import pytest
from inspect_ai import eval
from inspect_ai.dataset import MemoryDataset
from inspect_ai.log import EvalLog
from inspect_ai.model import (
    ChatMessageAssistant,
    ContentReasoning,
    ContentText,
    GenerateConfig,
    ModelOutput,
    get_model,
)
from pytest_inspect_evals.assertions import assert_eval_success
from pytest_mock import MockerFixture

from morebench import morebench
from morebench.dataset import PUBLIC_CONFIG, record_to_sample
from morebench.morebench import EVAL_VERSION
from morebench.prompts import NEUTRAL_TEMPLATE
from morebench.scorers import DEFAULT_GRADER, DEFAULT_GRADER_CONFIG, GRADER_ROLE
from tests.morebench.conftest import Judge, always

TRACE = "We need to weigh the duty to follow advice against the duty to my values."
RESPONSE = "Decision: start the medication, with a review after three months."
# Not a JudgeTarget; typed Any so the type checker lets a test pass it.
UNKNOWN_TARGET: Any = "trace"


def test_version_comes_from_eval_yaml() -> None:
    assert EVAL_VERSION == "1-A"


def use_rows(mocker: MockerFixture, *rows: dict[str, Any]) -> Any:
    # Offline: the loader is replaced by real rows from tests/morebench/data.
    return mocker.patch(
        "morebench.morebench.load_morebench_dataset",
        return_value=MemoryDataset([record_to_sample(row) for row in rows]),
    )


def model_under_test(trace: str = TRACE, response: str = RESPONSE) -> Any:
    content = [ContentReasoning(reasoning=trace), ContentText(text=response)]
    reply = ModelOutput.from_message(ChatMessageAssistant(content=content))
    return get_model("mockllm/model", custom_outputs=lambda *args: reply, memoize=False)


def run(mocker: MockerFixture, judge: Judge, *rows: dict[str, Any], **task_args: Any) -> EvalLog:
    use_rows(mocker, *rows)
    [log] = eval(
        tasks=morebench(**task_args),
        model=model_under_test(),
        model_roles={GRADER_ROLE: judge.model()},
        display="none",
    )
    assert_eval_success(log, expected_sample_count=len(rows))
    return log


def test_generation_settings(mocker: MockerFixture, public_row0: dict[str, Any]) -> None:
    # DECISIONS.md D-06.
    use_rows(mocker, public_row0)
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
    load = use_rows(mocker, public_row0)
    judge = always("yes")
    [log] = eval(
        tasks=morebench(),
        model="mockllm/model",
        model_roles={GRADER_ROLE: judge.model()},
        display="none",
    )
    load.assert_called_once_with(PUBLIC_CONFIG)
    assert_eval_success(log, expected_sample_count=1)
    assert log.samples is not None
    [sample] = log.samples
    assert sample.id == "morebench_999672f2"
    assert sample.input == NEUTRAL_TEMPLATE + public_row0["DILEMMA"]
    # One user message and no system message (R-GEN-1), then the model's reply.
    assert [message.role for message in sample.messages] == ["user", "assistant"]
    # mockllm's default reply has no reasoning block: the trace is unscored (D-07) and
    # only the final response is judged, once per criterion.
    assert sample.scores is not None
    assert sample.scores["thinking_trace"].explanation == "no reasoning trace"
    assert sample.scores["model_resp"].explanation == "26 of 28 criteria fulfilled"
    assert sample.scores["no_text"].value == {"thinking_trace": 1.0, "model_resp": 0.0}
    assert len(judge.calls) == 28


def test_both_targets_score_one_generation_twice(
    mocker: MockerFixture, public_row0: dict[str, Any], public_row405: dict[str, Any]
) -> None:
    # D-16: the default judges both texts, one scorer each, from the same generation.
    judge = always("yes")
    log = run(mocker, judge, public_row0, public_row405)
    assert log.results is not None
    assert [s.name for s in log.results.scores] == ["thinking_trace", "model_resp", "no_text"]
    for result in log.results.scores[:2]:
        # Row 0 all yes is 55 / 61 (G8); row 405 all yes is 45 / 51.
        expected = (100 * 55 / 61 + 100 * 45 / 51) / 2
        assert result.metrics["regular"].value == pytest.approx(expected)
        assert result.scored_samples == 2
    # One generation per sample, then one judge call per criterion for each text.
    assert len(judge.calls) == 2 * (28 + 20)
    assert log.samples is not None
    sample = log.samples[0]
    assert len([m for m in sample.messages if m.role == "assistant"]) == 1
    assert sample.scores is not None
    assert sample.scores["thinking_trace"].answer == TRACE
    assert sample.scores["model_resp"].answer == RESPONSE
    assert sample.scores["thinking_trace"].as_dict()["length"] == len(TRACE)
    assert sample.scores["model_resp"].as_dict()["length"] == len(RESPONSE)


@pytest.mark.parametrize(
    ("judge_target", "judged"), [("thinking_trace", TRACE), ("model_resp", RESPONSE)]
)
def test_a_single_judge_target(
    mocker: MockerFixture, public_row0: dict[str, Any], judge_target: str, judged: str
) -> None:
    judge = always("no")
    log = run(mocker, judge, public_row0, judge_target=judge_target)
    assert log.results is not None
    result, coverage = log.results.scores
    assert result.name == judge_target
    assert result.metrics["regular"].value == pytest.approx(100 * 6 / 61)
    # The no-text share is still reported for both texts (D-07, D-21).
    assert coverage.name == "no_text"
    assert len(judge.calls) == 28
    assert all(p.startswith(f"Reasoning Response:{judged}\n") for p in judge.prompts)


# The metric names the log shows for one judged text of public rows 0 and 405: both
# rows are daily dilemmas, long cases and AI-advisor scenarios, and together they have
# five of the six dimensions and the weights -3, 1, 2 and 3.
ROWS_0_AND_405_METRICS = [
    "regular",
    "stderr",
    "length",
    "hard",
    "daily_dilemmas",
    "ai_advisor",
    "long_case",
    "dimension_clear_process",
    "dimension_harmless_outcome",
    "dimension_helpful_outcome",
    "dimension_identifying",
    "dimension_logical_process",
    "weight_-3",
    "weight_1",
    "weight_2",
    "weight_3",
]


def test_every_metric_is_reported_for_both_texts(
    mocker: MockerFixture, public_row0: dict[str, Any], public_row405: dict[str, Any]
) -> None:
    # ARCHITECTURE.md § Metrics: each judge scorer carries every metric, and its length
    # and hard are those of the text it judged.
    log = run(mocker, always("yes"), public_row0, public_row405)
    assert log.results is not None
    trace, response, coverage = log.results.scores
    expected_regular = (100 * 55 / 61 + 100 * 45 / 51) / 2
    for result, text in ((trace, TRACE), (response, RESPONSE)):
        metrics = {name: metric.value for name, metric in result.metrics.items()}
        assert list(metrics) == ROWS_0_AND_405_METRICS
        assert metrics["regular"] == pytest.approx(expected_regular)
        assert metrics["length"] == len(text)
        assert metrics["hard"] == pytest.approx(expected_regular * 1000 / len(text))
        # Every sample is in each category, so each category's mean is the run's.
        for category in ("daily_dilemmas", "ai_advisor", "long_case"):
            assert metrics[category] == pytest.approx(expected_regular)
        # All yes: every positive criterion met, no negative one avoided.
        assert metrics["weight_-3"] == 0
        assert metrics["weight_3"] == 100
    assert {name: m.value for name, m in coverage.metrics.items()} == {
        "thinking_trace": 0.0,
        "model_resp": 0.0,
    }


@pytest.mark.parametrize("judge_target", ["both", "thinking_trace", "model_resp"])
def test_no_text_is_attached_for_every_judge_target(
    mocker: MockerFixture, public_row0: dict[str, Any], judge_target: str
) -> None:
    # The owner's ruling of 2026-11-17 (D-07): the share comes from its own scorer,
    # attached whatever the judge target, and it makes no judge calls.
    judge = always("yes")
    log = run(mocker, judge, public_row0, judge_target=judge_target)
    assert log.results is not None
    coverage = log.results.scores[-1]
    assert coverage.name == "no_text"
    assert coverage.scored_samples == 1
    assert list(coverage.metrics) == ["thinking_trace", "model_resp"]
    judged_texts = 2 if judge_target == "both" else 1
    assert len(judge.calls) == 28 * judged_texts


def test_a_sample_with_no_trace_is_in_the_share_and_not_in_the_trace_metrics(
    mocker: MockerFixture, public_row0: dict[str, Any], public_row405: dict[str, Any]
) -> None:
    # D-07: mockllm's default reply has no reasoning block. The trace scorer leaves both
    # samples unscored, so every trace metric is NaN, and the share says why.
    use_rows(mocker, public_row0, public_row405)
    [log] = eval(
        tasks=morebench(),
        model="mockllm/model",
        model_roles={GRADER_ROLE: always("yes").model()},
        display="none",
    )
    assert_eval_success(log, expected_sample_count=2)
    assert log.results is not None
    trace, response, coverage = log.results.scores
    assert trace.unscored_samples == 2
    assert all(math.isnan(metric.value) for metric in trace.metrics.values())
    assert list(trace.metrics) == [
        "regular",
        "stderr",
        "length",
        "hard",
        "category_regular",
        "dimension_rate",
        "weight_rate",
    ]
    assert response.scored_samples == 2
    assert {name: m.value for name, m in coverage.metrics.items()} == {
        "thinking_trace": 1.0,
        "model_resp": 0.0,
    }


def test_strict_verdicts_reach_the_scorers(
    mocker: MockerFixture, public_row0: dict[str, Any]
) -> None:
    # D-22: a reply the strict reading cannot read is retried, then unscored.
    judge = always("I do not know")
    log = run(mocker, judge, public_row0, strict_verdicts=True)
    assert log.results is not None
    *judged, coverage = log.results.scores
    for result in judged:
        assert result.scored_samples == 0
        assert result.unscored_samples == 1
    # A judge failure is not a missing text, so the no-text share stays 0 (D-04, D-07).
    assert {name: m.value for name, m in coverage.metrics.items()} == {
        "thinking_trace": 0.0,
        "model_resp": 0.0,
    }
    assert log.samples is not None
    assert log.samples[0].scores is not None
    for name in ("thinking_trace", "model_resp"):
        score = log.samples[0].scores[name]
        assert isinstance(score.value, float)
        assert math.isnan(score.value)
        assert score.reason == "grader_failed"


def test_a_bound_judge_keeps_its_settings_and_gets_upstreams_for_the_rest(
    mocker: MockerFixture, public_row0: dict[str, Any]
) -> None:
    # D-22: with a binding such as --model-role grader="{model: ..., temperature: 0}",
    # the setting it names wins and every other judge setting is upstream's. The task's
    # generation settings never reach the judge.
    judge = always("yes")
    use_rows(mocker, public_row0)
    [log] = eval(
        tasks=morebench(),
        model=model_under_test(),
        model_roles={GRADER_ROLE: judge.model(GenerateConfig(temperature=0))},
        display="none",
    )
    assert_eval_success(log, expected_sample_count=1)
    assert len(judge.configs) == 56
    for config in judge.configs:
        # Named by the binding: the binding's value, not upstream's 1.
        assert config.temperature == 0
        # Not named by the binding: upstream's (R-JUDGE-3).
        assert config.top_p == 1
        assert config.max_tokens == 10500
        assert config.reasoning_effort == "high"
        # A generation setting of the task, which is not a judge setting.
        assert config.reasoning_summary is None


def test_an_unbound_judge_is_the_default_with_upstream_settings(
    mocker: MockerFixture, public_row0: dict[str, Any]
) -> None:
    # D-05: with no binding, the scorer asks for upstream's judge and settings. The
    # mock stands in for the OpenRouter model, so nothing leaves the machine.
    judge_model = always("yes").model()
    resolve = mocker.patch("morebench.scorers.get_model", return_value=judge_model)
    use_rows(mocker, public_row0)
    [log] = eval(tasks=morebench(), model=model_under_test(), display="none")
    assert_eval_success(log, expected_sample_count=1)
    assert resolve.call_count == 2
    resolve.assert_called_with(
        role=GRADER_ROLE, default=DEFAULT_GRADER, config=DEFAULT_GRADER_CONFIG
    )


def test_an_unknown_judge_target_fails_at_task_creation(
    mocker: MockerFixture, public_row0: dict[str, Any]
) -> None:
    use_rows(mocker, public_row0)
    with pytest.raises(ValueError, match="judge_target"):
        morebench(judge_target=UNKNOWN_TARGET)


@pytest.mark.dataset_download
@pytest.mark.huggingface
def test_end_to_end_with_mock_model_on_the_real_dataset() -> None:
    # The judge is bound to a mock, so no judge API is called.
    judge = always("yes")
    [log] = eval(
        tasks=morebench(),
        model="mockllm/model",
        model_roles={GRADER_ROLE: judge.model()},
        limit=5,
        display="none",
    )
    assert_eval_success(log, expected_sample_count=5)
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
    # mockllm returns no reasoning, so only the final response is judged.
    rubric_sizes = sum(len(sample.metadata["rubric"]) for sample in log.samples)
    assert len(judge.calls) == rubric_sizes
