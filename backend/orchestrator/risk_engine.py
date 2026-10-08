"""
Turns a decision_table.Decision into the numeric risk_score (0-100) and
severity the API contract's detection object needs.

Score = verdict base score, scaled by how severe the attack type is,
plus a small bonus for novelty. Suspicious-unknown (model disagreement)
has no trustworthy attack type, so it is scored on how far past the
anomalous threshold the novelty score sits. All constants here are
starting points to revisit with real precision/recall data.
"""

from orchestrator.decision_table import (
    BENIGN, CONFIRMED_ATTACK, KNOWN_ATTACK, LOW_CONFIDENCE, NOVELTY_ANOMALOUS,
    SUSPICIOUS_UNKNOWN, Decision,
)

# Relative severity of each attack type. Unlisted labels use DEFAULT_WEIGHT.
ATTACK_WEIGHTS = {"ddos": 1.0, "exfiltration": 1.0, "port_scan": 0.6}
DEFAULT_WEIGHT = 0.8

VERDICT_BASE = {CONFIRMED_ATTACK: 90.0, KNOWN_ATTACK: 70.0, LOW_CONFIDENCE: 40.0}
NOVELTY_BONUS = 10.0  # max points novelty adds to an attack verdict
BENIGN_MAX = 10.0  # benign flows score 0-10 by novelty
SUSPICIOUS_MIN, SUSPICIOUS_MAX = 60.0, 90.0

# Severity lower bounds (inclusive).
SEVERITY_CUTS = ((85, "critical"), (60, "high"), (30, "medium"), (0, "low"))


def severity_for(score: int) -> str:
    for cut, name in SEVERITY_CUTS:
        if score >= cut:
            return name
    return "low"


def assess(decision: Decision, label: str, novelty_score: float) -> tuple[int, str]:
    """Return (risk_score 0-100, severity) for one flow."""
    novelty_score = min(max(novelty_score, 0.0), 1.0)
    if decision.verdict == BENIGN:
        raw = BENIGN_MAX * novelty_score
    elif decision.verdict == SUSPICIOUS_UNKNOWN:
        excess = max(novelty_score - NOVELTY_ANOMALOUS, 0.0) / (1.0 - NOVELTY_ANOMALOUS)
        raw = SUSPICIOUS_MIN + (SUSPICIOUS_MAX - SUSPICIOUS_MIN) * excess
    else:
        weight = ATTACK_WEIGHTS.get(label, DEFAULT_WEIGHT)
        raw = VERDICT_BASE[decision.verdict] * weight + NOVELTY_BONUS * novelty_score
    score = int(round(min(max(raw, 0.0), 100.0)))
    return score, severity_for(score)
