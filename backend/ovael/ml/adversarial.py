"""Evasion lab: how far can a known attack be modified before each model stops catching it?

This works in feature space, on the same 24 numbers the models see. It does not generate traffic.
A batch of flows of one attack class is pushed, step by step, toward what normal traffic looks
like, and every step goes through the real detect() and decision table. The output answers the
architecture's adversarial question: when the classifier stops recognising a modified attack,
does the anomaly detector still notice it?

Techniques (strength 0 = the original attack, 1 = fully modified):
    slow_down     send at a lower rate and spread packets out in time
    pad_packets   make packet sizes look like normal traffic
    spread_out    split the work across many sources so each one looks quiet
    mimic         move every feature toward a real normal flow
"""

from __future__ import annotations

from collections import Counter

import numpy as np
import pandas as pd

from ..feature_extraction.network_schema import NETWORK_FEATURES
from . import synthetic

TECHNIQUES: dict[str, str] = {
    "slow_down": "Send slower: lower rates, longer gaps between packets",
    "pad_packets": "Pad packets so their sizes look like normal traffic",
    "spread_out": "Spread the attack over many sources so each looks quiet",
    "mimic": "Move every feature toward a real normal flow",
}
ATTACKS = ["dos_flood", "port_scan", "slow_dos", "brute_force", "web_attack"]

RATE_COLS = ["flow_pkts_per_s", "flow_bytes_per_s"]
GAP_COLS = ["flow_iat_mean", "flow_iat_std", "fwd_iat_mean"]
SIZE_COLS = ["fwd_pkt_len_mean", "bwd_pkt_len_mean", "pkt_len_std"]
CONTEXT_COLS = ["src_conn_rate_10s", "src_distinct_dst_ports_10s"]


def _toward(a: pd.Series, b, s: float) -> pd.Series:
    return a + (b - a) * s


def perturb(attack: pd.DataFrame, technique: str, s: float, benign: pd.DataFrame,
            rng: np.random.Generator) -> pd.DataFrame:
    df = attack.copy()
    if s <= 0:
        return df
    med = benign.median(numeric_only=True)
    if technique == "slow_down":
        slow = 1 - 0.97 * s  # up to ~33x slower
        for c in RATE_COLS + ["src_conn_rate_10s"]:
            df[c] = df[c] * slow
        for c in GAP_COLS:
            df[c] = df[c] / slow
        df["flow_duration"] = df["flow_duration"] / slow
    elif technique == "pad_packets":
        for c in SIZE_COLS:
            df[c] = _toward(df[c], med[c], s)
        df["total_fwd_bytes"] = df["total_fwd_packets"] * df["fwd_pkt_len_mean"]
        df["total_bwd_bytes"] = df["total_bwd_packets"] * df["bwd_pkt_len_mean"]
        df["flow_bytes_per_s"] = (df["total_fwd_bytes"] + df["total_bwd_bytes"]) / df["flow_duration"].clip(lower=1e-6)
    elif technique == "spread_out":
        for c in CONTEXT_COLS:
            df[c] = _toward(df[c], med[c], s)
    elif technique == "mimic":
        donors = benign.sample(len(df), replace=True, random_state=int(rng.integers(1 << 31))).reset_index(drop=True)
        df = _toward(df.reset_index(drop=True), donors, s)
    else:
        raise ValueError(f"unknown technique {technique!r}")
    return df[NETWORK_FEATURES]


def sweep(engine, attack: str, technique: str, steps: int = 11, n: int = 80, seed: int = 7,
          source=None) -> dict:
    if attack not in ATTACKS:
        raise ValueError(f"attack must be one of {ATTACKS}")
    rng = np.random.default_rng(seed)
    if source is not None:  # real flows (CIC-IDS2017 replay) when available
        base = source.frame(attack, n, seed)
        benign = source.frame("benign", 400, seed + 1)
    else:
        base = synthetic.generate(n_per_class=n, seed=seed, classes=[attack]).drop(columns="label")
        benign = synthetic.generate(n_per_class=200, seed=seed + 1, classes=["benign"]).drop(columns="label")

    points = []
    for i in range(steps):
        s = i / (steps - 1)
        X = perturb(base, technique, s, benign, rng)
        results = engine.detect_many("network", X.to_dict("records"))
        levels = Counter(r.risk_level for r in results)
        k = len(results)
        points.append({
            "strength": round(s, 3),
            # classifier still names the original attack, confidently
            "recognized": round(sum(r.is_attack and r.label == attack for r in results) / k, 4),
            "attack_any": round(sum(r.is_attack for r in results) / k, 4),
            "confidence": round(float(np.mean([r.probabilities.get(attack, 0.0) for r in results])), 4),
            "unusual": round(sum(r.is_unusual for r in results) / k, 4),
            "caught": round(sum(r.risk_level != "low" for r in results) / k, 4),
            "blocked": round(levels.get("high", 0) / k, 4),
            "levels": {lvl: round(levels.get(lvl, 0) / k, 4) for lvl in ("high", "medium", "suspicious", "low")},
            "top_labels": dict(Counter(r.label for r in results).most_common(3)),
        })

    def first(pred):
        return next((p["strength"] for p in points if pred(p)), None)

    breaks_at = first(lambda p: p["recognized"] < 0.5)
    rescue = next((p for p in points if p["strength"] == breaks_at), None) if breaks_at is not None else None
    return {
        "attack": attack,
        "technique": technique,
        "technique_description": TECHNIQUES[technique],
        "flows_per_step": n,
        "flow_source": getattr(source, "name", "synthetic"),
        "model_version": engine.registry.active("network").version,
        "points": points,
        "summary": {
            "classifier_breaks_at": breaks_at,
            "caught_where_classifier_breaks": rescue["caught"] if rescue else None,
            "unusual_where_classifier_breaks": rescue["unusual"] if rescue else None,
            "fully_evades_at": first(lambda p: p["caught"] < 0.1),
            "caught_at_full_strength": points[-1]["caught"],
        },
    }
