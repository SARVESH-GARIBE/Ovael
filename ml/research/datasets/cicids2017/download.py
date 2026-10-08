"""
Fetches raw CIC-IDS-2017 data and exposes it to clean.py as a stream of
batches in ONE canonical raw schema, regardless of which underlying
source produced it. This is the boundary where source differences are
absorbed: everything in clean.py and downstream never needs to know
whether the data came from the interim Hugging Face mirror or the
official University of New Brunswick (UNB) / Canadian Institute for
Cybersecurity CSVs.

Two sources are supported:

- "huggingface_interim" (default, used today): the pre-extracted
  Network-Flows table from the `rdpahalavan/CIC-IDS2017` Hugging Face
  dataset (Apache-2.0). This is explicitly an INTERIM source — the
  repository owner is separately requesting the official dataset from
  UNB/CIC.
- "official_unb": official CICFlowMeter CSVs, expected to be dropped
  into OFFICIAL_CSV_DIR. NOT YET AVAILABLE in this environment and
  therefore NOT YET EXERCISED by any test here — the column mapping
  below is written from the official dataset's well-documented,
  publicly known CICFlowMeter CSV header convention, but has not been
  run against a real official file. Treat it as best-effort until
  verified against the real files.

Swapping sources is a one-line config change (DataSourceConfig.source),
never a rewrite of clean.py/split.py/featurize.py/scale.py.

Auth: the Hugging Face dataset used today is public and needs no token.
If a token is ever required, it is read ONLY from the HF_TOKEN
environment variable at runtime — never hardcoded, never written to a
committed file, never logged or printed.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[4]
DEFAULT_RAW_DIR = REPO_ROOT / "data" / "raw" / "cicids2017"
OFFICIAL_CSV_DIR = DEFAULT_RAW_DIR / "official"

# --- Interim Hugging Face source -------------------------------------

HF_REPO_ID = "rdpahalavan/CIC-IDS2017"
HF_REPO_TYPE = "dataset"
HF_FILENAME = "Network-Flows/CICIDS_Flow.parquet"
# Pinned commit, not a mutable branch name, so re-downloading always
# gets exactly this snapshot. Recorded in the manifest alongside the
# license and download date.
HF_REVISION = "eee96b6abc2c4bb621fd67679a4aa24bddc4be6a"
HF_LICENSE = "apache-2.0"
HF_TOKEN_ENV_VAR = "HF_TOKEN"

# Canonical raw-schema column names every source is normalized to
# before clean.py sees it. These match the interim HF file's own
# column names (it already happens to use a convenient convention);
# the official-source loader below renames its CSV headers to match.
RAW_ID_COLUMNS = (
    "flow_id",
    "source_ip",
    "source_port",
    "destination_ip",
    "destination_port",
    "protocol",
    "Timestamp",
    "attack_label",
)


@dataclass(frozen=True)
class DataSourceConfig:
    """Which source to read from, and where. Change `source` (and, for
    the official path, make sure csv_dir has files in it) to switch
    sources — nothing else in the pipeline needs to change."""

    source: str = "huggingface_interim"  # or "official_unb"
    raw_dir: Path = DEFAULT_RAW_DIR
    csv_dir: Path = OFFICIAL_CSV_DIR
    revision: str = HF_REVISION
    batch_size: int = 200_000


def _hf_local_path(config: DataSourceConfig) -> Path:
    return config.raw_dir / HF_FILENAME


def fetch_interim_hf(config: DataSourceConfig) -> Path:
    """Downloads the interim HF parquet file if it isn't already on
    disk. Returns its local path. Never re-downloads once present."""
    dest = _hf_local_path(config)
    if dest.exists():
        return dest

    from huggingface_hub import hf_hub_download

    token = os.environ.get(HF_TOKEN_ENV_VAR)  # never logged, never printed
    path = hf_hub_download(
        repo_id=HF_REPO_ID,
        repo_type=HF_REPO_TYPE,
        filename=HF_FILENAME,
        revision=config.revision,
        local_dir=str(config.raw_dir),
        token=token,
    )
    return Path(path)


def _iter_hf_batches(config: DataSourceConfig) -> Iterator[pd.DataFrame]:
    import pyarrow.parquet as pq

    path = fetch_interim_hf(config)
    parquet_file = pq.ParquetFile(path)
    for record_batch in parquet_file.iter_batches(batch_size=config.batch_size):
        yield record_batch.to_pandas()


# --- Official UNB/CIC source (untested — see module docstring) -------

# The classic official CICIDS2017 CICFlowMeter CSV header convention
# (GeneratedLabelledFlows.zip), mapped onto RAW_ID_COLUMNS above.
_OFFICIAL_COLUMN_MAP = {
    "Flow ID": "flow_id",
    "Source IP": "source_ip",
    "Src IP": "source_ip",
    "Source Port": "source_port",
    "Src Port": "source_port",
    "Destination IP": "destination_ip",
    "Dst IP": "destination_ip",
    "Destination Port": "destination_port",
    "Dst Port": "destination_port",
    "Protocol": "protocol",
    "Timestamp": "Timestamp",
    "Label": "attack_label",
}

# CICFlowMeter's official CSVs encode protocol numerically (IANA
# protocol numbers); the interim HF source already uses lowercase
# strings. Normalized here so clean.py never sees two conventions.
_OFFICIAL_PROTOCOL_MAP = {"6": "tcp", "17": "udp"}


def _normalize_official_batch(raw: pd.DataFrame) -> pd.DataFrame:
    raw = raw.rename(columns=lambda c: c.strip())
    raw = raw.rename(columns=_OFFICIAL_COLUMN_MAP)
    if "flow_id" not in raw.columns:
        # Official CSVs don't always include a Flow ID column; fall
        # back to the row's position in the file, made unique via the
        # file's own name by the caller if needed.
        raw["flow_id"] = raw.index
    raw["protocol"] = (
        raw["protocol"].astype(str).map(lambda p: _OFFICIAL_PROTOCOL_MAP.get(p, "other"))
    )
    return raw


def _iter_official_batches(config: DataSourceConfig) -> Iterator[pd.DataFrame]:
    csv_paths = sorted(config.csv_dir.glob("*.csv"))
    if not csv_paths:
        raise FileNotFoundError(
            f"No official CICIDS2017 CSVs found in {config.csv_dir}. "
            "Drop the UNB/CIC GeneratedLabelledFlows CSVs there, or use "
            "source='huggingface_interim'."
        )
    for csv_path in csv_paths:
        for chunk in pd.read_csv(csv_path, chunksize=config.batch_size, low_memory=False):
            chunk = _normalize_official_batch(chunk)
            # Flow IDs are only unique within a single official CSV
            # file; qualify them so they stay globally unique once all
            # files are concatenated across the 5-day capture.
            chunk["flow_id"] = chunk["flow_id"].astype(str) + f"__{csv_path.name}"
            yield chunk


def iter_raw_batches(config: DataSourceConfig) -> Iterator[pd.DataFrame]:
    """Yields the raw dataset in batches, in ONE canonical schema,
    regardless of `config.source`. This is the only function clean.py
    calls to get data."""
    if config.source == "huggingface_interim":
        yield from _iter_hf_batches(config)
    elif config.source == "official_unb":
        yield from _iter_official_batches(config)
    else:
        raise ValueError(f"Unknown data source: {config.source!r}")
