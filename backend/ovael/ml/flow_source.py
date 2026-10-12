"""Where demo and lab flows come from.

When a recorded network dataset exists (e.g. CIC-IDS2017 imported with `ovael dataset
import-cicids`), the simulator, the evasion lab and the learning-loop probe replay REAL flows from
it; "novel" means the held-out class (real botnet flows the model never trained on). Without one,
they fall back to the synthetic profiles in synthetic.py.

Replayed flows keep their real features but get sandbox addresses (attacker 172.28.0.6x, victim
172.28.0.10), because auto-defense only ever acts inside the sandbox subnet.
"""

from __future__ import annotations

import threading
from pathlib import Path

import numpy as np
import pandas as pd

from ..config import Settings
from ..feature_extraction.network_schema import NETWORK_FEATURES
from . import synthetic

_lock = threading.Lock()
_cache: dict[tuple, "FlowSource"] = {}


class FlowSource:
    def __init__(self, settings: Settings):
        self.groups: dict[str, pd.DataFrame] = {}
        path, unknown = Path(settings.network_dataset), Path(settings.network_unknown_dataset)
        if path.exists():
            df = pd.read_csv(path, low_memory=False)
            for label, g in df.groupby("label"):
                self.groups[str(label)] = g[NETWORK_FEATURES].reset_index(drop=True)
            if unknown.exists():
                self.groups["novel"] = pd.read_csv(unknown, low_memory=False)[NETWORK_FEATURES]
        self.real = bool(self.groups)
        self.name = "cicids2017 replay" if self.real else "synthetic"

    def has(self, cls: str) -> bool:
        return cls in self.groups if self.real else True

    def frame(self, cls: str, n: int, seed: int = 7) -> pd.DataFrame:
        if self.real and cls in self.groups:
            g = self.groups[cls]
            return g.sample(n, replace=len(g) < n, random_state=seed).reset_index(drop=True).astype(float)
        return synthetic.generate(n_per_class=n, seed=seed, classes=[cls]).drop(columns="label").head(n)

    def sample(self, cls: str, rng: np.random.Generator) -> tuple[dict, dict]:
        if not (self.real and cls in self.groups):
            return synthetic.sample_flow(cls, rng)
        g = self.groups[cls]
        row = g.iloc[int(rng.integers(len(g)))].to_dict()
        row = {k: (None if pd.isna(v) else float(v)) for k, v in row.items()}
        src = synthetic.ATTACKER_IPS.get(cls, f"172.28.0.{int(rng.integers(100, 200))}")
        meta = {"src_ip": src, "dst_ip": synthetic.VICTIM_IP, "src_port": int(rng.integers(30000, 65000)),
                "dst_port": int(row.get("dst_port") or 0), "protocol": int(row.get("protocol") or 6)}
        return row, meta


def get_flow_source(settings: Settings) -> FlowSource:
    p = Path(settings.network_dataset)
    key = (str(p), p.stat().st_mtime if p.exists() else None)
    with _lock:
        if key not in _cache:
            _cache.clear()
            _cache[key] = FlowSource(settings)
        return _cache[key]
