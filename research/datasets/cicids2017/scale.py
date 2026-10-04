"""
Fits a StandardScaler (z-score) on the `train` split's feature_*
columns ONLY, then applies that SAME fitted scaler to `test` and
`test_unknown` - it is never refit per split. The fitted parameters
(mean/scale per feature) are saved to disk so they can be reloaded
without recomputation. Scaling produces a new dataframe alongside the
unscaled one; the unscaled version is never discarded or overwritten.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
from sklearn.preprocessing import StandardScaler


def fit_scaler(train_df: pd.DataFrame, columns: list[str]) -> StandardScaler:
    """Fits on train_df[columns] ONLY. Caller must pass the train split
    - this function has no way to know or enforce that, so scale.py's
    pipeline-level caller (pipeline.py) is what guarantees it; see
    tests/research/test_cicids2017_scaling.py for the direct check."""
    scaler = StandardScaler()
    scaler.fit(train_df[columns].to_numpy(dtype="float64"))
    return scaler


def apply_scaler(df: pd.DataFrame, scaler: StandardScaler, columns: list[str]) -> pd.DataFrame:
    """Returns a NEW dataframe with `columns` replaced by their scaled
    values; `df` itself is untouched."""
    scaled = df.copy()
    scaled[columns] = scaler.transform(df[columns].to_numpy(dtype="float64"))
    return scaled


def scaler_to_dict(scaler: StandardScaler, columns: list[str]) -> dict:
    return {
        "feature_columns": list(columns),
        "mean": scaler.mean_.tolist(),
        "scale": scaler.scale_.tolist(),
        "var": scaler.var_.tolist(),
        "n_samples_seen": int(scaler.n_samples_seen_),
    }


def save_scaler(scaler: StandardScaler, columns: list[str], path: Path) -> None:
    path.write_text(json.dumps(scaler_to_dict(scaler, columns), indent=2))


def load_scaler(path: Path) -> tuple[StandardScaler, list[str]]:
    data = json.loads(Path(path).read_text())
    scaler = StandardScaler()
    scaler.mean_ = np.array(data["mean"], dtype="float64")
    scaler.scale_ = np.array(data["scale"], dtype="float64")
    scaler.var_ = np.array(data["var"], dtype="float64")
    scaler.n_samples_seen_ = data["n_samples_seen"]
    scaler.n_features_in_ = len(data["feature_columns"])
    return scaler, data["feature_columns"]


def fit_scaler_streaming(path: Path, columns: list[str], chunk_size: int = 200_000) -> StandardScaler:
    """Same fit-on-train-only contract as fit_scaler(), but reads
    `path` (the train split's featurized Parquet file) in chunks via
    StandardScaler.partial_fit() rather than loading it whole - the
    resulting mean_/var_/scale_ are mathematically the train split's
    own statistics either way (partial_fit uses a numerically stable
    streaming variance update, not an approximation)."""
    scaler = StandardScaler()
    parquet_file = pq.ParquetFile(path)
    for record_batch in parquet_file.iter_batches(batch_size=chunk_size, columns=columns):
        chunk = record_batch.to_pandas()
        scaler.partial_fit(chunk.to_numpy(dtype="float64"))
        del chunk
    return scaler


def apply_scaler_streaming(
    input_path: Path, scaler: StandardScaler, columns: list[str], output_path: Path, chunk_size: int = 200_000
) -> int:
    """Streaming file-to-file version of apply_scaler(): reads
    `input_path` in chunks, replaces `columns` with their scaled
    values using the SAME already-fitted scaler for every chunk, and
    writes to `output_path` incrementally. `input_path` itself is
    untouched - the unscaled file is never discarded or overwritten.
    Returns the number of rows written."""
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    rows_written = 0
    writer = None
    try:
        parquet_file = pq.ParquetFile(input_path)
        for record_batch in parquet_file.iter_batches(batch_size=chunk_size):
            chunk = record_batch.to_pandas()
            chunk[columns] = scaler.transform(chunk[columns].to_numpy(dtype="float64"))
            table = pa.Table.from_pandas(chunk, preserve_index=False)
            if writer is None:
                writer = pq.ParquetWriter(str(output_path), table.schema)
            writer.write_table(table)
            rows_written += len(chunk)
            del chunk, table
    finally:
        if writer is not None:
            writer.close()
    return rows_written
