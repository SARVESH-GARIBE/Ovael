"""
Orchestrates the full Stage 2 CICIDS2017 pipeline as one callable entry
point: download -> clean -> split -> featurize -> scale, writing the
processed Parquet files, the fitted scaler's parameters, and
manifest.yaml.

Every stage streams through on-disk Parquet rather than holding the
full dataset (or a full split) as one in-memory dataframe at any point
- clean_dataset() and split_dataset() already stream internally (see
their own docstrings); this module's job is just to pass file paths
between them and run featurize/scale per split, one split at a time,
reading and writing in chunks throughout. An earlier, all-in-memory
version of this pipeline crashed via an actual OOM kill on this
machine; this version has been run to completion with peak RSS
measured and reported in docs/stage2.md.

Intermediate files (the cleaned dataset and the unfeaturized splits,
under data/processed/cicids2017/_intermediate/) are scratch - not a
deliverable - and are removed once the run completes successfully.

Run with:
    PYTHONPATH=. python -m research.datasets.cicids2017.pipeline
"""

from __future__ import annotations

import datetime
import shutil
from pathlib import Path

from research.datasets.cicids2017.clean import HELD_OUT_LABEL, clean_dataset
from research.datasets.cicids2017.download import (
    REPO_ROOT,
    DataSourceConfig,
    HF_LICENSE,
    HF_REPO_ID,
)
from research.datasets.cicids2017.featurize import featurize_file
from research.datasets.cicids2017.manifest_schema import (
    CleaningInfo,
    FeaturizationInfo,
    Manifest,
    ScalingInfo,
    SourceInfo,
    SplitInfo,
    write_manifest,
)
from research.datasets.cicids2017.scale import (
    apply_scaler_streaming,
    fit_scaler_streaming,
    save_scaler,
)
from research.datasets.cicids2017.split import SEED, TEST_FRACTION, split_dataset

DEFAULT_PROCESSED_DIR = REPO_ROOT / "data" / "processed" / "cicids2017"
SPLIT_ORDER = ("train", "test", "test_unknown")


def _feature_column_names(parquet_path: Path) -> list[str]:
    """The feature_* columns of an already-featurized Parquet file -
    i.e. the actual FeatureVector.features keys, NOT the identity-echo
    columns (source_port, destination_port, payload_size, ...) that
    featurize_file() also writes alongside them for readability.
    Mixing those identity columns into the scaler would silently
    overwrite their human-readable values with z-scores in the
    _scaled.parquet files - the same "feature_" prefix rule
    featurize.feature_columns() uses for in-memory dataframes, applied
    here directly to a file's schema."""
    import pyarrow.parquet as pq

    columns = pq.ParquetFile(parquet_path).schema_arrow.names
    return [c for c in columns if c.startswith("feature_")]


def run(config: DataSourceConfig | None = None, out_dir: Path = DEFAULT_PROCESSED_DIR) -> dict:
    config = config or DataSourceConfig()
    out_dir = Path(out_dir)
    intermediate_dir = out_dir / "_intermediate"
    out_dir.mkdir(parents=True, exist_ok=True)

    print("=== Stage 2: CICIDS2017 pipeline ===")
    print(f"source: {config.source}")

    cleaned_path, cleaning_stats = clean_dataset(config, output_path=intermediate_dir / "cleaned.parquet")
    print(f"cleaned: {cleaning_stats}")

    split_paths, split_info = split_dataset(
        cleaned_path, seed=SEED, test_fraction=TEST_FRACTION, output_dir=intermediate_dir
    )

    scaler = None
    columns: list[str] | None = None
    n_samples_seen = None

    for name in SPLIT_ORDER:
        featurized_path = out_dir / f"{name}.parquet"
        featurize_file(split_paths[name], featurized_path)

        if columns is None:
            columns = _feature_column_names(featurized_path)
        if name == "train":
            scaler = fit_scaler_streaming(featurized_path, columns)
            n_samples_seen = split_info["row_counts"]["train"]

        apply_scaler_streaming(featurized_path, scaler, columns, out_dir / f"{name}_scaled.parquet")

    scaler_path = out_dir / "scaler.json"
    save_scaler(scaler, columns, scaler_path)

    manifest = Manifest(
        generated_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
        source=SourceInfo(
            source_type=config.source,
            dataset_name=HF_REPO_ID,
            revision=config.revision if config.source == "huggingface_interim" else None,
            license=HF_LICENSE,
            download_date=datetime.date.today().isoformat(),
        ),
        cleaning=CleaningInfo(**cleaning_stats),
        split=SplitInfo(**split_info),
        featurization=FeaturizationInfo(),
        scaling=ScalingInfo(
            method="StandardScaler (z-score)",
            fit_on_split="train",
            feature_columns=columns,
            n_samples_seen=n_samples_seen,
            params_path="scaler.json",
        ),
    )
    write_manifest(manifest, out_dir / "manifest.yaml")

    # Intermediate files (cleaned.parquet, {name}_clean.parquet) are
    # scratch, not a deliverable - remove them now that every real
    # output has been written successfully.
    shutil.rmtree(intermediate_dir, ignore_errors=True)

    held_out_in_train = split_info["class_counts"]["train"].get(HELD_OUT_LABEL, 0)
    test_unknown_labels = sorted(split_info["class_counts"]["test_unknown"].keys())

    summary = {
        "row_counts": split_info["row_counts"],
        "class_counts": split_info["class_counts"],
        "test_unknown_labels": test_unknown_labels,
        "held_out_in_train": held_out_in_train,
    }

    print("--- summary ---")
    for name, count in summary["row_counts"].items():
        print(f"{name}: {count} rows")
    for name, class_counts in summary["class_counts"].items():
        print(f"  {name} per-class: {class_counts}")
    print(f"test_unknown labels: {summary['test_unknown_labels']}")
    print(f"held-out class rows in train: {summary['held_out_in_train']} (must be 0)")

    return summary


if __name__ == "__main__":
    run()
