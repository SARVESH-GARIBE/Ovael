"""
Loads raw CICIDS2017 batches (from download.iter_raw_batches), removes
NaN/infinite values and duplicate rows, and standardizes column names,
label text, and the numeric feature set into one canonical cleaned
schema.

Full feature width: every numeric CICFlowMeter flow-statistics column
present in the source is carried forward - packet count/length stats
(fwd/bwd), inter-arrival-time stats, flag counts, window sizes, subflow
stats, idle/active time stats, source/destination port, and protocol
(re-encoded numerically; see PROTOCOL_NUMERIC_CODE below). Excluded:
raw source/destination IP addresses (non-numeric identifiers), the
flow_id identifier, the raw Timestamp (parsed into a separate,
non-feature epoch-seconds column for ordering/debugging), and the
label (handled by split.py's routing logic, never fed in as a
feature). See docs/stage2.md for the exact kept/excluded column list
and the rationale for each exclusion.

Processed in batches rather than as one big dataframe, with feature
columns held at float32 and low-cardinality text columns (protocol,
label) held as pandas `category` dtype while in memory, instead of
loading the whole raw file as one float64 dataframe. This -
chunked/row-group reading + narrower dtypes - was still not enough on
its own: holding the full ~2.8M-row result as one in-memory dataframe
(even at these narrower dtypes) measured at ~2.1-2.5GB peak RSS, and
the full combined pipeline (this plus split/featurize downstream)
crashed via an actual OOM kill on this machine. clean_dataset() now
STREAMS its output directly to an on-disk Parquet file via an
incremental pyarrow ParquetWriter, one cleaned batch at a time - it
never holds the full cleaned dataset in memory at any point, at any
dataset size. It replaces an earlier revision of this module that
narrowed the row to ~9 fields before deduplicating, which incorrectly
flagged 28,919 distinct flows as "duplicates" because they only looked
identical once most of their columns had already been discarded -
deduplication here runs on the full restored column set, and is
near-zero-memory (an int64 hash plus an int64 flow_id per row, ~2.8M of
each is a few tens of MB) regardless of how many rows are deduplicated.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from ml.research.datasets.cicids2017.download import REPO_ROOT, DataSourceConfig, iter_raw_batches

DEFAULT_CLEANED_PATH = REPO_ROOT / "data" / "processed" / "cicids2017" / "_intermediate" / "cleaned.parquet"

BENIGN_LABEL = "Benign"
HELD_OUT_LABEL = "DoS Slowloris"

# Known label-text variants in the raw data, normalized to one
# canonical spelling per label. Anything not listed is kept as-is
# (whitespace-stripped only) - Stage 2 does not select or train an
# algorithm, so categorizing every attack type beyond "is it the
# held-out class" is out of scope.
LABEL_NORMALIZATION = {
    "BENIGN": BENIGN_LABEL,
    "DoS slowloris": HELD_OUT_LABEL,
    "DoS Slowloris": HELD_OUT_LABEL,
}

# Columns that identify or label a row rather than describe its
# traffic - never fed into a model as a feature value.
RAW_IDENTITY_COLUMNS = ("flow_id", "source_ip", "destination_ip")
RAW_TIMESTAMP_COLUMN = "Timestamp"
RAW_LABEL_COLUMN = "attack_label"
RAW_PROTOCOL_COLUMN = "protocol"

# This source already decodes CICFlowMeter's protocol field to a
# string ("tcp"/"udp"/"other"); re-encoded here to the IANA protocol
# numbers CICFlowMeter's own CSVs (and the official UNB source) use
# numerically, so protocol is carried forward as a numeric feature
# rather than dropped or left as text inside a float feature dict.
PROTOCOL_NUMERIC_CODE = {"tcp": 6, "udp": 17, "other": 0}
PROTOCOL_FEATURE_NAME = "protocol_num"


def _snake_case(name: str) -> str:
    return re.sub(r"[^0-9a-zA-Z]+", "_", name).strip("_").lower()


def _raw_feature_columns(raw_columns: list[str]) -> list[str]:
    """Every raw column except the identity/timestamp/label/raw-protocol-
    text columns, in the order the source provides them. Computed from
    whatever columns are actually present, so nothing is silently
    dropped if a source's exact header set differs."""
    excluded = set(RAW_IDENTITY_COLUMNS) | {
        RAW_TIMESTAMP_COLUMN,
        RAW_LABEL_COLUMN,
        RAW_PROTOCOL_COLUMN,
    }
    return [c for c in raw_columns if c not in excluded]


def feature_names(raw_columns: list[str]) -> list[str]:
    """The canonical (snake_case) feature column names clean_dataset()
    produces, given the raw source's own column list."""
    names = [_snake_case(c) for c in _raw_feature_columns(raw_columns)]
    return names + [PROTOCOL_FEATURE_NAME]


@dataclass
class CleaningStats:
    input_rows: int = 0
    rows_with_nan_or_inf: int = 0
    duplicate_rows_removed: int = 0
    output_rows: int = 0
    feature_count: int = 0

    def as_dict(self) -> dict:
        return dict(
            input_rows=self.input_rows,
            rows_with_nan_or_inf=self.rows_with_nan_or_inf,
            duplicate_rows_removed=self.duplicate_rows_removed,
            output_rows=self.output_rows,
            feature_count=self.feature_count,
        )


def _normalize_label(raw_label: str) -> str:
    stripped = str(raw_label).strip()
    return LABEL_NORMALIZATION.get(stripped, stripped)


def _parse_timestamp_epoch_seconds(series: pd.Series) -> pd.Series:
    # dayfirst=True: the raw Timestamp column is DD/M/YYYY (inconsistently
    # zero-padded, e.g. "03/07/2017 08:55:58" and "4/7/2017 09:10:00"),
    # matching CICIDS2017's 5-day capture window (3-7 July 2017).
    # format="mixed": some rows additionally omit the seconds field
    # (e.g. "4/7/2017 8:54"), so no single strptime format matches
    # every row - each value is parsed individually instead.
    parsed = pd.to_datetime(series, dayfirst=True, format="mixed")
    return (parsed - pd.Timestamp("1970-01-01")) / pd.Timedelta("1s")


def _canonicalize_batch(
    batch: pd.DataFrame, raw_feature_columns: list[str]
) -> tuple[pd.DataFrame, int]:
    """Drops rows with NaN/Inf in any numeric column (checked at the
    source's own precision, before any downcasting), then builds the
    canonical batch: identity columns, parsed timestamp, label,
    original protocol text, and every feature column at float32
    (protocol additionally re-encoded numerically as a feature).

    source_ip/destination_ip/label are cast to `category` PER BATCH
    (an ad-hoc category set local to that batch, not a globally shared
    one). This was measured, not assumed: a version that first scans
    the whole dataset to build one global, shared CategoricalDtype (so
    the dtype would survive concat as a true category in the final
    frame) raised peak RSS to ~2.5GB, because the extra full pass's
    own memory didn't fully overlap with the main pass's. The ad-hoc
    per-batch version measured here - even though pandas' concat later
    upcasts these three columns back to plain strings once it sees
    each batch brought a different category set - is what actually
    kept peak RSS down (~2.6GB -> ~2.1GB): the saving happens DURING
    the expensive accumulate-then-concat phase, which is where the
    peak occurs, not in the dtype of the frame concat finally returns.
    `protocol` is the exception: it only ever has 3 possible values,
    identical in every batch, so it remains a true category in the
    final result."""
    numeric_cols = batch.select_dtypes(include=[np.number]).columns
    keep_mask = ~batch[numeric_cols].isna().any(axis=1)
    for col in numeric_cols:
        if pd.api.types.is_float_dtype(batch[col]):
            keep_mask &= ~np.isinf(batch[col].to_numpy())

    dropped = int((~keep_mask).sum())
    batch = batch.loc[keep_mask]

    canonical = pd.DataFrame(
        {
            "flow_id": batch["flow_id"],
            "source_ip": batch["source_ip"].astype(str).astype("category"),
            "destination_ip": batch["destination_ip"].astype(str).astype("category"),
            "timestamp": _parse_timestamp_epoch_seconds(batch[RAW_TIMESTAMP_COLUMN]),
            "protocol": batch[RAW_PROTOCOL_COLUMN].astype(str).astype("category"),
            "label": batch[RAW_LABEL_COLUMN].map(_normalize_label).astype("category"),
        }
    )

    for raw_col in raw_feature_columns:
        canonical[_snake_case(raw_col)] = batch[raw_col].to_numpy(dtype="float32")

    protocol_code = batch[RAW_PROTOCOL_COLUMN].astype(str).map(
        lambda p: PROTOCOL_NUMERIC_CODE.get(p, 0)
    )
    canonical[PROTOCOL_FEATURE_NAME] = protocol_code.to_numpy(dtype="float32")

    return canonical, dropped


def _remove_duplicate_rows(path: Path, duplicate_flow_ids: set[int]) -> None:
    """Streaming filter pass: rewrites `path` excluding any row whose
    flow_id is in duplicate_flow_ids. Only called when duplicates were
    actually found (the common case on this source is zero - see
    clean_dataset()'s docstring) - reads and writes in row-group-sized
    batches, never the whole file at once."""
    tmp_path = path.with_suffix(".dedup_tmp.parquet")
    parquet_file = pq.ParquetFile(path)
    writer = None
    try:
        for record_batch in parquet_file.iter_batches(batch_size=200_000):
            table = pa.Table.from_batches([record_batch])
            flow_id_values = table.column("flow_id").to_numpy(zero_copy_only=False)
            keep = np.array([fid not in duplicate_flow_ids for fid in flow_id_values])
            filtered = table.filter(pa.array(keep))
            if writer is None:
                writer = pq.ParquetWriter(str(tmp_path), filtered.schema)
            writer.write_table(filtered)
    finally:
        if writer is not None:
            writer.close()
    tmp_path.replace(path)


def clean_dataset(
    config: DataSourceConfig | None = None, output_path: Path = DEFAULT_CLEANED_PATH
) -> tuple[Path, dict]:
    """Streams raw batches, drops NaN/Inf rows, writes every surviving
    row to `output_path` (a single Parquet file) via an incremental
    ParquetWriter, and finally removes any duplicate rows (by a content
    hash over every column except flow_id - the full restored column
    set, not a narrowed subset). Never holds the full cleaned dataset
    in memory: only an int64 hash and an int64 flow_id per row are kept
    across the whole run, everything else is written out one batch at
    a time and discarded. Returns (output_path, cleaning_stats_dict)."""
    config = config or DataSourceConfig()
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    stats = CleaningStats()

    row_hashes: list[np.ndarray] = []
    flow_ids: list[np.ndarray] = []
    raw_feature_columns: list[str] | None = None
    writer: pq.ParquetWriter | None = None

    try:
        for batch in iter_raw_batches(config):
            stats.input_rows += len(batch)
            if raw_feature_columns is None:
                raw_feature_columns = _raw_feature_columns(list(batch.columns))
                stats.feature_count = len(raw_feature_columns) + 1  # + protocol_num

            canonical, dropped = _canonicalize_batch(batch, raw_feature_columns)
            stats.rows_with_nan_or_inf += dropped

            row_hashes.append(
                pd.util.hash_pandas_object(
                    canonical.drop(columns=["flow_id"]), index=False
                ).to_numpy()
            )
            flow_ids.append(canonical["flow_id"].to_numpy())

            table = pa.Table.from_pandas(canonical, preserve_index=False)
            if writer is None:
                writer = pq.ParquetWriter(str(output_path), table.schema)
            writer.write_table(table)
            del canonical, table
    finally:
        if writer is not None:
            writer.close()

    all_hashes = np.concatenate(row_hashes)
    del row_hashes
    all_flow_ids = np.concatenate(flow_ids)
    del flow_ids

    if len(np.unique(all_flow_ids)) != len(all_flow_ids):
        # flow_id is only used as a dedup/leakage-check identifier, not
        # as the dedup criterion itself - a repeated flow_id alongside
        # otherwise-differing rows would break that assumption outright.
        raise ValueError(
            "flow_id is expected to be a stable, unique row identifier "
            "after NaN/Inf filtering; this source violates that "
            "assumption before duplicate content is even considered."
        )

    is_duplicate = pd.Series(all_hashes).duplicated(keep="first").to_numpy()
    stats.duplicate_rows_removed = int(is_duplicate.sum())
    if stats.duplicate_rows_removed > 0:
        duplicate_flow_ids = set(all_flow_ids[is_duplicate].tolist())
        _remove_duplicate_rows(output_path, duplicate_flow_ids)

    stats.output_rows = stats.input_rows - stats.rows_with_nan_or_inf - stats.duplicate_rows_removed
    return output_path, stats.as_dict()
