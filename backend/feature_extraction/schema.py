"""
Feature vector schema — SHARED CONTRACT between feature_extraction/
(owned by the networking teammate) and ml/ (owned by the ML lead).

This file defines the exact shape of the object that feature_extraction
must produce for every closed flow, and that ml/multiclass/model.py and
ml/novelty/model.py consume. It is not throwaway/mock code: real
feature-extraction code must produce dicts that satisfy `FeatureVector`
and pass `validate()`, and any schema change must be made here first and
communicated to both sides.

Until real feature extraction exists, ml/mock_feature_generator.py
produces synthetic rows conforming to this exact schema so the models
can be built and validated without being blocked on the networking
teammate's Docker/capture pipeline.
"""

from dataclasses import dataclass

# Canonical attack categories the Multiclass Model predicts and the mock
# data generator labels. Keep this list in sync with orchestrator's
# decision table when that module is built.
LABELS = ("normal", "ddos", "port_scan", "exfiltration")

# Special label used only by the Novelty Detector's training data
# selection (it trains on "normal" rows only, regardless of how many
# attack categories exist).
NORMAL_LABEL = "normal"

# Exact order of numeric fields fed into both ML models. Order matters:
# both model.py modules build/consume vectors in this order via
# `to_vector()` below. Do not reorder without retraining both models.
NUMERIC_FEATURE_ORDER = (
    "byte_count",
    "duration",
    "packet_rate",
    "packet_count",
    "src_port",
    "dst_port",
)


@dataclass
class FeatureVector:
    """One row = one closed network flow, keyed by the 5-tuple.

    Identifying fields (src_ip, dst_ip, protocol) are for display,
    logging, and DB storage — they are NOT fed into the models directly
    (raw IP strings aren't usable ML features without an encoding step
    that doesn't exist yet). Only the fields listed in
    NUMERIC_FEATURE_ORDER are used as model input.
    """

    # 5-tuple identity (flow key) — display/storage only
    src_ip: str
    dst_ip: str
    src_port: int
    dst_port: int
    protocol: str  # "TCP" | "UDP" | "ICMP"

    # Numeric features — actual model input, in NUMERIC_FEATURE_ORDER
    byte_count: float
    duration: float  # seconds
    packet_rate: float  # packets/sec
    packet_count: int

    # Ground-truth label, only present for training/mock data — real
    # traffic passed to the models at inference time will not have this.
    label: str | None = None


def validate(feature_vector: FeatureVector) -> None:
    """Raise ValueError if a FeatureVector doesn't satisfy the contract."""
    if feature_vector.protocol not in ("TCP", "UDP", "ICMP"):
        raise ValueError(f"unsupported protocol: {feature_vector.protocol!r}")
    if feature_vector.duration < 0 or feature_vector.byte_count < 0:
        raise ValueError("duration and byte_count must be non-negative")
    if feature_vector.label is not None and feature_vector.label not in LABELS:
        raise ValueError(f"unknown label: {feature_vector.label!r}")


def to_vector(feature_vector: FeatureVector) -> list[float]:
    """Extract the numeric model-input array, in NUMERIC_FEATURE_ORDER."""
    return [float(getattr(feature_vector, name)) for name in NUMERIC_FEATURE_ORDER]
