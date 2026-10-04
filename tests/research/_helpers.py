"""Lightweight Parquet read helpers for tests/research/. Deliberately
avoid loading a full split into memory anywhere - these mirror the
same chunked/column-limited reading discipline the production pipeline
itself uses (research/datasets/cicids2017/{clean,split}.py), so the
test suite can verify a multi-million-row split's properties without
reintroducing the full-dataset-in-memory problem this revision exists
to fix.
"""

from __future__ import annotations

from pathlib import Path
from typing import Iterator

import numpy as np
import pandas as pd
import pyarrow.parquet as pq


def count_rows(path: Path) -> int:
    return pq.ParquetFile(path).metadata.num_rows


def read_column(path: Path, column: str) -> pd.Series:
    return pq.read_table(path, columns=[column]).column(column).to_pandas()


def flow_id_set(path: Path) -> set[int]:
    return set(pq.read_table(path, columns=["flow_id"]).column("flow_id").to_pylist())


def label_counts(path: Path) -> dict[str, int]:
    """Value counts of the label column, cast to plain str first.

    Why the cast: clean.py writes "label" as a pandas `category` per
    batch (an ad-hoc, per-batch dictionary, not a globally shared
    one - see clean.py's docstring for why). Parquet's dictionary
    encoding doesn't shrink a column's declared categories when a
    later read filters rows down to a subset (e.g. split.py routing
    only a few rows to test_unknown.parquet) - the file can still
    "declare" categories that zero actual rows use. Uncast,
    .value_counts() faithfully reports those as real entries with
    count 0, which looks like (but is not) a labeling bug."""
    return read_column(path, "label").astype(str).value_counts().to_dict()


def read_first_row(path: Path) -> pd.Series:
    """Reads only the first row - via a batch_size=1 read, not a full
    load followed by .iloc[0]."""
    batch = next(pq.ParquetFile(path).iter_batches(batch_size=1))
    return batch.to_pandas().iloc[0]


def iter_chunks(
    path: Path, columns: list[str] | None = None, batch_size: int = 200_000
) -> Iterator[pd.DataFrame]:
    for batch in pq.ParquetFile(path).iter_batches(batch_size=batch_size, columns=columns):
        yield batch.to_pandas()


def concatenated_column(path: Path, column: str) -> np.ndarray:
    """Like read_column(), but as one numpy array - for columns small
    enough to hold as a single array across the whole file (e.g. one
    int64 per row is a few tens of MB even at millions of rows)."""
    return read_column(path, column).to_numpy()


def streaming_mean_std(path: Path, columns: list[str], batch_size: int = 200_000):
    """Independently recomputes per-column mean/population-std across
    the whole file, streaming in chunks - used to directly verify a
    fitted scaler's parameters without ever loading the full file (the
    same reason fit_scaler_streaming() itself is chunked)."""
    total_count = 0
    total_sum = None
    total_sumsq = None
    for chunk in iter_chunks(path, columns=columns, batch_size=batch_size):
        values = chunk.to_numpy(dtype="float64")
        if total_sum is None:
            total_sum = values.sum(axis=0)
            total_sumsq = (values**2).sum(axis=0)
        else:
            total_sum += values.sum(axis=0)
            total_sumsq += (values**2).sum(axis=0)
        total_count += len(values)

    mean = total_sum / total_count
    var = total_sumsq / total_count - mean**2
    std = np.sqrt(np.clip(var, 0, None))
    return mean, std
