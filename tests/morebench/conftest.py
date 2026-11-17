import json
from pathlib import Path
from typing import Any

import pytest

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
def theory_row0() -> dict[str, Any]:
    """Row 0 of morebench_theory (Scanlonian Contractualism)."""
    return load_row("morebench_theory_row0")


@pytest.fixture
def theory_row72() -> dict[str, Any]:
    """Row 72 of morebench_theory: the first row whose CONTEXT cell is empty."""
    return load_row("morebench_theory_row72")
