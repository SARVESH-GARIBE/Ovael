"""extract_features() returns a FeatureVector from a RawTraffic input."""

from ovael.contracts.schemas import FeatureVector, RawTraffic
from ovael.ingestion.feature_extraction import extract_features


def test_extract_features_returns_feature_vector():
    raw = RawTraffic(
        source_ip="10.0.0.5",
        destination_ip="10.0.0.9",
        source_port=51234,
        destination_port=80,
        protocol="TCP",
        payload_size=512,
        timestamp=1700000000.0,
    )
    features = extract_features(raw)

    assert isinstance(features, FeatureVector)
    assert features.source_ip == raw.source_ip
    assert features.destination_ip == raw.destination_ip
    assert features.source_port == raw.source_port
    assert features.destination_port == raw.destination_port
    assert features.protocol == raw.protocol
    assert features.payload_size == raw.payload_size
    assert features.timestamp == raw.timestamp
    assert isinstance(features.features, dict) and features.features
