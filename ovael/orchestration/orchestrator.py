"""
Orchestrator — Stage 1.

Combines a DetectionResult and a NoveltyResult (plus the FeatureVector
they were both computed from) into a single OrchestrationContext.

This is bundling only. It deliberately does NOT implement any
agreement/disagreement handling, weighting, or decision logic between
the two results — how the Detection Agent and Novelty Agent outputs
should actually be combined is an open research decision, and is not
invented here. Neither input is read for its content or altered in any
way; they are passed through unchanged.
"""

from __future__ import annotations

from ovael.contracts.schemas import (
    DetectionResult,
    FeatureVector,
    NoveltyResult,
    OrchestrationContext,
)


def orchestrate(
    feature_vector: FeatureVector,
    detection_result: DetectionResult,
    novelty_result: NoveltyResult,
) -> OrchestrationContext:
    """Bundle the two parallel agent outputs together. No combination
    logic beyond bundling."""
    return OrchestrationContext(
        feature_vector=feature_vector,
        detection_result=detection_result,
        novelty_result=novelty_result,
        metadata={"stub": True},
    )
