"""Loading MoReBench from Hugging Face and turning its rows into Inspect samples."""

import ast
from typing import Any

from inspect_ai.dataset import Dataset, Sample
from inspect_evals_utils import create_stable_id
from inspect_evals_utils.huggingface import hf_dataset

from morebench.prompts import generation_prompt

DATASET_PATH = "morebench/morebench"
DATASET_REVISION = "d900e89f942f784f8e0113935034b4f0541a0b55"
DATASET_SPLIT = "test"
PUBLIC_CONFIG = "morebench_public"
THEORY_CONFIG = "morebench_theory"

ID_PREFIX = "morebench"
MIN_WEIGHT = -3
MAX_WEIGHT = 3
SOURCE_GROUP_TOKENS = 2


def parse_rubric(raw: str) -> list[dict[str, Any]]:
    """Parse a RUBRIC cell into its criteria.

    The cell is a Python literal, not JSON. Each criterion is returned with the keys
    `id`, `title`, `weight` and `dimension`.

    Args:
        raw: The RUBRIC cell of one row.

    Raises:
        ValueError: If the cell is not a list of criteria, or a weight is not a
            non-zero integer from -3 to 3. A bad rubric is a dataset defect, so the
            row is never skipped.
    """
    # Ported from morebench/morebench at e6689bb (MIT): run_inferences_on_dilemmas.py L55.
    rubric = ast.literal_eval(raw)
    if not isinstance(rubric, list):
        raise ValueError(f"RUBRIC is a {type(rubric).__name__}, expected a list")
    criteria = []
    for criterion in rubric:
        weight = criterion["weight"]
        if type(weight) is not int or weight == 0 or not MIN_WEIGHT <= weight <= MAX_WEIGHT:
            raise ValueError(f"criterion {criterion['id']} has weight {weight!r}")
        criteria.append(
            {
                "id": criterion["id"],
                "title": criterion["title"],
                "weight": weight,
                "dimension": criterion["annotations"]["rubric_dimension"],
            }
        )
    return criteria


def source_group(dilemma_source: str) -> str:
    """Return the dilemma source as upstream groups it: its first two `_`-separated tokens."""
    # Ported from morebench/morebench at e6689bb (MIT): utils.py L333-L335.
    return "_".join(dilemma_source.split("_")[:SOURCE_GROUP_TOKENS])


def record_to_sample(record: dict[str, Any]) -> Sample:
    """Convert one dataset row into an Inspect sample.

    The input is the full prompt. There is no target: the rubric in the metadata is the
    ground truth.
    """
    dilemma = record["DILEMMA"]
    theory = record["THEORY"]
    dilemma_source = record["DILEMMA_SOURCE"]
    return Sample(
        id=create_stable_id(dilemma, theory, prefix=ID_PREFIX),
        input=generation_prompt(dilemma, theory),
        metadata={
            "rubric": parse_rubric(record["RUBRIC"]),
            "dilemma_source": dilemma_source,
            "dilemma_source_group": source_group(dilemma_source),
            "dilemma_type": record["DILEMMA_TYPE"],
            "role_domain": record["ROLE_DOMAIN"],
            "theory": theory,
            "context": record["CONTEXT"],
        },
    )


def load_morebench_dataset(config_name: str) -> Dataset:
    """Load one config of MoReBench at the pinned revision.

    Args:
        config_name: `morebench_public` or `morebench_theory`.

    Returns:
        The samples in the dataset's own order, each with its position in
        `metadata["row_index"]`.
    """
    dataset = hf_dataset(
        path=DATASET_PATH,
        name=config_name,
        split=DATASET_SPLIT,
        revision=DATASET_REVISION,
        sample_fields=record_to_sample,
    )
    # Upstream identifies a scenario by its row position; keep it for cross-reference.
    for row_index, sample in enumerate(dataset):
        sample.metadata = {**(sample.metadata or {}), "row_index": row_index}
    return dataset
