"""
Defines the structure of manifest.yaml - a plain, inspectable record of
exactly how a processed CICIDS2017 run was produced, so it can be
reproduced or audited later. Deliberately a dict/dataclass written to
YAML, not a database or a complex object.

Must never contain: credentials/tokens, developer-machine-specific
absolute paths, or personally identifying information.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import yaml


@dataclass
class SourceInfo:
    source_type: str  # "huggingface_interim" | "official_unb"
    dataset_name: str
    revision: str | None
    license: str
    download_date: str  # ISO 8601 date


@dataclass
class CleaningInfo:
    input_rows: int
    rows_with_nan_or_inf: int
    duplicate_rows_removed: int
    output_rows: int
    feature_count: int
    steps_applied: list[str] = field(
        default_factory=lambda: [
            "drop rows with NaN in any numeric column",
            "drop rows with Infinity in any numeric column",
            "drop duplicate rows (by content hash over every column "
            "except the row identifier, i.e. the full restored column set)",
            "standardize column names to a canonical schema",
            "standardize label text to one canonical spelling per class",
            "parse Timestamp to epoch seconds",
            "re-encode protocol numerically as an additional feature",
        ]
    )


@dataclass
class SplitInfo:
    seed: int
    test_fraction: float
    held_out_label: str
    benign_label: str
    test_unknown_pair_count: int
    row_counts: dict[str, int]
    class_counts: dict[str, dict[str, int]]
    logic_description: str = (
        "train = every class except the held-out class (zero held-out rows). "
        "test = every class including the held-out class, each class split by "
        "the same fixed test_fraction. test_unknown = the held-out class's "
        "remaining rows (after test's share) paired with an equal, disjoint, "
        "randomly sampled set of Benign rows. All three splits are disjoint "
        "by row identifier."
    )


@dataclass
class FeaturizationInfo:
    function: str = "ovael.ingestion.feature_extraction.extract_features"
    note: str = (
        "The same function the live detection pipeline calls "
        "(ovael/pipeline/pipeline.py:run()) - not a separate implementation."
    )


@dataclass
class ScalingInfo:
    method: str
    fit_on_split: str
    feature_columns: list[str]
    n_samples_seen: int
    params_path: str


@dataclass
class Manifest:
    generated_at: str
    source: SourceInfo
    cleaning: CleaningInfo
    split: SplitInfo
    featurization: FeaturizationInfo
    scaling: ScalingInfo

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def write_manifest(manifest: Manifest, path: Path) -> None:
    with open(path, "w") as f:
        yaml.safe_dump(manifest.to_dict(), f, sort_keys=False)


def load_manifest(path: Path) -> dict[str, Any]:
    with open(path) as f:
        return yaml.safe_load(f)
