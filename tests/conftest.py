"""
Shared fixtures.

Everything here loads artefacts that are tracked in git. The Bronze CSVs and
the Silver Parquet are deliberately not, so the suite runs on a fresh clone
with no 23MB download and no credentials — which is the only way a test suite
on this repository is worth having.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pandas as pd
import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
RELEASE_SLUG = "release_2026-08-28"
GOLD_DIR = REPO_ROOT / "data" / "gold" / RELEASE_SLUG
SILVER_DIR = REPO_ROOT / "data" / "silver" / RELEASE_SLUG
BRONZE_DIR = REPO_ROOT / "data" / "bronze" / RELEASE_SLUG

# Every Gold table that carries a rate, so the invariant tests can sweep them.
BREAKDOWN_TABLES = [
    "03_unmatched_by_property_type",
    "04_unmatched_by_new_build",
    "05_unmatched_by_ppd_category",
    "06_unmatched_by_property_type_and_new_build",
    "07_unmatched_by_postcode_presence",
]


def load_pipeline_module(filename: str):
    """Import a pipeline script by path — the names start with digits."""
    path = REPO_ROOT / "src" / "pipeline" / filename
    spec = importlib.util.spec_from_file_location(path.stem, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="session")
def silver_report() -> dict:
    return json.loads((SILVER_DIR / "validation.json").read_text())


@pytest.fixture(scope="session")
def gold_summary() -> dict:
    return json.loads((GOLD_DIR / "summary.json").read_text())


@pytest.fixture(scope="session")
def context_summary() -> dict:
    return json.loads((GOLD_DIR / "context_summary.json").read_text())


@pytest.fixture(scope="session")
def bronze_manifest() -> dict:
    return json.loads((BRONZE_DIR / "metadata.json").read_text())


@pytest.fixture(scope="session")
def gold() -> dict[str, pd.DataFrame]:
    return {p.stem: pd.read_csv(p) for p in sorted(GOLD_DIR.glob("*.csv"))}


@pytest.fixture(scope="session")
def figures_html() -> str:
    return (REPO_ROOT / "docs" / "figures.html").read_text()
