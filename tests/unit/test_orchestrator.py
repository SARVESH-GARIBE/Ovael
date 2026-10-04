"""Orchestrator combines a DetectionResult + NoveltyResult into an
OrchestrationContext without altering either input."""

from ovael.agents.detection.stub import StubDetectionModel
from ovael.agents.novelty.stub import StubNoveltyDetector
from ovael.contracts.schemas import FeatureVector, OrchestrationContext
from ovael.orchestration.orchestrator import orchestrate


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


def test_orchestrate_bundles_results_unaltered():
    features = _feature_vector()
    detection_result = StubDetectionModel().predict(features)
    novelty_result = StubNoveltyDetector().detect(features)

    context = orchestrate(features, detection_result, novelty_result)

    assert isinstance(context, OrchestrationContext)
    # Equality (dataclass value equality) confirms nothing was mutated;
    # identity confirms the orchestrator passed the same objects through
    # rather than rebuilding copies.
    assert context.feature_vector is features
    assert context.detection_result is detection_result
    assert context.novelty_result is novelty_result
    assert context.detection_result == detection_result
    assert context.novelty_result == novelty_result
