"""Locks in A2 against the real branching in learning_loop/retrain.py: rejects a candidate that
lowers macro F1, and rejects one whose false-alarm rate regresses by more than the 0.02 tolerance,
even when macro F1 is unchanged or better. Monkeypatches train_bundle/evaluate to return
controlled metrics, rather than depending on a real model actually training worse - this tests the
promotion branching itself, not RandomForest behaviour.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd
import pytest

from ovael.config import Settings
from ovael.learning_loop import retrain as retrain_mod
from ovael.ml import datasets
from ovael.ml.registry import ModelRegistry


@dataclass
class _FakeBundle:
    module: str
    version: str
    metadata: dict = field(default_factory=dict)

    def summary(self) -> dict:
        return {"module": self.module, "version": self.version, **self.metadata}


@pytest.fixture
def rig(tmp_path, monkeypatch):
    monkeypatch.setattr(datasets, "load_base", lambda m, s: (pd.DataFrame({"label": ["benign"] * 10}), "fake"))
    settings = Settings(_env_file=None, model_dir=tmp_path, env="test",
                       network_dataset=tmp_path / "x.csv", network_unknown_dataset=tmp_path / "y.csv")
    registry = ModelRegistry(tmp_path)
    return settings, registry, monkeypatch


def _install(monkeypatch, metrics_by_version: dict[str, dict]):
    def fake_train_bundle(module, train_df, holdout, *, version, threshold, label_source, novel=None, extra_meta=None):
        b = _FakeBundle(module=module, version=version)
        b.metadata["metrics"] = metrics_by_version[version]
        return b

    def fake_evaluate(bundle, holdout, novel=None):
        return metrics_by_version[bundle.version]

    monkeypatch.setattr(retrain_mod, "train_bundle", fake_train_bundle)
    monkeypatch.setattr(retrain_mod, "evaluate", fake_evaluate)


def test_first_model_is_promoted_with_no_comparable_active_model(rig):
    settings, registry, monkeypatch = rig
    _install(monkeypatch, {"network-v1": {"macro_f1": 0.5, "anomaly_false_alarm_rate": 0.05}})
    out = retrain_mod.retrain("network", settings, registry)
    assert out["promoted"] is True
    assert out["reason"] == "no comparable active model"


def test_rejects_a_candidate_that_lowers_macro_f1(rig):
    settings, registry, monkeypatch = rig
    _install(monkeypatch, {"network-v1": {"macro_f1": 0.90, "anomaly_false_alarm_rate": 0.05}})
    retrain_mod.retrain("network", settings, registry)

    _install(monkeypatch, {
        "network-v1": {"macro_f1": 0.90, "anomaly_false_alarm_rate": 0.05},  # re-eval of the active model
        "network-v2": {"macro_f1": 0.85, "anomaly_false_alarm_rate": 0.05},  # candidate: worse F1, same FAR
    })
    out = retrain_mod.retrain("network", settings, registry)
    assert out["promoted"] is False
    assert "macro F1" in out["reason"]
    assert registry.active_version("network") == "network-v1"  # unchanged


def test_rejects_a_candidate_whose_false_alarm_rate_regresses_past_tolerance(rig):
    settings, registry, monkeypatch = rig
    _install(monkeypatch, {"network-v1": {"macro_f1": 0.90, "anomaly_false_alarm_rate": 0.05}})
    retrain_mod.retrain("network", settings, registry)

    _install(monkeypatch, {
        "network-v1": {"macro_f1": 0.90, "anomaly_false_alarm_rate": 0.05},
        # same-or-better F1, but FAR regresses by 0.03 > MAX_FALSE_ALARM_REGRESSION (0.02)
        "network-v2": {"macro_f1": 0.92, "anomaly_false_alarm_rate": 0.08},
    })
    out = retrain_mod.retrain("network", settings, registry)
    assert out["promoted"] is False
    assert "false-alarm" in out["reason"]
    assert registry.active_version("network") == "network-v1"


def test_accepts_a_candidate_within_the_false_alarm_tolerance(rig):
    settings, registry, monkeypatch = rig
    _install(monkeypatch, {"network-v1": {"macro_f1": 0.90, "anomaly_false_alarm_rate": 0.05}})
    retrain_mod.retrain("network", settings, registry)

    _install(monkeypatch, {
        "network-v1": {"macro_f1": 0.90, "anomaly_false_alarm_rate": 0.05},
        # Unambiguously under the 0.02 tolerance (0.065-0.05 = 0.015) - see the next test for why
        # a value exactly "0.02" by decimal arithmetic is not used here.
        "network-v2": {"macro_f1": 0.90, "anomaly_false_alarm_rate": 0.065},
    })
    out = retrain_mod.retrain("network", settings, registry)
    assert out["promoted"] is True
    assert registry.active_version("network") == "network-v2"


def test_finding_exact_tolerance_boundary_is_float_precision_sensitive(rig):
    """FINDING, not a bug fix target (rule: report a failing/surprising case, don't patch
    source). retrain.py compares `(new_far - old_far) > MAX_FALSE_ALARM_REGRESSION` directly as
    floats. 0.07 - 0.05 in IEEE-754 double precision is 0.020000000000000004, which is strictly
    greater than the 0.02 literal - so a candidate whose false-alarm rate "regressed by exactly
    0.02" in decimal terms is REJECTED, not accepted, depending on which two float values produced
    that 0.02. This is demonstrated directly below; it is not asserted as a defect, only recorded,
    per the task rule to report rather than fix."""
    settings, registry, monkeypatch = rig
    _install(monkeypatch, {"network-v1": {"macro_f1": 0.90, "anomaly_false_alarm_rate": 0.05}})
    retrain_mod.retrain("network", settings, registry)

    _install(monkeypatch, {
        "network-v1": {"macro_f1": 0.90, "anomaly_false_alarm_rate": 0.05},
        "network-v2": {"macro_f1": 0.90, "anomaly_false_alarm_rate": 0.07},  # "exactly" +0.02 in decimal
    })
    out = retrain_mod.retrain("network", settings, registry)
    raw_diff = 0.07 - 0.05
    assert raw_diff > 0.02  # the float artifact that drives the observed outcome
    assert out["promoted"] is False  # observed behaviour, recorded as a finding, not "corrected" here
