import itertools

import pytest

from orchestrator.decision_table import (
    BENIGN, CONFIRMED_ATTACK, KNOWN_ATTACK, LOW_CONFIDENCE, SUSPICIOUS_UNKNOWN,
    _TABLE, decide, confidence_bucket, novelty_bucket,
)


def test_table_covers_every_bucket_combination():
    for key in itertools.product((True, False), ("high", "medium", "low"),
                                 ("normal", "elevated", "anomalous")):
        assert key in _TABLE


@pytest.mark.parametrize("conf,expected", [(0.95, "high"), (0.80, "high"), (0.79, "medium"),
                                           (0.50, "medium"), (0.49, "low")])
def test_confidence_buckets(conf, expected):
    assert confidence_bucket(conf) == expected


@pytest.mark.parametrize("score,expected", [(0.99, "anomalous"), (0.95, "anomalous"),
                                            (0.92, "elevated"), (0.90, "elevated"), (0.5, "normal")])
def test_novelty_buckets(score, expected):
    assert novelty_bucket(score) == expected


def test_disagreement_is_hard_example():
    d = decide("normal", 0.99, 0.99)
    assert d.verdict == SUSPICIOUS_UNKNOWN and d.is_hard_example


def test_both_agree_normal():
    d = decide("normal", 0.99, 0.3)
    assert d.verdict == BENIGN and not d.is_hard_example


def test_known_attack_novelty_quiet():
    assert decide("ddos", 0.95, 0.3).verdict == KNOWN_ATTACK


def test_attack_confirmed_by_novelty():
    assert decide("ddos", 0.95, 0.99).verdict == CONFIRMED_ATTACK


def test_weak_attack_call_no_corroboration():
    assert decide("ddos", 0.6, 0.2).verdict == LOW_CONFIDENCE


def test_only_anomalous_novelty_creates_hard_examples():
    for (is_attack, conf, nov), (_, hard, _) in _TABLE.items():
        if hard:
            assert nov == "anomalous"
