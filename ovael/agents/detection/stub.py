"""
STUB — Detection Agent.

Deterministic dummy output only. No real classifier (no Random Forest,
no neural net, nothing) is selected or implemented here — that choice
is explicit future work. The output is intentionally and visibly fake
so nothing downstream can mistake it for a real prediction.
"""

from __future__ import annotations

from ovael.agents.detection.interface import DetectionModel
from ovael.contracts.schemas import DetectionResult, FeatureVector

PLACEHOLDER_CLASS = "unknown-placeholder"
PLACEHOLDER_CONFIDENCE = 0.0


class StubDetectionModel(DetectionModel):
    """Always returns the same obviously-fake DetectionResult,
    regardless of input."""

    def predict(self, features: FeatureVector) -> DetectionResult:
        return DetectionResult(
            predicted_class=PLACEHOLDER_CLASS,
            confidence=PLACEHOLDER_CONFIDENCE,
            model_name="StubDetectionModel",
            metadata={"stub": True},
        )
