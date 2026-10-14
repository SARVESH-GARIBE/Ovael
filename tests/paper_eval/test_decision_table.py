"""Locks in A1 (band placement) and A6 (review routing) against orchestrator/decision.py."""
from __future__ import annotations

import pytest

from ovael.orchestrator.decision import BANDS, RiskLevel, decide
from ovael.orchestrator.taxonomy import family_for


@pytest.mark.parametrize("is_attack,is_unusual,expected", [
    (True, True, RiskLevel.HIGH),
    (True, False, RiskLevel.MEDIUM),
    (False, True, RiskLevel.SUSPICIOUS),
    (False, False, RiskLevel.LOW),
])
def test_all_four_combinations_return_the_correct_risk_level_and_band(is_attack, is_unusual, expected):
    fam = family_for("network", "dos_flood" if is_attack else "benign")
    d = decide(is_attack=is_attack, is_unusual=is_unusual, confidence=0.9, anomaly_score=0.5, family=fam)
    assert d.risk_level == expected
    lo, hi = BANDS[expected]
    assert lo <= d.risk_score <= hi


@pytest.mark.parametrize("is_attack,is_unusual", [(True, True), (True, False), (False, True), (False, False)])
@pytest.mark.parametrize("confidence", [0.0, 0.1, 0.5, 0.9, 1.0])
@pytest.mark.parametrize("anomaly_score", [0.0, 0.3, 0.7, 1.0])
def test_score_always_lies_inside_its_band(is_attack, is_unusual, confidence, anomaly_score):
    fam = family_for("network", "dos_flood" if is_attack else "benign")
    d = decide(is_attack=is_attack, is_unusual=is_unusual, confidence=confidence,
               anomaly_score=anomaly_score, family=fam)
    lo, hi = BANDS[d.risk_level]
    assert lo <= d.risk_score <= hi


def test_suspicious_row_needs_review():
    d = decide(is_attack=False, is_unusual=True, confidence=0.9, anomaly_score=0.99,
               family=family_for("network", "benign"))
    assert d.risk_level == RiskLevel.SUSPICIOUS
    assert d.needs_review


def test_low_confidence_needs_review_even_when_level_is_low():
    d = decide(is_attack=False, is_unusual=False, confidence=0.3, anomaly_score=0.1,
               family=family_for("network", "benign"), low_confidence_threshold=0.5)
    assert d.risk_level == RiskLevel.LOW
    assert d.needs_review  # confidence < floor, regardless of level


def test_confident_normal_does_not_need_review():
    d = decide(is_attack=False, is_unusual=False, confidence=0.95, anomaly_score=0.1,
               family=family_for("network", "benign"))
    assert not d.needs_review
