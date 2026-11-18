import ast
from collections import Counter
from typing import Any

import pytest
from inspect_ai.dataset import Dataset, MemoryDataset, Sample
from pytest_inspect_evals.huggingface import (
    assert_huggingface_dataset_structure,
    get_dataset_infos_dict,
)
from pytest_mock import MockerFixture

from morebench.dataset import (
    DATASET_PATH,
    PUBLIC_CONFIG,
    THEORY_CONFIG,
    load_morebench_dataset,
    parse_rubric,
    record_to_sample,
    source_group,
)
from morebench.prompts import NEUTRAL_TEMPLATE, THEORY_DEFINITIONS, generation_prompt
from morebench.scoring import THEORY_CATEGORY_KEYS

COLUMNS = [
    "DILEMMA",
    "DILEMMA_SOURCE",
    "DILEMMA_TYPE",
    "THEORY",
    "RUBRIC",
    "ROLE_DOMAIN",
    "CONTEXT",
]
# ARCHITECTURE.md, golden cases G8 and G9.
PUBLIC_ROW0_WEIGHTS = [
    *[2, 2, 3, 3, 3, 3, 2, 2, 2, 2, 2, 1, 2, 2],
    *[2, 1, 1, 2, -3, 3, 3, 2, 2, 2, 3, 2, 1, -3],
]


def metadata_of(sample: Sample) -> dict[str, Any]:
    assert sample.metadata is not None
    return sample.metadata


def count(dataset: Dataset, key: str) -> dict[Any, int]:
    return dict(Counter(metadata_of(sample)[key] for sample in dataset))


def count_criteria(dataset: Dataset, key: str) -> dict[Any, int]:
    return dict(
        Counter(criterion[key] for sample in dataset for criterion in metadata_of(sample)["rubric"])
    )


def criteria_per_row(dataset: Dataset) -> list[int]:
    return [len(metadata_of(sample)["rubric"]) for sample in dataset]


# ---- offline: real rows from tests/morebench/data ------------------------------


def test_parse_rubric_public_row0(public_row0: dict[str, Any]) -> None:
    criteria = parse_rubric(public_row0["RUBRIC"])
    assert [criterion["weight"] for criterion in criteria] == PUBLIC_ROW0_WEIGHTS
    assert all(set(criterion) == {"id", "title", "weight", "dimension"} for criterion in criteria)
    assert criteria[0]["id"] == "cf7493d2-5b3d-4c9f-be29-37b4f75d8c7c"
    assert criteria[0]["title"].startswith("Briefly summarizes the moral dilemma")
    assert criteria[0]["dimension"] == "identifying"
    assert len({criterion["id"] for criterion in criteria}) == len(criteria)


@pytest.mark.parametrize("bad_weight", [0, 4, -4, 2.5, "3", True, None])
def test_parse_rubric_rejects_a_bad_weight(public_row0: dict[str, Any], bad_weight: Any) -> None:
    rubric = ast.literal_eval(public_row0["RUBRIC"])
    rubric[0]["weight"] = bad_weight
    with pytest.raises(ValueError, match="cf7493d2-5b3d-4c9f-be29-37b4f75d8c7c has weight"):
        parse_rubric(repr(rubric))


def test_parse_rubric_rejects_a_rubric_that_is_not_a_list(public_row0: dict[str, Any]) -> None:
    criterion = ast.literal_eval(public_row0["RUBRIC"])[0]
    with pytest.raises(ValueError, match="expected a list"):
        parse_rubric(repr(criterion))


def test_parse_rubric_rejects_text_that_is_not_a_literal(public_row0: dict[str, Any]) -> None:
    truncated = public_row0["RUBRIC"][:200]
    with pytest.raises(SyntaxError):
        parse_rubric(truncated)


def test_record_to_sample_public_row0(public_row0: dict[str, Any]) -> None:
    sample = record_to_sample(public_row0)
    assert sample.id == "morebench_999672f2"
    assert sample.input == NEUTRAL_TEMPLATE + public_row0["DILEMMA"]
    assert sample.target == ""
    metadata = metadata_of(sample)
    assert len(metadata["rubric"]) == 28
    assert {key: value for key, value in metadata.items() if key != "rubric"} == {
        "dilemma_source": "daily_dilemmas",
        "dilemma_source_group": "daily_dilemmas",
        "dilemma_type": "long_case",
        "role_domain": "ai_advisor",
        "theory": "neutral",
        "context": "Right & Duty & Justice",
    }


def test_record_to_sample_theory_row0(theory_row0: dict[str, Any]) -> None:
    sample = record_to_sample(theory_row0)
    assert sample.id == "morebench_a1b9b874"
    assert isinstance(sample.input, str)
    assert sample.input.startswith(
        "Provide corresponding reasoning and decision for the following scenario based on "
        "Scanlonian Contractualism. Theory Definition: Scanlonian contractualism is"
    )
    assert sample.input.endswith(theory_row0["DILEMMA"])
    metadata = metadata_of(sample)
    assert len(metadata["rubric"]) == 23
    assert {key: value for key, value in metadata.items() if key != "rubric"} == {
        "dilemma_source": "expert_written_collab",
        "dilemma_source_group": "expert_written",
        "dilemma_type": "expert_case",
        "role_domain": "ai_agent",
        "theory": "Scanlonian Contractualism",
        "context": "Professional Ethics",
    }


def test_record_to_sample_keeps_an_empty_context_as_none(theory_row72: dict[str, Any]) -> None:
    assert theory_row72["CONTEXT"] is None
    sample = record_to_sample(theory_row72)
    assert sample.id == "morebench_7af1a0c7"
    assert metadata_of(sample)["context"] is None
    assert metadata_of(sample)["theory"] == "Act Utilitarianism"


def test_the_same_dilemma_gets_a_different_id_under_each_theory(
    public_row0: dict[str, Any],
) -> None:
    ids = {
        record_to_sample({**public_row0, "THEORY": theory}).id
        for theory in ["neutral", *THEORY_DEFINITIONS]
    }
    assert len(ids) == 6


@pytest.mark.parametrize(
    ("dilemma_source", "group"),
    [
        ("daily_dilemmas", "daily_dilemmas"),
        ("ai_risk_dilemmas", "ai_risk"),
        ("expert_written_ethic_bowl", "expert_written"),
        ("expert_written_ethic_unwrapped", "expert_written"),
        ("expert_written_literature", "expert_written"),
        ("expert_written_collab", "expert_written"),
    ],
)
def test_source_group(dilemma_source: str, group: str) -> None:
    assert source_group(dilemma_source) == group


def test_the_loader_reads_the_pinned_revision_and_numbers_the_rows(
    mocker: MockerFixture, public_row0: dict[str, Any], public_row405: dict[str, Any]
) -> None:
    # Offline: Hugging Face is replaced by real rows, so the loader's own work is
    # checked without the marked tests below. The pins are SPEC.md §2's.
    rows = [public_row0, public_row405]
    load = mocker.patch(
        "morebench.dataset.hf_dataset",
        return_value=MemoryDataset([record_to_sample(row) for row in rows]),
    )
    dataset = load_morebench_dataset(PUBLIC_CONFIG)
    load.assert_called_once_with(
        path="morebench/morebench",
        name="morebench_public",
        split="test",
        revision="d900e89f942f784f8e0113935034b4f0541a0b55",
        sample_fields=record_to_sample,
    )
    # Each sample gets its position, as upstream identifies a scenario by its row, and
    # keeps the rest of its metadata.
    for row_index, (sample, row) in enumerate(zip(dataset, rows, strict=True)):
        assert metadata_of(sample) == {**metadata_of(record_to_sample(row)), "row_index": row_index}


# ---- against the pinned dataset on Hugging Face --------------------------------


@pytest.fixture(scope="module")
def public_dataset() -> Dataset:
    return load_morebench_dataset(PUBLIC_CONFIG)


@pytest.fixture(scope="module")
def theory_dataset() -> Dataset:
    return load_morebench_dataset(THEORY_CONFIG)


@pytest.mark.dataset_download
@pytest.mark.huggingface
def test_dataset_structure() -> None:
    config = {"splits": ["test"], "features": dict.fromkeys(COLUMNS, str)}
    assert_huggingface_dataset_structure(
        get_dataset_infos_dict(DATASET_PATH),
        {"configs": {PUBLIC_CONFIG: config, THEORY_CONFIG: config}},
    )


@pytest.mark.dataset_download
@pytest.mark.huggingface
def test_public_dataset_counts(public_dataset: Dataset) -> None:
    # REQUIREMENTS.md R-DATA-5 to R-DATA-7.
    assert len(public_dataset) == 500
    per_row = criteria_per_row(public_dataset)
    assert sum(per_row) == 11_450
    assert (min(per_row), max(per_row)) == (20, 47)
    assert count_criteria(public_dataset, "weight") == {
        -3: 633,
        -2: 239,
        -1: 69,
        1: 1_380,
        2: 5_324,
        3: 3_805,
    }
    assert count_criteria(public_dataset, "dimension") == {
        "identifying": 4_370,
        "logical process": 2_801,
        "helpful outcome": 1_791,
        "clear process": 1_584,
        "harmless outcome": 881,
        "other": 23,
    }
    assert count(public_dataset, "theory") == {"neutral": 500}
    assert count(public_dataset, "dilemma_source") == {
        "daily_dilemmas": 200,
        "ai_risk_dilemmas": 200,
        "expert_written_ethic_bowl": 51,
        "expert_written_ethic_unwrapped": 30,
        "expert_written_literature": 12,
        "expert_written_collab": 7,
    }
    assert count(public_dataset, "dilemma_source_group") == {
        "daily_dilemmas": 200,
        "ai_risk": 200,
        "expert_written": 100,
    }
    assert count(public_dataset, "dilemma_type") == {
        "short_case": 200,
        "long_case": 200,
        "expert_case": 100,
    }
    assert count(public_dataset, "role_domain") == {"ai_advisor": 293, "ai_agent": 207}
    assert count(public_dataset, "context").get(None, 0) == 0


@pytest.mark.dataset_download
@pytest.mark.huggingface
def test_theory_dataset_counts(theory_dataset: Dataset) -> None:
    # REQUIREMENTS.md R-DATA-5 to R-DATA-7.
    assert len(theory_dataset) == 150
    per_row = criteria_per_row(theory_dataset)
    assert sum(per_row) == 3_835
    assert (min(per_row), max(per_row)) == (20, 44)
    assert count_criteria(theory_dataset, "weight") == {
        -3: 255,
        -2: 57,
        -1: 9,
        1: 356,
        2: 1_595,
        3: 1_563,
    }
    assert count_criteria(theory_dataset, "dimension") == {
        "identifying": 1_326,
        "logical process": 1_051,
        "clear process": 765,
        "helpful outcome": 468,
        "harmless outcome": 224,
        "other": 1,
    }
    # D-10: no filter is applied, so no Theory row may be neutral.
    assert count(theory_dataset, "theory") == dict.fromkeys(THEORY_DEFINITIONS, 30)
    assert count(theory_dataset, "dilemma_source") == {
        "daily_dilemmas": 50,
        "ai_risk_dilemmas": 50,
        "expert_written_collab": 50,
    }
    assert count(theory_dataset, "dilemma_type") == {"long_case": 100, "expert_case": 50}
    assert count(theory_dataset, "role_domain") == {"ai_agent": 100, "ai_advisor": 50}
    assert count(theory_dataset, "context")[None] == 13


@pytest.mark.dataset_download
@pytest.mark.huggingface
def test_theory_rows_set_each_dilemma_once_under_every_theory(theory_dataset: Dataset) -> None:
    # R-DATA-6: 30 distinct dilemmas, each once under each of the five theories, and
    # every input is the theory template of its own row (R-TASK-2, R-GEN-3).
    theories_by_dilemma: dict[str, list[str]] = {}
    for sample in theory_dataset:
        theory = metadata_of(sample)["theory"]
        instruction = generation_prompt("", theory)
        assert isinstance(sample.input, str)
        assert sample.input.startswith(instruction)
        dilemma = sample.input.removeprefix(instruction)
        theories_by_dilemma.setdefault(dilemma, []).append(theory)
    assert len(theories_by_dilemma) == 30
    for theories in theories_by_dilemma.values():
        assert sorted(theories) == sorted(THEORY_DEFINITIONS)


@pytest.mark.dataset_download
@pytest.mark.huggingface
def test_theory_breakdown_values_are_distinct_across_keys(theory_dataset: Dataset) -> None:
    # R-SCORE-6: Theory is broken down by theory and by source group. The metric names
    # each entry by its value alone, so no value may occur under both keys.
    values = {key: count(theory_dataset, key) for key in THEORY_CATEGORY_KEYS}
    assert values == {
        "theory": dict.fromkeys(THEORY_DEFINITIONS, 30),
        "dilemma_source_group": {"daily_dilemmas": 50, "ai_risk": 50, "expert_written": 50},
    }
    assert set(values["theory"]).isdisjoint(values["dilemma_source_group"])


@pytest.mark.dataset_download
@pytest.mark.huggingface
def test_ids_are_unique_and_rows_keep_their_position(
    public_dataset: Dataset, theory_dataset: Dataset
) -> None:
    public_ids = [sample.id for sample in public_dataset]
    theory_ids = [sample.id for sample in theory_dataset]
    assert len(set(public_ids)) == 500
    assert len(set(theory_ids)) == 150
    assert set(public_ids).isdisjoint(theory_ids)
    assert [metadata_of(s)["row_index"] for s in public_dataset] == list(range(500))
    assert [metadata_of(s)["row_index"] for s in theory_dataset] == list(range(150))


@pytest.mark.dataset_download
@pytest.mark.huggingface
def test_loaded_rows_match_the_fixture_rows(
    public_dataset: Dataset,
    theory_dataset: Dataset,
    public_row0: dict[str, Any],
    public_row405: dict[str, Any],
    theory_row0: dict[str, Any],
    theory_row72: dict[str, Any],
) -> None:
    for loaded, row in [
        (public_dataset[0], public_row0),
        (public_dataset[405], public_row405),
        (theory_dataset[0], theory_row0),
        (theory_dataset[72], theory_row72),
    ]:
        expected = record_to_sample(row)
        assert loaded.id == expected.id
        assert loaded.input == expected.input
        assert {k: v for k, v in metadata_of(loaded).items() if k != "row_index"} == (
            expected.metadata
        )
