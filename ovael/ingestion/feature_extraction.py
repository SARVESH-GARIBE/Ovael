"""
STUB — Feature Extraction.

Real feature extraction (flow assembly, statistical feature computation,
windowing, protocol-aware parsing, etc.) is explicit future work and is
not implemented here. This stub performs a trivial pass-through: it
copies the identifying fields straight from RawTraffic into a
FeatureVector and attaches an obviously-placeholder `features` dict, so
nothing downstream can mistake this for real feature engineering.
"""

from __future__ import annotations

from ovael.contracts.schemas import FeatureVector, RawTraffic

# Obviously fake: a single named placeholder feature, not a real
# engineered feature set.
PLACEHOLDER_FEATURES: dict[str, float] = {"placeholder_feature": 0.0}


def extract_features(raw_traffic: RawTraffic) -> FeatureVector:
    """Pass-through stub: RawTraffic -> FeatureVector.

    Does not compute any real features. Exists only to prove the shape
    of the ingestion -> detection/novelty boundary.
    """
    return FeatureVector(
        source_ip=raw_traffic.source_ip,
        destination_ip=raw_traffic.destination_ip,
        source_port=raw_traffic.source_port,
        destination_port=raw_traffic.destination_port,
        protocol=raw_traffic.protocol,
        payload_size=raw_traffic.payload_size,
        timestamp=raw_traffic.timestamp,
        features=dict(PLACEHOLDER_FEATURES),
        metadata={"stub": True},
    )
