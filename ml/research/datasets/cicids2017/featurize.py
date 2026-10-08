"""
Converts each row of a cleaned/split dataframe into a FeatureVector by
building a RawTraffic instance - with the real CICFlowMeter flow
statistics attached via RawTraffic.flow_features - and calling Stage
1's REAL ovael.ingestion.feature_extraction.extract_features(). Because
flow_features is non-empty, extract_features() passes it straight
through as FeatureVector.features (see that module's docstring); this
module still does not compute any feature value itself, it only moves
values from a dataframe row into the RawTraffic/FeatureVector shapes.
"""

from __future__ import annotations

import gc
from pathlib import Path

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from ovael.contracts.schemas import RawTraffic
from ovael.ingestion.feature_extraction import extract_features

# Building one Python dict (79 float entries) per row, for millions of
# rows, measured at roughly 2.5GB of peak RSS per 200k rows processed
# in a single unbroken pass - CPython's small-object allocator does
# not return freed memory to the OS promptly, so even though each
# row's intermediate dict/RawTraffic/FeatureVector objects are
# short-lived, peak RSS still climbs with the total number processed
# in one go, not with how many are alive at once. Processing in
# bounded internal chunks - converting each chunk straight to a small
# DataFrame and freeing its Python objects (with an explicit gc pass)
# before starting the next - keeps peak RSS bounded by one chunk's
# cost instead of the whole split's. See docs/stage2.md for the
# measured numbers this chunk size is based on.
CHUNK_SIZE = 20_000

# Columns clean.py produces that are identity/label, not features -
# everything else in a cleaned/split dataframe is a numeric feature.
LABEL_COLUMN = "label"
NON_FEATURE_COLUMNS = ("flow_id", "source_ip", "destination_ip", "timestamp", "protocol", LABEL_COLUMN)


def feature_columns_in(df: pd.DataFrame) -> list[str]:
    """The numeric feature columns present in a cleaned/split dataframe
    (everything except identity/timestamp/protocol-text/label)."""
    return [c for c in df.columns if c not in NON_FEATURE_COLUMNS]


def row_to_raw_traffic(row: pd.Series, feature_cols: list[str]) -> RawTraffic:
    payload_size = int(
        row["total_length_of_fwd_packets"] + row["total_length_of_bwd_packets"]
    )
    return RawTraffic(
        source_ip=str(row["source_ip"]),
        destination_ip=str(row["destination_ip"]),
        source_port=int(row["source_port"]),
        destination_port=int(row["destination_port"]),
        protocol=str(row["protocol"]),
        payload_size=payload_size,
        timestamp=float(row["timestamp"]),
        flow_features={name: float(row[name]) for name in feature_cols},
    )


def _featurize_rows(df: pd.DataFrame, feature_cols: list[str]) -> list[dict]:
    feature_rows: list[dict] = []
    for _, row in df.iterrows():
        raw_traffic = row_to_raw_traffic(row, feature_cols)
        feature_vector = extract_features(raw_traffic)

        feature_row = {
            "flow_id": row["flow_id"],
            "source_ip": feature_vector.source_ip,
            "destination_ip": feature_vector.destination_ip,
            "source_port": feature_vector.source_port,
            "destination_port": feature_vector.destination_port,
            "protocol": feature_vector.protocol,
            "timestamp": feature_vector.timestamp,
            "payload_size": feature_vector.payload_size,
        }
        for feature_name, value in feature_vector.features.items():
            feature_row[f"feature_{feature_name}"] = value
        feature_row[LABEL_COLUMN] = row[LABEL_COLUMN]
        feature_rows.append(feature_row)
    return feature_rows


def featurize_split(df: pd.DataFrame, chunk_size: int = CHUNK_SIZE) -> pd.DataFrame:
    """Builds a RawTraffic for every row and calls the real
    extract_features() on it. Returns a new dataframe: the identifying
    fields, one `feature_<name>` column per key in the produced
    FeatureVector.features dict, and the original label column.

    Processed in bounded internal chunks (see CHUNK_SIZE's docstring
    above) rather than building one Python list of per-row dicts for
    the whole input - the external behavior (and result) is identical
    either way; this only bounds peak memory for large inputs."""
    feature_cols = feature_columns_in(df)
    chunk_frames: list[pd.DataFrame] = []
    for start in range(0, len(df), chunk_size):
        chunk = df.iloc[start : start + chunk_size]
        chunk_frames.append(pd.DataFrame(_featurize_rows(chunk, feature_cols)))
        gc.collect()

    return pd.concat(chunk_frames, ignore_index=True)


def feature_columns(df: pd.DataFrame) -> list[str]:
    """The numeric feature_* columns produced by featurize_split - the
    columns scale.py fits/applies a scaler to."""
    return [c for c in df.columns if c.startswith("feature_")]


def featurize_file(input_path: Path, output_path: Path, chunk_size: int = CHUNK_SIZE) -> int:
    """Streaming file-to-file version of featurize_split(): reads
    `input_path` (a cleaned/split Parquet file) in chunks, applies the
    same row -> RawTraffic -> extract_features() logic, and appends
    each chunk's result straight to `output_path` via an incremental
    ParquetWriter. Unlike featurize_split(), this never holds the full
    output in memory either - only one chunk at a time, for inputs of
    any size. Returns the number of rows written."""
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    source_columns = pq.ParquetFile(input_path).schema_arrow.names
    feature_cols = [c for c in source_columns if c not in NON_FEATURE_COLUMNS]

    rows_written = 0
    writer: pq.ParquetWriter | None = None
    try:
        parquet_file = pq.ParquetFile(input_path)
        for record_batch in parquet_file.iter_batches(batch_size=chunk_size):
            chunk = record_batch.to_pandas()
            result = pd.DataFrame(_featurize_rows(chunk, feature_cols))
            del chunk
            table = pa.Table.from_pandas(result, preserve_index=False)
            if writer is None:
                writer = pq.ParquetWriter(str(output_path), table.schema)
            writer.write_table(table)
            rows_written += len(result)
            del result, table
            gc.collect()
    finally:
        if writer is not None:
            writer.close()

    return rows_written
