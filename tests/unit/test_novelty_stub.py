"""StubNoveltyDetector.detect() returns a well-formed NoveltyResult."""

from ovael.agents.novelty.interface import NoveltyDetector
from ovael.agents.novelty.stub import StubNoveltyDetector
from ovael.contracts.schemas import FeatureVector, NoveltyResult


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


def test_stub_novelty_detector_is_a_novelty_detector():
    assert isinstance(StubNoveltyDetector(), NoveltyDetector)


def test_stub_novelty_detector_returns_well_formed_result():
    result = StubNoveltyDetector().detect(_feature_vector())

    assert isinstance(result, NoveltyResult)
    assert result.is_novel is False
    assert result.novelty_score == 0.0
    assert result.model_name == "StubNoveltyDetector"


def test_stub_novelty_detector_is_deterministic():
    detector = StubNoveltyDetector()
    assert detector.detect(_feature_vector()) == detector.detect(_feature_vector())
