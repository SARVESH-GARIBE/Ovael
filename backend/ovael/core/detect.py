"""The shared detect() contract (architecture section 4.4).

    detect(module, features) -> {label, confidence, anomaly_score, risk_level, top_features,
                                 model_version}

Both modules call the same function; the module name picks the feature schema and the saved
models. The result carries a few extra fields (family, risk_score, decision breakdown) that the
dashboard needs, but the six contract fields are always present and always mean the same thing.

Detection is synchronous and CPU-bound. API handlers call it through a thread pool so it never
blocks the event loop, and batches are vectorised: 500 flows cost one predict() call, not 500.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field

from ..config import Settings
from ..ml.registry import ModelRegistry
from ..orchestrator import decide, family_for
from ..orchestrator.taxonomy import LEARNED, UNKNOWN


@dataclass
class DetectionResult:
    module: str
    label: str
    confidence: float
    anomaly_score: float
    risk_level: str
    top_features: list[dict]
    model_version: str
    # extras
    family: str = "unknown"
    family_name: str = ""
    is_attack: bool = False
    is_unusual: bool = False
    risk_score: float = 0.0
    action: str = "none"
    models_agree: bool = True
    needs_review: bool = False
    probabilities: dict[str, float] = field(default_factory=dict)
    breakdown: dict = field(default_factory=dict)
    label_source: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


class DetectionEngine:
    def __init__(self, registry: ModelRegistry, settings: Settings):
        self.registry = registry
        self.settings = settings

    def detect_many(self, module: str, rows: list[dict], explain: bool = False) -> list[DetectionResult]:
        bundle = self.registry.active(module)
        threshold = bundle.threshold or self.settings.anomaly_threshold
        results = []
        low_conf = self.settings.low_confidence_threshold
        for row, pred in zip(rows, bundle.predict(rows)):
            is_unusual = pred.anomaly_score > threshold
            # "Known bad" needs the classifier to actually be sure. An attack label below the
            # confidence threshold is a guess between classes, which usually means the behaviour
            # is new; it is treated as not-recognised so it lands in review, not auto-defense.
            is_attack = pred.label not in bundle.benign_labels and pred.confidence >= low_conf
            guessed = pred.label not in bundle.benign_labels and not is_attack
            # Classifier says normal but the anomaly detector disagrees: a possible unknown attack.
            unrecognised = guessed or (not is_attack and is_unusual)
            family = family_for(module, "unknown" if unrecognised else pred.label)
            if is_attack and family is UNKNOWN[module]:
                family = LEARNED[module]  # confidently recognised, but a class reviewers added
            d = decide(is_attack=is_attack, is_unusual=is_unusual, confidence=pred.confidence,
                       anomaly_score=pred.anomaly_score, family=family,
                       low_confidence_threshold=low_conf)
            results.append(DetectionResult(
                module=module, label=pred.label, confidence=round(pred.confidence, 4),
                anomaly_score=round(pred.anomaly_score, 4), risk_level=d.risk_level.value,
                top_features=bundle.explain(row, pred.label) if explain else [],
                model_version=bundle.version, family=family.id, family_name=family.name,
                is_attack=is_attack, is_unusual=is_unusual, risk_score=d.risk_score,
                action=d.action, models_agree=d.models_agree, needs_review=d.needs_review,
                probabilities=pred.probabilities, breakdown=d.breakdown,
                label_source=bundle.metadata.get("label_source", ""),
            ))
        return results

    def detect(self, module: str, features: dict, explain: bool = False) -> DetectionResult:
        return self.detect_many(module, [features], explain=explain)[0]

    def explain(self, module: str, features: dict, label: str, model_version: str) -> list[dict]:
        bundle = self.registry.active(module)
        if bundle.version != model_version:
            bundle = self.registry.load(module, model_version)
        return bundle.explain(features, label)
