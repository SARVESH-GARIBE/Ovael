"""CIC-IDS2017 -> Ovael network schema.

CIC-IDS2017 (Sharafaldin, Lashkari and Ghorbani, ICISSP 2018; Canadian Institute for
Cybersecurity) is real traffic captured over five working days in a lab network, with flows built by
CICFlowMeter and labelled per attack. The architecture names it as the primary network dataset.
We read the labelled-flow ("TrafficLabelling") files, which keep the source IP and timestamp.

Mapping to our 24 features:
  * the CICFlowMeter columns map one-to-one; durations and inter-arrival times are converted from
    microseconds to seconds
  * src_conn_rate_10s / src_distinct_dst_ports_10s are not in CIC. They are rebuilt from the
    source IP and timestamp. CIC timestamps have one-minute resolution, so the 10 s values are
    estimated from per-minute windows (count x 10/60). This is an approximation, stated here and
    in the model's label source, and it differs from the sensor's exact 10 s window.

Label mapping:
  BENIGN -> benign; DDoS, DoS Hulk, DoS GoldenEye -> dos_flood; DoS slowloris, DoS Slowhttptest
  -> slow_dos; PortScan -> port_scan; FTP-/SSH-Patator -> brute_force; Web Attack * -> web_attack;
  Bot -> botnet (held out of training: the real "unknown attack"); Infiltration (36 rows) and
  Heartbleed (11 rows) are dropped as too small to learn or evaluate.

Classes are capped (benign 80k, each attack 15k), sampled across the original sub-labels so DoS
Hulk does not crowd out GoldenEye, to keep training fast and balanced.
"""

from __future__ import annotations

import logging
from pathlib import Path

import numpy as np
import pandas as pd

from ..feature_extraction.network_schema import NETWORK_FEATURES

log = logging.getLogger(__name__)

SOURCE = "cicids2017"
HOLDOUT_CLASS = "botnet"
CAPS = {"benign": 80_000}
DEFAULT_CAP = 15_000
SEED = 42

DIRECT = {
    "protocol": "Protocol",
    "dst_port": "Destination Port",
    "total_fwd_packets": "Total Fwd Packets",
    "total_bwd_packets": "Total Backward Packets",
    "total_fwd_bytes": "Total Length of Fwd Packets",
    "total_bwd_bytes": "Total Length of Bwd Packets",
    "fwd_pkt_len_mean": "Fwd Packet Length Mean",
    "bwd_pkt_len_mean": "Bwd Packet Length Mean",
    "pkt_len_std": "Packet Length Std",
    "flow_bytes_per_s": "Flow Bytes/s",
    "flow_pkts_per_s": "Flow Packets/s",
    "syn_flag_count": "SYN Flag Count",
    "ack_flag_count": "ACK Flag Count",
    "fin_flag_count": "FIN Flag Count",
    "rst_flag_count": "RST Flag Count",
    "psh_flag_count": "PSH Flag Count",
    "down_up_ratio": "Down/Up Ratio",
    "init_win_bytes_fwd": "Init_Win_bytes_forward",
}
MICROSECONDS = {
    "flow_duration": "Flow Duration",
    "flow_iat_mean": "Flow IAT Mean",
    "flow_iat_std": "Flow IAT Std",
    "fwd_iat_mean": "Fwd IAT Mean",
}
NEEDED = ["Source IP", "Destination IP", "Timestamp", "Label", *DIRECT.values(), *MICROSECONDS.values()]


def map_label(raw: str) -> str | None:
    s = str(raw).strip().lower()
    if s == "benign":
        return "benign"
    if s in ("ddos", "dos hulk", "dos goldeneye"):
        return "dos_flood"
    if s in ("dos slowloris", "dos slowhttptest"):
        return "slow_dos"
    if s == "portscan":
        return "port_scan"
    if s.endswith("patator"):
        return "brute_force"
    if s.startswith("web attack"):
        return "web_attack"
    if s == "bot":
        return "botnet"
    return None  # infiltration, heartbleed


def convert_frame(raw: pd.DataFrame) -> pd.DataFrame:
    raw = raw.rename(columns=lambda c: c.strip())
    out = pd.DataFrame({ours: pd.to_numeric(raw[theirs], errors="coerce") for ours, theirs in DIRECT.items()})
    for ours, theirs in MICROSECONDS.items():
        out[ours] = pd.to_numeric(raw[theirs], errors="coerce") / 1e6
    out = out.replace([np.inf, -np.inf], np.nan)
    # negative values are CICFlowMeter artefacts (e.g. Init_Win -1 = not seen)
    out = out.mask(out < 0)

    ts = pd.to_datetime(raw["Timestamp"])
    minute = ts.dt.floor("min")
    keys = pd.DataFrame({"src": raw["Source IP"].astype(str), "minute": minute, "port": out["dst_port"]})
    per_min = keys.groupby(["src", "minute"])["port"].agg(["size", "nunique"])
    joined = keys.join(per_min, on=["src", "minute"])
    out["src_conn_rate_10s"] = np.ceil(joined["size"].to_numpy() * 10 / 60)
    out["src_distinct_dst_ports_10s"] = np.ceil(joined["nunique"].to_numpy() * 10 / 60)

    out["label"] = raw["Label"].map(map_label)
    out["orig_label"] = raw["Label"].astype(str).str.replace("\x96", "-", regex=False).str.strip()
    out["src_ip"] = raw["Source IP"].astype(str)
    out["dst_ip"] = raw["Destination IP"].astype(str)
    return out[out["label"].notna()]


def build(src_dir: Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Returns (training rows, held-out unknown-attack rows)."""
    files = sorted(Path(src_dir).glob("*.parquet")) + sorted(Path(src_dir).glob("*.csv"))
    if not files:
        raise FileNotFoundError(f"no CIC-IDS2017 parquet/csv files in {src_dir}")
    frames = []
    for f in files:
        raw = pd.read_parquet(f) if f.suffix == ".parquet" else pd.read_csv(f, encoding="latin-1", low_memory=False)
        raw = raw.rename(columns=lambda c: c.strip())
        missing = [c for c in NEEDED if c not in raw.columns]
        if missing:
            raise ValueError(f"{f.name}: missing columns {missing} (use the labelled-flow files)")
        part = convert_frame(raw[NEEDED])
        log.info("%s: %d rows", f.name, len(part))
        frames.append(part)
    df = pd.concat(frames, ignore_index=True)

    holdout = df[df["label"] == HOLDOUT_CLASS]
    df = df[df["label"] != HOLDOUT_CLASS]
    rng = np.random.default_rng(SEED)
    parts = []
    for label, group in df.groupby("label"):
        cap = CAPS.get(label, DEFAULT_CAP)
        if len(group) <= cap:
            parts.append(group)
            continue
        # spread the cap evenly over the original sub-labels (Hulk vs GoldenEye vs DDoS, ...)
        subs = group.groupby("orig_label")
        share = max(cap // subs.ngroups, 1)
        picked = [g.sample(min(len(g), share), random_state=int(rng.integers(1 << 31))) for _, g in subs]
        sample = pd.concat(picked)
        if len(sample) < cap:
            rest = group.drop(sample.index)
            sample = pd.concat([sample, rest.sample(min(len(rest), cap - len(sample)), random_state=SEED)])
        parts.append(sample)
    train = pd.concat(parts).sample(frac=1.0, random_state=SEED).reset_index(drop=True)
    cols = [*NETWORK_FEATURES, "label", "orig_label", "src_ip", "dst_ip"]
    train = train[cols].assign(source=SOURCE)
    holdout = holdout[cols].assign(source=SOURCE).reset_index(drop=True)
    return train, holdout
