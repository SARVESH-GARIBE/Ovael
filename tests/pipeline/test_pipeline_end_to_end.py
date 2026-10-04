"""The full pipeline (pipeline.run(...)) executes end-to-end on a sample
RawTraffic and returns a well-formed FinalAssessment."""

from ovael.contracts.schemas import (
    DetectionResult,
    FeatureVector,
    FinalAssessment,
    NoveltyResult,
    OrchestrationContext,
    RawTraffic,
    RiskAssessment,
)
from ovael.pipeline import pipeline


def _sample_raw_traffic() -> RawTraffic:
    return RawTraffic(
        source_ip="192.168.1.10",
        destination_ip="192.168.1.20",
        source_port=51234,
        destination_port=443,
        protocol="TCP",
        payload_size=1500,
        timestamp=1700000000.0,
    )


def test_pipeline_runs_end_to_end_without_error():
    result = pipeline.run(_sample_raw_traffic())
    assert isinstance(result, FinalAssessment)


def test_pipeline_result_contains_every_stage_output():
    raw = _sample_raw_traffic()
    result = pipeline.run(raw)

    assert result.raw_traffic == raw
    assert isinstance(result.feature_vector, FeatureVector)
    assert isinstance(result.detection_result, DetectionResult)
    assert isinstance(result.novelty_result, NoveltyResult)
    assert isinstance(result.orchestration_context, OrchestrationContext)
    assert isinstance(result.risk_assessment, RiskAssessment)


def test_pipeline_result_is_internally_consistent():
    result = pipeline.run(_sample_raw_traffic())

    # The same objects that flowed into the orchestrator are the ones
    # inside its context and inside the final assessment.
    assert result.orchestration_context.feature_vector == result.feature_vector
    assert result.orchestration_context.detection_result == result.detection_result
    assert result.orchestration_context.novelty_result == result.novelty_result


def test_pipeline_output_is_visibly_stubbed():
    result = pipeline.run(_sample_raw_traffic())

    assert result.detection_result.predicted_class == "unknown-placeholder"
    assert result.detection_result.confidence == 0.0
    assert result.novelty_result.novelty_score == 0.0
    assert result.risk_assessment.severity == "unknown-placeholder"
    assert result.risk_assessment.status == "unknown-placeholder"
