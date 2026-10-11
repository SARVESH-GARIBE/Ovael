"""Synthetic network flows, used in two places:

1. Bootstrap training when no recorded sandbox dataset exists yet (`ovael train network` with no
   CSV). Models trained this way are tagged `label_source=synthetic_bootstrap` and the dashboard
   shows that, so nobody mistakes them for models trained on real captures.
2. The traffic simulator behind POST /api/simulate, which pushes these flows through the real
   detect() -> orchestrator -> storage -> WebSocket path for demos without Docker.

Each class is a set of feature distributions shaped after how the attack behaves on the wire
(see orchestrator/taxonomy.py for the narrative). They are deliberately noisy and overlapping so
the classifier does not get a trivially separable problem.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from ..feature_extraction.network_schema import NETWORK_FEATURES

NETWORK_CLASSES = ["benign", "dos_flood", "slow_dos", "port_scan", "brute_force", "web_attack"]

ATTACKER_IPS = {
    "dos_flood": "172.28.0.66",
    "slow_dos": "172.28.0.67",
    "port_scan": "172.28.0.68",
    "brute_force": "172.28.0.69",
    "web_attack": "172.28.0.70",
    "novel": "172.28.0.99",
}
VICTIM_IP = "172.28.0.10"


def _ln(rng, mean, sigma, n):
    return rng.lognormal(np.log(mean), sigma, n)


def _flows(cls: str, n: int, rng: np.random.Generator) -> pd.DataFrame:
    z = np.zeros(n)
    if cls == "benign":
        port = rng.choice([80, 443, 443, 443, 53, 22, 8080], n)
        proto = np.where(port == 53, 17, 6)
        fwd = rng.integers(3, 40, n)
        bwd = (fwd * rng.uniform(0.8, 3.0, n)).astype(int)
        dur = _ln(rng, 1.5, 1.2, n)
        f = dict(protocol=proto, dst_port=port, flow_duration=dur, total_fwd_packets=fwd,
                 total_bwd_packets=bwd, fwd_pkt_len_mean=_ln(rng, 220, 0.6, n),
                 bwd_pkt_len_mean=_ln(rng, 900, 0.5, n), syn_flag_count=np.where(proto == 6, 1, 0),
                 ack_flag_count=fwd + bwd - 1, fin_flag_count=rng.integers(0, 3, n),
                 rst_flag_count=rng.binomial(1, 0.05, n), psh_flag_count=rng.integers(1, 10, n),
                 init_win_bytes_fwd=rng.choice([29200, 64240, 65535], n),
                 src_conn_rate_10s=rng.integers(1, 12, n), src_distinct_dst_ports_10s=rng.integers(1, 4, n))
    elif cls == "dos_flood":
        fwd = rng.integers(1, 4, n)
        dur = _ln(rng, 0.002, 1.0, n)
        f = dict(protocol=rng.choice([6, 6, 6, 17], n), dst_port=rng.choice([80, 443], n),
                 flow_duration=dur, total_fwd_packets=fwd, total_bwd_packets=rng.integers(0, 2, n),
                 fwd_pkt_len_mean=_ln(rng, 60, 0.2, n), bwd_pkt_len_mean=_ln(rng, 58, 0.3, n),
                 syn_flag_count=fwd, ack_flag_count=rng.integers(0, 2, n), fin_flag_count=z,
                 rst_flag_count=rng.binomial(1, 0.4, n), psh_flag_count=z,
                 init_win_bytes_fwd=rng.choice([512, 1024, 64], n),
                 src_conn_rate_10s=rng.integers(400, 5000, n), src_distinct_dst_ports_10s=rng.integers(1, 3, n))
    elif cls == "slow_dos":
        fwd = rng.integers(4, 15, n)
        dur = rng.uniform(10, 15, n)
        f = dict(protocol=np.full(n, 6), dst_port=np.full(n, 80), flow_duration=dur,
                 total_fwd_packets=fwd, total_bwd_packets=rng.integers(1, 6, n),
                 fwd_pkt_len_mean=_ln(rng, 25, 0.4, n), bwd_pkt_len_mean=_ln(rng, 60, 0.3, n),
                 syn_flag_count=np.ones(n), ack_flag_count=fwd, fin_flag_count=z, rst_flag_count=z,
                 psh_flag_count=fwd - 1, init_win_bytes_fwd=rng.choice([29200, 64240], n),
                 src_conn_rate_10s=rng.integers(50, 400, n), src_distinct_dst_ports_10s=np.ones(n))
    elif cls == "port_scan":
        f = dict(protocol=np.full(n, 6), dst_port=rng.integers(1, 10000, n),
                 flow_duration=_ln(rng, 0.0005, 0.8, n), total_fwd_packets=rng.integers(1, 3, n),
                 total_bwd_packets=rng.integers(0, 2, n), fwd_pkt_len_mean=_ln(rng, 44, 0.1, n),
                 bwd_pkt_len_mean=_ln(rng, 40, 0.2, n), syn_flag_count=np.ones(n),
                 ack_flag_count=rng.integers(0, 2, n), fin_flag_count=z,
                 rst_flag_count=rng.integers(0, 2, n), psh_flag_count=z,
                 init_win_bytes_fwd=rng.choice([1024, 2048, 4096], n),
                 src_conn_rate_10s=rng.integers(60, 1000, n),
                 src_distinct_dst_ports_10s=rng.integers(40, 1000, n))
    elif cls == "brute_force":
        fwd = rng.integers(10, 30, n)
        f = dict(protocol=np.full(n, 6), dst_port=rng.choice([22, 22, 21], n),
                 flow_duration=_ln(rng, 2.5, 0.4, n), total_fwd_packets=fwd,
                 total_bwd_packets=(fwd * rng.uniform(0.8, 1.3, n)).astype(int),
                 fwd_pkt_len_mean=_ln(rng, 90, 0.3, n), bwd_pkt_len_mean=_ln(rng, 110, 0.3, n),
                 syn_flag_count=np.ones(n), ack_flag_count=fwd * 2 - 1,
                 fin_flag_count=rng.integers(1, 3, n), rst_flag_count=rng.binomial(1, 0.3, n),
                 psh_flag_count=(fwd * 0.6).astype(int), init_win_bytes_fwd=rng.choice([29200, 64240], n),
                 src_conn_rate_10s=rng.integers(15, 120, n), src_distinct_dst_ports_10s=np.ones(n))
    elif cls == "web_attack":
        fwd = rng.integers(4, 14, n)
        f = dict(protocol=np.full(n, 6), dst_port=rng.choice([80, 8080, 443], n),
                 flow_duration=_ln(rng, 0.4, 0.8, n), total_fwd_packets=fwd,
                 total_bwd_packets=(fwd * rng.uniform(0.7, 1.5, n)).astype(int),
                 fwd_pkt_len_mean=_ln(rng, 650, 0.4, n), bwd_pkt_len_mean=_ln(rng, 500, 0.5, n),
                 syn_flag_count=np.ones(n), ack_flag_count=fwd * 2 - 1,
                 fin_flag_count=rng.integers(1, 3, n), rst_flag_count=rng.binomial(1, 0.1, n),
                 psh_flag_count=(fwd * 0.5).astype(int) + 1, init_win_bytes_fwd=rng.choice([29200, 64240], n),
                 src_conn_rate_10s=rng.integers(5, 60, n), src_distinct_dst_ports_10s=rng.integers(1, 3, n))
    elif cls == "novel":
        # Not a training class: exfiltration-like behaviour that sits outside every class above.
        fwd = rng.integers(200, 600, n)
        f = dict(protocol=np.full(n, 17), dst_port=rng.integers(30000, 60000, n),
                 flow_duration=rng.uniform(5, 15, n), total_fwd_packets=fwd,
                 total_bwd_packets=rng.integers(0, 3, n), fwd_pkt_len_mean=_ln(rng, 1400, 0.05, n),
                 bwd_pkt_len_mean=_ln(rng, 40, 0.2, n), syn_flag_count=z, ack_flag_count=z,
                 fin_flag_count=z, rst_flag_count=z, psh_flag_count=z, init_win_bytes_fwd=z,
                 src_conn_rate_10s=rng.integers(1, 4, n), src_distinct_dst_ports_10s=np.ones(n))
    else:
        raise ValueError(f"unknown synthetic class {cls!r}")

    df = pd.DataFrame(f)
    total = df.total_fwd_packets + df.total_bwd_packets
    df["total_fwd_bytes"] = df.total_fwd_packets * df.fwd_pkt_len_mean
    df["total_bwd_bytes"] = df.total_bwd_packets * df.bwd_pkt_len_mean
    df["pkt_len_std"] = np.abs(df.fwd_pkt_len_mean - df.bwd_pkt_len_mean) * rng.uniform(0.2, 0.6, n)
    df["flow_bytes_per_s"] = (df.total_fwd_bytes + df.total_bwd_bytes) / df.flow_duration
    df["flow_pkts_per_s"] = total / df.flow_duration
    df["flow_iat_mean"] = df.flow_duration / np.maximum(total - 1, 1)
    df["flow_iat_std"] = df.flow_iat_mean * rng.uniform(0.1, 1.5, n)
    df["fwd_iat_mean"] = df.flow_duration / np.maximum(df.total_fwd_packets - 1, 1)
    df["down_up_ratio"] = df.total_bwd_packets / np.maximum(df.total_fwd_packets, 1)
    return df[NETWORK_FEATURES].astype(float)


def generate(n_per_class: int = 1500, seed: int = 7, classes: list[str] | None = None) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    frames = []
    for cls in classes or NETWORK_CLASSES:
        df = _flows(cls, n_per_class * (3 if cls == "benign" else 1), rng)
        df["label"] = cls
        frames.append(df)
    return pd.concat(frames, ignore_index=True).sample(frac=1.0, random_state=seed).reset_index(drop=True)


def sample_flow(cls: str, rng: np.random.Generator) -> tuple[dict, dict]:
    """One synthetic flow plus plausible sandbox metadata, for the simulator."""
    row = _flows(cls, 1, rng).iloc[0].to_dict()
    src = ATTACKER_IPS.get(cls, f"172.28.0.{int(rng.integers(100, 200))}")
    meta = {"src_ip": src, "dst_ip": VICTIM_IP, "src_port": int(rng.integers(30000, 65000)),
            "dst_port": int(row["dst_port"]), "protocol": int(row["protocol"])}
    return row, meta
