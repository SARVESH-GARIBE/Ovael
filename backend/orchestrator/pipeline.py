"""
Synchronous detection: one feature vector -> both models -> decision
table -> risk engine. Both models always run; neither output gates the
other.
"""

from dataclasses import dataclass

from feature_extraction.schema import FeatureVector, validate
from ml.backend_models.multiclass.model import MulticlassModel
from ml.backend_models.novelty.model import NoveltyModel
from orchestrator.decision_table import Decision, decide
from orchestrator.risk_engine import assess


@dataclass(frozen=True)
class DetectionResult:
    label: str
    confidence: float
    novelty_score: float
    decision: Decision
    risk_score: int
    severity: str


def detect(feature_vector: FeatureVector, multiclass: MulticlassModel, novelty: NoveltyModel) -> DetectionResult:
    validate(feature_vector)
    label, confidence = multiclass.predict_one(feature_vector)
    novelty_score = novelty.predict_one(feature_vector)
    label = str(label)
    decision = decide(label, confidence, novelty_score)
    risk_score, severity = assess(decision, label, novelty_score)
    return DetectionResult(label, confidence, novelty_score, decision, risk_score, severity)
