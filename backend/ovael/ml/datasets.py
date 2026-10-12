"""Base training datasets for each module."""

from __future__ import annotations

import logging
from pathlib import Path

import pandas as pd

from ..config import Settings
from . import synthetic
from .labeling import label_website_dataset

log = logging.getLogger(__name__)


def load_base(module: str, settings: Settings) -> tuple[pd.DataFrame, str]:
    """Return (labelled dataframe, label_source)."""
    if module == "website":
        path = Path(settings.website_dataset)
        if not path.exists():
            raise FileNotFoundError(f"website dataset not found at {path}")
        df = label_website_dataset(pd.read_csv(path))
        source = ",".join(sorted(df["label_source"].unique()))
        log.info("website dataset: %d usable rows, labels %s", len(df), df["label"].value_counts().to_dict())
        return df, source
    if module == "network":
        path = Path(settings.network_dataset)
        if path.exists():
            df = pd.read_csv(path, low_memory=False)
            if "label" not in df:
                raise ValueError(f"{path} has no 'label' column")
            source = ",".join(sorted(df["source"].astype(str).unique())) if "source" in df else "sandbox_capture"
            log.info("network dataset %s: %d rows (%s)", path, len(df), source)
            return df, source
        log.warning("no recorded network dataset at %s; using the synthetic bootstrap set", path)
        return synthetic.generate(), "synthetic_bootstrap"
    raise ValueError(f"unknown module {module!r}")


def novel_probe(module: str, settings: Settings | None = None) -> pd.DataFrame | None:
    """Rows of a behaviour no training class covers, used to measure novelty detection.

    With real data this is the held-out attack class (real CIC-IDS2017 botnet flows); otherwise
    the synthetic exfiltration-like class.
    """
    if module != "network":
        return None
    if settings is not None and Path(settings.network_unknown_dataset).exists():
        return pd.read_csv(settings.network_unknown_dataset, low_memory=False)
    return synthetic.generate(n_per_class=300, seed=99, classes=["novel"])
