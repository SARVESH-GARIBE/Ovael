"""
PLACEHOLDER — Risk Analysis.

Always returns the same fixed, obviously-fake RiskAssessment, regardless
of what's in the OrchestrationContext it's given. This is NOT a real
risk-scoring formula: it does not read risk signal from the detection
result, the novelty result, or anything else. A real formula (how
confidence, novelty, and attack-type severity should combine into a
risk score) is explicit future work.
"""

from __future__ import annotations

from ovael.contracts.schemas import OrchestrationContext, RiskAssessment

PLACEHOLDER_RISK_SCORE = 0.0
PLACEHOLDER_SEVERITY = "unknown-placeholder"
PLACEHOLDER_STATUS = "unknown-placeholder"


def assess_risk(context: OrchestrationContext) -> RiskAssessment:
    """Fixed placeholder: does not compute a real risk score."""
    return RiskAssessment(
        risk_score=PLACEHOLDER_RISK_SCORE,
        severity=PLACEHOLDER_SEVERITY,
        status=PLACEHOLDER_STATUS,
        rationale="placeholder - risk analysis is not yet implemented",
        metadata={"stub": True},
    )
