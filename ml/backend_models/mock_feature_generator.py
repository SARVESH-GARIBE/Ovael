"""
Generates synthetic feature vectors that conform to
feature_extraction/schema.py, so ml/multiclass and ml/novelty can be
built and validated before the real Docker/capture pipeline exists.

MOCK DATA ONLY — swap this out for feature_extraction's real output
once it's ready. Distributions below are hand-picked to be
directionally realistic per class (e.g. DDoS = high packet rate, short
duration), not derived from a real capture.
"""

import random

import numpy as np

from feature_extraction.schema import FeatureVector

COMMON_PORTS = (80, 443, 22, 53, 3306, 8080)


def _random_ip() -> str:
    return ".".join(str(random.randint(1, 254)) for _ in range(4))


def _clip_positive(value: float) -> float:
    return max(value, 0.0)


def _generate_normal(rng: np.random.Generator) -> FeatureVector:
    return FeatureVector(
        src_ip=_random_ip(),
        dst_ip=_random_ip(),
        src_port=random.randint(1024, 65535),
        dst_port=random.choice(COMMON_PORTS),
        protocol=random.choice(("TCP", "UDP")),
        byte_count=_clip_positive(rng.normal(5000, 2000)),
        duration=_clip_positive(rng.normal(2.0, 1.0)),
        packet_rate=_clip_positive(rng.normal(20, 8)),
        packet_count=int(_clip_positive(rng.normal(40, 15))),
        label="normal",
    )


def _generate_ddos(rng: np.random.Generator) -> FeatureVector:
    # Flooding: very high packet rate, short-lived flow, large total bytes.
    return FeatureVector(
        src_ip=_random_ip(),
        dst_ip=_random_ip(),
        src_port=random.randint(1024, 65535),
        dst_port=random.choice(COMMON_PORTS),
        protocol=random.choice(("TCP", "UDP", "ICMP")),
        byte_count=_clip_positive(rng.normal(200000, 80000)),
        duration=_clip_positive(rng.normal(0.5, 0.3)),
        packet_rate=_clip_positive(rng.normal(2000, 600)),
        packet_count=int(_clip_positive(rng.normal(1500, 400))),
        label="ddos",
    )


def _generate_port_scan(rng: np.random.Generator) -> FeatureVector:
    # Recon: tiny packets, near-instant flows, many distinct dst ports.
    return FeatureVector(
        src_ip=_random_ip(),
        dst_ip=_random_ip(),
        src_port=random.randint(1024, 65535),
        dst_port=random.randint(1, 65535),
        protocol="TCP",
        byte_count=_clip_positive(rng.normal(80, 40)),
        duration=_clip_positive(rng.normal(0.05, 0.03)),
        packet_rate=_clip_positive(rng.normal(120, 50)),
        packet_count=int(_clip_positive(rng.normal(3, 1))),
        label="port_scan",
    )


def _generate_exfiltration(rng: np.random.Generator) -> FeatureVector:
    # Slow, steady, large outbound transfer to blend in with normal traffic.
    return FeatureVector(
        src_ip=_random_ip(),
        dst_ip=_random_ip(),
        src_port=random.randint(1024, 65535),
        dst_port=random.choice((443, 8080)),
        protocol="TCP",
        byte_count=_clip_positive(rng.normal(500000, 150000)),
        duration=_clip_positive(rng.normal(60.0, 20.0)),
        packet_rate=_clip_positive(rng.normal(15, 5)),
        packet_count=int(_clip_positive(rng.normal(800, 200))),
        label="exfiltration",
    )


_GENERATORS = {
    "normal": _generate_normal,
    "ddos": _generate_ddos,
    "port_scan": _generate_port_scan,
    "exfiltration": _generate_exfiltration,
}


def generate_mock_dataset(
    n_per_class: int = 300, seed: int = 42
) -> list[FeatureVector]:
    """Return a balanced, shuffled list of mock FeatureVectors covering
    every label in feature_extraction.schema.LABELS."""
    rng = np.random.default_rng(seed)
    random.seed(seed)

    rows = [
        _GENERATORS[label](rng)
        for label in _GENERATORS
        for _ in range(n_per_class)
    ]
    random.shuffle(rows)
    return rows


if __name__ == "__main__":
    sample = generate_mock_dataset(n_per_class=3)
    for row in sample[:8]:
        print(row)
