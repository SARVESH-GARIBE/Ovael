"""StubDetectionModel.predict() returns a well-formed DetectionResult."""

from ovael.agents.detection.interface import DetectionModel
from ovael.agents.detection.stub import StubDetectionModel
from ovael.contracts.schemas import DetectionResult, FeatureVector


def _feature_vector() -> FeatureVector:
    return FeatureVector(
        source_ip="10.0.0.5",
        destination_ip="10.0.0.9",
        source_port=51234,
        destination_port=80,
        protocol="TCP",
        payload_size=512,
        timestamp=1700000000.0,
    )


def test_stub_detection_model_is_a_detection_model():
    assert isinstance(StubDetectionModel(), DetectionModel)


def test_stub_detection_model_returns_well_formed_result():
    result = StubDetectionModel().predict(_feature_vector())

    assert isinstance(result, DetectionResult)
    assert result.predicted_class == "unknown-placeholder"
    assert result.confidence == 0.0
    assert result.model_name == "StubDetectionModel"


def test_stub_detection_model_is_deterministic():
    model = StubDetectionModel()
    assert model.predict(_feature_vector()) == model.predict(_feature_vector())
