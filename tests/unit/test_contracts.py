"""Each contract in ovael.contracts.schemas can be constructed with
valid field values."""

from ovael.contracts.schemas import (
    DetectionResult,
    FeatureVector,
    FinalAssessment,
    NoveltyResult,
    OrchestrationContext,
    RawTraffic,
    RiskAssessment,
)


def _raw_traffic() -> RawTraffic:
    return RawTraffic(
        source_ip="10.0.0.5",
        destination_ip="10.0.0.9",
        source_port=51234,
        destination_port=80,
        protocol="TCP",
        payload_size=512,
        timestamp=1700000000.0,
    )


def _feature_vector() -> FeatureVector:
    return FeatureVector(
        source_ip="10.0.0.5",
        destination_ip="10.0.0.9",
        source_port=51234,
        destination_port=80,
        protocol="TCP",
        payload_size=512,
        timestamp=1700000000.0,
        features={"placeholder_feature": 0.0},
    )


def _detection_result() -> DetectionResult:
    return DetectionResult(
        predicted_class="unknown-placeholder",
        confidence=0.0,
        model_name="StubDetectionModel",
    )


def _novelty_result() -> NoveltyResult:
    return NoveltyResult(
        is_novel=False,
        novelty_score=0.0,
        model_name="StubNoveltyDetector",
    )


def test_raw_traffic_constructs():
    rt = _raw_traffic()
    assert rt.source_ip == "10.0.0.5" and rt.protocol == "TCP"


def test_feature_vector_constructs():
    fv = _feature_vector()
    assert fv.features == {"placeholder_feature": 0.0}


def test_detection_result_constructs():
    dr = _detection_result()
    assert dr.predicted_class == "unknown-placeholder" and dr.confidence == 0.0


def test_novelty_result_constructs():
    nr = _novelty_result()
    assert nr.is_novel is False and nr.novelty_score == 0.0


def test_orchestration_context_constructs():
    ctx = OrchestrationContext(
        feature_vector=_feature_vector(),
        detection_result=_detection_result(),
        novelty_result=_novelty_result(),
    )
    assert ctx.detection_result.model_name == "StubDetectionModel"


def test_risk_assessment_constructs():
    ra = RiskAssessment(
        risk_score=0.0,
        severity="unknown-placeholder",
        status="unknown-placeholder",
        rationale="placeholder",
    )
    assert ra.severity == "unknown-placeholder"
    assert ra.status == "unknown-placeholder"


def test_final_assessment_constructs():
    fv = _feature_vector()
    dr = _detection_result()
    nr = _novelty_result()
    ctx = OrchestrationContext(feature_vector=fv, detection_result=dr, novelty_result=nr)
    ra = RiskAssessment(
        risk_score=0.0,
        severity="unknown-placeholder",
        status="unknown-placeholder",
        rationale="placeholder",
    )
    fa = FinalAssessment(
        raw_traffic=_raw_traffic(),
        feature_vector=fv,
        detection_result=dr,
        novelty_result=nr,
        orchestration_context=ctx,
        risk_assessment=ra,
    )
    assert fa.risk_assessment.severity == "unknown-placeholder"
    assert fa.risk_assessment.status == "unknown-placeholder"


def test_contracts_are_frozen():
    rt = _raw_traffic()
    try:
        rt.source_ip = "changed"  # type: ignore[misc]
        assert False, "RawTraffic should be immutable"
    except AttributeError:
        pass
