"""Decision table and risk score.

Both modules use the same four rows (architecture section 4.3):

    Random Forest   Isolation Forest   risk_level
    known bad       unusual            high        (auto-defense allowed)
    known bad       normal             medium      (alert only)
    normal          unusual            suspicious  (alert + hard example for review)
    normal          normal             low         (no action)

The risk score places a result inside its level's band, so levels never overlap and the number
always agrees with the level:

    low        0-24   scaled by anomaly_score
    suspicious 25-49  scaled by anomaly_score
    medium     50-74  scaled by severity_weight x confidence
    high       75-100 scaled by severity_weight x confidence
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from .taxonomy import AttackFamily


class RiskLevel(StrEnum):
    LOW = "low"
    SUSPICIOUS = "suspicious"
    MEDIUM = "medium"
    HIGH = "high"


BANDS: dict[RiskLevel, tuple[int, int]] = {
    RiskLevel.LOW: (0, 24),
    RiskLevel.SUSPICIOUS: (25, 49),
    RiskLevel.MEDIUM: (50, 74),
    RiskLevel.HIGH: (75, 100),
}

ACTIONS: dict[RiskLevel, str] = {
    RiskLevel.HIGH: "alert_and_defend",
    RiskLevel.MEDIUM: "alert",
    RiskLevel.SUSPICIOUS: "alert_and_review",
    RiskLevel.LOW: "none",
}


@dataclass(frozen=True)
class Decision:
    risk_level: RiskLevel
    risk_score: float
    action: str
    models_agree: bool  # both models flag it, or both say normal
    needs_review: bool
    breakdown: dict


def decide(*, is_attack: bool, is_unusual: bool, confidence: float, anomaly_score: float,
           family: AttackFamily, low_confidence_threshold: float = 0.5) -> Decision:
    if is_attack and is_unusual:
        level = RiskLevel.HIGH
    elif is_attack:
        level = RiskLevel.MEDIUM
    elif is_unusual:
        level = RiskLevel.SUSPICIOUS
    else:
        level = RiskLevel.LOW

    lo, hi = BANDS[level]
    if is_attack:
        position = family.severity_weight * confidence
    else:
        position = anomaly_score
    position = min(max(position, 0.0), 1.0)
    score = round(lo + (hi - lo) * position, 1)

    disagreement = is_attack != is_unusual
    uncertain = confidence < low_confidence_threshold
    return Decision(
        risk_level=level,
        risk_score=score,
        action=ACTIONS[level],
        models_agree=not disagreement,
        # The flagged disagreement (normal but unusual) always goes to review; so does any
        # verdict the classifier itself is unsure about.
        needs_review=level == RiskLevel.SUSPICIOUS or uncertain,
        breakdown={
            "band": [lo, hi],
            "position": round(position, 4),
            "severity_weight": family.severity_weight,
            "confidence": round(confidence, 4),
            "anomaly_score": round(anomaly_score, 4),
            "classifier_says": "attack" if is_attack else "normal",
            "anomaly_detector_says": "unusual" if is_unusual else "normal",
        },
    )
