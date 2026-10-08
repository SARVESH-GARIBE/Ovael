import pytest

from orchestrator.decision_table import decide
from orchestrator.risk_engine import assess, severity_for


@pytest.mark.parametrize("score,sev", [(0, "low"), (29, "low"), (30, "medium"), (59, "medium"),
                                       (60, "high"), (84, "high"), (85, "critical"), (100, "critical")])
def test_severity_boundaries(score, sev):
    assert severity_for(score) == sev


def _assess(label, conf, nov):
    return assess(decide(label, conf, nov), label, nov)


def test_low_benign():
    score, sev = _assess("normal", 0.99, 0.2)
    assert sev == "low" and score <= 10


def test_medium_known_port_scan():
    score, sev = _assess("port_scan", 0.9, 0.3)
    assert sev == "medium" and 30 <= score < 60


def test_high_known_ddos():
    score, sev = _assess("ddos", 0.9, 0.3)
    assert sev == "high"


def test_critical_confirmed_ddos():
    score, sev = _assess("ddos", 0.95, 0.99)
    assert sev == "critical" and score == 100


def test_port_scan_less_severe_than_ddos_and_exfiltration():
    args = (0.9, 0.99)
    assert _assess("port_scan", *args)[0] < _assess("ddos", *args)[0]
    assert _assess("exfiltration", *args)[0] == _assess("ddos", *args)[0]


def test_disagreement_scales_with_novelty_and_is_high():
    low, sev_low = _assess("normal", 0.99, 0.95)
    top, _ = _assess("normal", 0.99, 1.0)
    assert sev_low == "high" and low == 60 and top == 90 and top > low


def test_score_always_in_range():
    for label in ("normal", "ddos", "port_scan", "exfiltration", "other"):
        for conf in (0.1, 0.6, 0.95):
            for nov in (0.0, 0.5, 0.92, 1.0):
                score, _ = _assess(label, conf, nov)
                assert 0 <= score <= 100
