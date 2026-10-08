"""
Loads CICIDS2017's pre-extracted flow CSVs (GeneratedLabelledFlows) and
maps them onto this project's FeatureVector contract
(feature_extraction/schema.py).

This does NOT introduce a new schema. It only pulls the subset of
CICIDS2017's ~78 CICFlowMeter columns that correspond to the 6 fields in
NUMERIC_FEATURE_ORDER, so both models train on exactly the same shape of
data that mock_feature_generator.py produces.

Known CICIDS2017 quirks handled here:
- Column headers have inconsistent leading/trailing whitespace.
- Rows with Infinity/NaN in rate-based columns (divide-by-zero during the
  original CICFlowMeter extraction) are dropped, not imputed.
- CICIDS2017's Protocol column is numeric (6/17/1); the schema wants the
  string "TCP"/"UDP"/"ICMP", so it's mapped here.
- CICIDS2017's label set is far more fine-grained than LABELS
  ("normal", "ddos", "port_scan", "exfiltration") — attack types that
  don't map cleanly onto one of the four categories are DROPPED, not
  force-fit into the wrong bucket. See LABEL_MAP below.
"""

import glob

import numpy as np
import pandas as pd

from feature_extraction.schema import LABELS, NORMAL_LABEL, FeatureVector, validate

PROTOCOL_MAP = {6: "TCP", 17: "UDP", 1: "ICMP"}

# Only attack types with a clean match to our four LABELS are kept.
# Everything else (web attacks, botnet, brute force, heartbleed) is
# dropped rather than mapped into the wrong category.
LABEL_MAP = {
    "benign": "normal",
    "ddos": "ddos",
    "dos hulk": "ddos",
    "dos goldeneye": "ddos",
    "dos slowloris": "ddos",
    "dos slowhttptest": "ddos",
    "portscan": "port_scan",
    "infiltration": "exfiltration",
}


def _normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    df.columns = [c.strip().lower() for c in df.columns]
    return df


def load_and_map(csv_dir: str) -> list[FeatureVector]:
    """Read every CSV in csv_dir, keep rows whose label maps onto LABELS,
    and return validated FeatureVector instances."""
    paths = glob.glob(f"{csv_dir}/*.csv")
    if not paths:
        raise FileNotFoundError(f"No CSV files found in {csv_dir}")

    frames = [_normalize_columns(pd.read_csv(p, low_memory=False)) for p in paths]
    df = pd.concat(frames, ignore_index=True)

    df = df.replace([np.inf, -np.inf], np.nan)
    numeric_cols = df.select_dtypes(include=[np.number]).columns
    before = len(df)
    df = df.dropna(subset=numeric_cols)
    print(f"Dropped {before - len(df)} rows with Infinity/NaN ({(before - len(df)) / max(before, 1):.2%})")

    df["label"] = df["label"].str.strip().str.lower().map(LABEL_MAP)
    dropped_unmapped = df["label"].isna().sum()
    df = df.dropna(subset=["label"])
    print(f"Dropped {dropped_unmapped} rows with attack types outside {LABELS}")

    vectors: list[FeatureVector] = []
    skipped = 0
    for _, row in df.iterrows():
        try:
            duration_sec = row["flow duration"] / 1_000_000  # microseconds -> seconds
            fwd_pkts = row.get("total fwd packets", 0)
            bwd_pkts = row.get("total backward packets", 0)
            packet_count = fwd_pkts + bwd_pkts
            byte_count = row.get("total length of fwd packets", 0) + row.get("total length of bwd packets", 0)
            safe_duration = duration_sec if duration_sec > 0 else 1e-6

            fv = FeatureVector(
                src_ip=row.get("source ip", "0.0.0.0"),
                dst_ip=row.get("destination ip", "0.0.0.0"),
                src_port=int(row.get("source port", 0)),
                dst_port=int(row["destination port"]),
                protocol=PROTOCOL_MAP.get(int(row["protocol"]), "TCP"),
                byte_count=float(byte_count),
                duration=float(duration_sec),
                packet_rate=float(packet_count / safe_duration),
                packet_count=int(packet_count),
                label=row["label"],
            )
            validate(fv)
            vectors.append(fv)
        except (ValueError, KeyError):
            skipped += 1
            continue

    print(f"Skipped {skipped} rows that failed validate()")
    print(f"Loaded {len(vectors)} valid FeatureVector rows")
    return vectors


def split_for_training(vectors: list[FeatureVector]):
    """multiclass_vectors: everything, all labels.
    novelty_vectors: NORMAL_LABEL only, per the novelty detector's
    requirement to train exclusively on benign traffic."""
    novelty_vectors = [v for v in vectors if v.label == NORMAL_LABEL]
    return vectors, novelty_vectors


if __name__ == "__main__":
    vectors = load_and_map("data/raw/CICIDS2017/GeneratedLabelledFlows")
    multiclass_vectors, novelty_vectors = split_for_training(vectors)
    print(f"Multiclass training rows: {len(multiclass_vectors)}")
    print(f"Novelty (normal-only) training rows: {len(novelty_vectors)}")
