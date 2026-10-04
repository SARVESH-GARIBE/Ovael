"""extract_features() returns a FeatureVector from a RawTraffic input."""

from ovael.contracts.schemas import FeatureVector, RawTraffic
from ovael.ingestion.feature_extraction import PLACEHOLDER_FEATURES, extract_features


def _raw_traffic(**overrides) -> RawTraffic:
    defaults = dict(
        source_ip="10.0.0.5",
        destination_ip="10.0.0.9",
        source_port=51234,
        destination_port=80,
        protocol="TCP",
        payload_size=512,
        timestamp=1700000000.0,
    )
    defaults.update(overrides)
    return RawTraffic(**defaults)


def test_extract_features_returns_feature_vector():
    raw = _raw_traffic()
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


def test_extract_features_without_flow_features_uses_placeholder():
    # No flow_features set (the default) - existing Stage 1 callers are
    # unaffected and still get the original placeholder stub output.
    raw = _raw_traffic()
    assert raw.flow_features == {}

    result = extract_features(raw)

    assert result.features == PLACEHOLDER_FEATURES
    assert result.features is not PLACEHOLDER_FEATURES  # not aliased


def test_extract_features_with_flow_features_passes_them_through_unchanged():
    flow_features = {"flow_duration": 123.0, "total_fwd_packets": 7.0, "protocol_num": 6.0}
    raw = _raw_traffic(flow_features=flow_features)

    result = extract_features(raw)

    assert result.features == flow_features
    assert result.features is not flow_features  # not aliased
    # Identifying fields are unaffected by this change.
    assert result.source_ip == raw.source_ip
    assert result.payload_size == raw.payload_size
