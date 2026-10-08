"""
Rule-based combiner for the two parallel model outputs.

Both models always run; this module only sees their two results. It is
a lookup table keyed on (multiclass bucket, novelty bucket), not a
weighted average: the inputs answer different questions (classifier
confidence vs. percentile-of-normal), and averaging them would erase
the disagreement case, which is the point of running both.
"""

from dataclasses import dataclass

from feature_extraction.schema import NORMAL_LABEL

# Multiclass confidence buckets (lower bound inclusive).
CONF_HIGH = 0.80
CONF_MEDIUM = 0.50

# Novelty percentile buckets. 0.95 matches the threshold ml/novelty/model.py
# already evaluates detection/false-positive rate at.
NOVELTY_ANOMALOUS = 0.95
NOVELTY_ELEVATED = 0.90

# Verdicts
BENIGN = "benign"
KNOWN_ATTACK = "known_attack"
CONFIRMED_ATTACK = "confirmed_attack"
SUSPICIOUS_UNKNOWN = "suspicious_unknown"  # models disagree -> hard example
LOW_CONFIDENCE = "low_confidence"


@dataclass(frozen=True)
class Decision:
    verdict: str
    is_hard_example: bool
    reason: str


def confidence_bucket(confidence: float) -> str:
    if confidence >= CONF_HIGH:
        return "high"
    if confidence >= CONF_MEDIUM:
        return "medium"
    return "low"


def novelty_bucket(score: float) -> str:
    if score >= NOVELTY_ANOMALOUS:
        return "anomalous"
    if score >= NOVELTY_ELEVATED:
        return "elevated"
    return "normal"


# (is_attack, confidence bucket, novelty bucket) -> (verdict, hard_example, reason)
_TABLE: dict[tuple[bool, str, str], tuple[str, bool, str]] = {}


def _row(is_attack, conf, novelty, verdict, hard, reason):
    _TABLE[(is_attack, conf, novelty)] = (verdict, hard, reason)


for _n in ("normal", "elevated", "anomalous"):
    # Attack label, high confidence
    _row(True, "high", _n, CONFIRMED_ATTACK if _n == "anomalous" else KNOWN_ATTACK, False,
         "classifier confident of a known attack" + (", novelty agrees" if _n == "anomalous" else ""))
    # Attack label, medium confidence
    _row(True, "medium", _n, CONFIRMED_ATTACK if _n != "normal" else LOW_CONFIDENCE, False,
         "attack label with moderate confidence" + ("; novelty corroborates" if _n != "normal" else "; novelty sees nothing unusual"))
    # Attack label, low confidence
    _row(True, "low", _n, SUSPICIOUS_UNKNOWN if _n == "anomalous" else LOW_CONFIDENCE,
         _n == "anomalous",
         "classifier unsure" + ("; novelty flags it as unlike normal" if _n == "anomalous" else ""))
    # Normal label, medium/low confidence
    for _c in ("medium", "low"):
        _row(False, _c, _n, BENIGN if _n == "normal" else SUSPICIOUS_UNKNOWN,
             _n == "anomalous",
             "weak 'normal' call" + ("" if _n == "normal" else "; novelty raises doubt"))

# Normal label, high confidence
_row(False, "high", "normal", BENIGN, False, "both models agree: normal")
_row(False, "high", "elevated", BENIGN, False, "classifier confident normal; novelty only mildly elevated")
_row(False, "high", "anomalous", SUSPICIOUS_UNKNOWN, True,
     "DISAGREEMENT: classifier confidently says normal, novelty says anomalous")


def decide(label: str, confidence: float, novelty_score: float) -> Decision:
    """Combine one flow's multiclass (label, confidence) and novelty
    score into a Decision."""
    key = (label != NORMAL_LABEL, confidence_bucket(confidence), novelty_bucket(novelty_score))
    verdict, hard, reason = _TABLE[key]
    return Decision(verdict=verdict, is_hard_example=hard, reason=reason)
