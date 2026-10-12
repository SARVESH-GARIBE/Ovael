"""Checking and importing recorded network datasets.

The lab records labelled flows with `sensor/sensor.py` (OVAEL_RECORD_CSV). Before those rows train
a model they are checked against the schema, and on import every row keeps a `source` tag so a
model's training data can always be traced back to the capture session it came from.

    python -m ovael.cli dataset check  capture.csv
    python -m ovael.cli dataset import capture.csv --source lab-2026-10-12
    python -m ovael.cli dataset info
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from ..config import Settings
from ..feature_extraction import SCHEMAS
from ..orchestrator.taxonomy import families

MIN_ROWS_PER_CLASS = 50  # below this a class is too thin to learn or to evaluate


def known_labels(module: str) -> set[str]:
    return {label.lower() for f in families(module) for label in [f.id, *f.labels]}


def check(df: pd.DataFrame, module: str = "network") -> dict:
    cols = SCHEMAS[module]
    missing = [c for c in cols if c not in df.columns]
    problems: list[str] = []
    warnings: list[str] = []
    if "label" not in df.columns:
        problems.append("no 'label' column")
    if missing:
        problems.append(f"missing feature columns: {', '.join(missing)}")
    if problems:
        return {"ok": False, "rows": int(len(df)), "problems": problems, "warnings": warnings}

    X = df[cols].apply(pd.to_numeric, errors="coerce")
    bad_values = int((~np.isfinite(X.to_numpy(dtype=float, na_value=np.nan))).sum())
    labels = df["label"].astype(str).str.strip().str.lower()
    counts = {k: int(v) for k, v in labels.value_counts().items()}
    unknown = sorted(set(counts) - known_labels(module))
    thin = sorted(k for k, v in counts.items() if v < MIN_ROWS_PER_CLASS)
    dupes = int(df.duplicated(subset=cols + ["label"]).sum())

    if not any(lbl in ("benign", "normal") for lbl in counts):
        problems.append("no benign rows: the anomaly detector learns normal behaviour from them")
    if bad_values:
        warnings.append(f"{bad_values} empty or non-numeric feature values (filled with the median when training)")
    if unknown:
        warnings.append(f"labels not in the taxonomy (they still train, shown as learned classes): {', '.join(unknown)}")
    if thin:
        warnings.append(f"classes with fewer than {MIN_ROWS_PER_CLASS} rows: {', '.join(thin)}")
    if dupes:
        warnings.append(f"{dupes} duplicate rows")
    extra = [c for c in df.columns if c not in cols and c not in ("label", "src_ip", "dst_ip", "source")]
    if extra:
        warnings.append(f"ignored columns: {', '.join(extra[:8])}{'…' if len(extra) > 8 else ''}")
    return {"ok": not problems, "rows": int(len(df)), "labels": counts, "problems": problems,
            "warnings": warnings, "duplicates": dupes}


def import_csv(src: Path, dst: Path, source: str, module: str = "network") -> dict:
    df = pd.read_csv(src)
    report = check(df, module)
    if not report["ok"]:
        raise ValueError("; ".join(report["problems"]))
    keep = SCHEMAS[module] + ["label"] + [c for c in ("src_ip", "dst_ip") if c in df.columns]
    df = df[keep].copy()
    df["label"] = df["label"].astype(str).str.strip().str.lower().replace({"normal": "benign"})
    df["source"] = source
    before = 0
    if dst.exists():
        old = pd.read_csv(dst)
        before = len(old)
        df = pd.concat([old, df], ignore_index=True)
    df = df.drop_duplicates(subset=SCHEMAS[module] + ["label"])
    dst.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(dst, index=False)
    return {"added": int(len(df) - before), "total": int(len(df)), "path": str(dst),
            "labels": {k: int(v) for k, v in df["label"].value_counts().items()}}


def info(settings: Settings) -> dict:
    """What each module currently trains on."""
    from .datasets import load_base  # noqa: PLC0415

    out = {}
    for module in ("network", "website"):
        try:
            df, source = load_base(module, settings)
        except Exception as exc:  # noqa: BLE001
            out[module] = {"error": str(exc)}
            continue
        path = settings.network_dataset if module == "network" else settings.website_dataset
        recorded = module == "website" or Path(path).exists()
        out[module] = {
            "path": str(path) if recorded else None,
            "label_source": source,
            "synthetic": source == "synthetic_bootstrap",
            "rows": int(len(df)),
            "labels": {k: int(v) for k, v in df["label"].value_counts().items()},
            "sources": ({k: int(v) for k, v in df["source"].value_counts().items()}
                        if "source" in df.columns else {}),
        }
    return out
