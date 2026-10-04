"""
Pipeline — wires every Stage 1 component into one callable, end-to-end
entry point:

    RawTraffic
        -> Feature Extraction (stub)
        -> FeatureVector
        -> Detection Agent (stub) + Novelty Agent (stub)
        -> DetectionResult + NoveltyResult
        -> Orchestrator
        -> OrchestrationContext
        -> Risk Analysis (placeholder)
        -> RiskAssessment
        -> FinalAssessment

This module is deliberately the ONLY place in ovael/ that imports from
every other component package. Validation and Learning are NOT wired in
here — Stage 1 does not call either.
"""

from __future__ import annotations

from ovael.agents.detection.interface import DetectionModel
from ovael.agents.detection.stub import StubDetectionModel
from ovael.agents.novelty.interface import NoveltyDetector
from ovael.agents.novelty.stub import StubNoveltyDetector
from ovael.contracts.schemas import FinalAssessment, RawTraffic
from ovael.ingestion.feature_extraction import extract_features
from ovael.orchestration.orchestrator import orchestrate
from ovael.risk.risk_analysis import assess_risk


def run(
    raw_traffic: RawTraffic,
    detection_model: DetectionModel | None = None,
    novelty_detector: NoveltyDetector | None = None,
) -> FinalAssessment:
    """Run one RawTraffic sample through the full Stage 1 pipeline.

    `detection_model` / `novelty_detector` default to Stage 1's stub
    implementations; they are accepted as parameters so a later stage
    can swap in real implementations against this same interface
    without changing the wiring below.
    """
    detection_model = detection_model or StubDetectionModel()
    novelty_detector = novelty_detector or StubNoveltyDetector()

    feature_vector = extract_features(raw_traffic)
    detection_result = detection_model.predict(feature_vector)
    novelty_result = novelty_detector.detect(feature_vector)
    context = orchestrate(feature_vector, detection_result, novelty_result)
    risk_assessment = assess_risk(context)

    return FinalAssessment(
        raw_traffic=raw_traffic,
        feature_vector=feature_vector,
        detection_result=detection_result,
        novelty_result=novelty_result,
        orchestration_context=context,
        risk_assessment=risk_assessment,
        metadata={"stage": "stage1-skeleton"},
    )
