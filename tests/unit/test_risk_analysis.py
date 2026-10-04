"""Risk Analysis produces a RiskAssessment from an OrchestrationContext."""

from ovael.agents.detection.stub import StubDetectionModel
from ovael.agents.novelty.stub import StubNoveltyDetector
from ovael.contracts.schemas import FeatureVector, RiskAssessment
from ovael.orchestration.orchestrator import orchestrate
from ovael.risk.risk_analysis import assess_risk


def _context():
    features = FeatureVector(
        source_ip="10.0.0.5",
        destination_ip="10.0.0.9",
        source_port=51234,
        destination_port=80,
        protocol="TCP",
        payload_size=512,
        timestamp=1700000000.0,
    )
    detection_result = StubDetectionModel().predict(features)
    novelty_result = StubNoveltyDetector().detect(features)
    return orchestrate(features, detection_result, novelty_result)


def test_assess_risk_returns_well_formed_risk_assessment():
    assessment = assess_risk(_context())

    assert isinstance(assessment, RiskAssessment)
    assert assessment.risk_score == 0.0
    assert assessment.severity == "unknown-placeholder"
    assert assessment.status == "unknown-placeholder"
    assert assessment.rationale


def test_assess_risk_is_a_fixed_placeholder_not_a_real_formula():
    # Deliberately NOT a function of the context's content: same
    # placeholder output regardless of what's inside it.
    assert assess_risk(_context()) == assess_risk(_context())
