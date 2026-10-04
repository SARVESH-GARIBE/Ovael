"""
STUB — Feature Extraction.

Real feature extraction (flow assembly, statistical feature computation,
windowing, protocol-aware parsing, etc.) is explicit future work and is
not implemented here. This stub performs a trivial pass-through: it
copies the identifying fields straight from RawTraffic into a
FeatureVector.

Still a pass-through, not real feature engineering: if the caller
already computed numeric flow features and attached them to
RawTraffic.flow_features (e.g. an offline dataset pipeline reading real
flow-statistics columns), they are forwarded into FeatureVector.features
unchanged - no transformation, no filtering, no renaming. This function
still does not compute anything itself. If flow_features is empty (the
default - true for every existing caller that never sets it), the
original obviously-placeholder features dict is used instead, exactly
as before.
"""

from __future__ import annotations

from ovael.contracts.schemas import FeatureVector, RawTraffic

# Obviously fake: a single named placeholder feature, not a real
# engineered feature set. Used only when the caller supplies no
# flow_features of its own.
PLACEHOLDER_FEATURES: dict[str, float] = {"placeholder_feature": 0.0}


def extract_features(raw_traffic: RawTraffic) -> FeatureVector:
    """Pass-through stub: RawTraffic -> FeatureVector.

    Does not compute any real features. Exists only to prove the shape
    of the ingestion -> detection/novelty boundary.
    """
    features = dict(raw_traffic.flow_features) if raw_traffic.flow_features else dict(
        PLACEHOLDER_FEATURES
    )
    return FeatureVector(
        source_ip=raw_traffic.source_ip,
        destination_ip=raw_traffic.destination_ip,
        source_port=raw_traffic.source_port,
        destination_port=raw_traffic.destination_port,
        protocol=raw_traffic.protocol,
        payload_size=raw_traffic.payload_size,
        timestamp=raw_traffic.timestamp,
        features=features,
        metadata={"stub": True},
    )
