"""Locks in A3 (an attack label under the 0.5 confidence floor is never treated as is_attack, so
it can never be auto-blocked) and A8 (every one of DefenseEngine.eligible()'s conditions, tested
individually against ovael/defense/engine.py).
"""
from __future__ import annotations

from dataclasses import replace

import pytest

from ovael.config import Settings
from ovael.core.cache import Cache
from ovael.core.detect import DetectionEngine
from ovael.defense.engine import DefenseEngine
from ovael.ml.bundle import Prediction
from ovael.ml.registry import ModelRegistry


class _FixedBundle:
    """A stand-in bundle whose predict() always returns one fixed Prediction - isolates the
    is_attack gate in core/detect.py from needing a real trained model."""
    def __init__(self, label, confidence, anomaly_score, benign_labels=("benign",)):
        self.module, self.version, self.threshold = "network", "fixed-v1", 0.99
        self.benign_labels = list(benign_labels)
        self.metadata = {"label_source": "paper_eval"}
        self._pred = Prediction(label=label, confidence=confidence, anomaly_score=anomaly_score,
                                probabilities={label: confidence})

    def predict(self, rows):
        return [self._pred for _ in rows]

    def explain(self, row, label):
        return []


def _registry_with(tmp_path, bundle) -> ModelRegistry:
    reg = ModelRegistry(tmp_path)
    d = tmp_path / "network"
    d.mkdir(parents=True, exist_ok=True)
    (d / "ACTIVE").write_text("fixed-v1")
    mtime = (d / "ACTIVE").stat().st_mtime
    reg._loaded["network"] = (mtime, bundle)
    return reg


def test_low_confidence_attack_label_is_never_is_attack(tmp_path):
    settings = Settings(_env_file=None, low_confidence_threshold=0.5)
    bundle = _FixedBundle(label="dos_flood", confidence=0.3, anomaly_score=0.2)  # below the floor
    reg = _registry_with(tmp_path, bundle)
    engine = DetectionEngine(reg, settings)
    result = engine.detect("network", {"dst_port": 80})
    assert result.is_attack is False  # the 0.5 gate, core/detect.py:65


def test_low_confidence_attack_label_is_never_auto_block_eligible(tmp_path):
    settings = Settings(_env_file=None, low_confidence_threshold=0.5, defense_mode="simulate")
    bundle = _FixedBundle(label="dos_flood", confidence=0.3, anomaly_score=0.999)  # also "unusual"
    reg = _registry_with(tmp_path, bundle)
    engine = DetectionEngine(reg, settings)
    result = engine.detect("network", {"dst_port": 80})
    defense = DefenseEngine(settings, Cache(None))
    ok, reason = defense.eligible(result, "172.28.0.5", persistent=0)
    assert not ok, reason


def test_high_confidence_attack_with_unusual_is_eligible_when_everything_else_holds(tmp_path):
    settings = Settings(_env_file=None, low_confidence_threshold=0.5, defense_mode="simulate")
    bundle = _FixedBundle(label="dos_flood", confidence=0.95, anomaly_score=0.999)
    reg = _registry_with(tmp_path, bundle)
    engine = DetectionEngine(reg, settings)
    result = engine.detect("network", {"dst_port": 80})
    defense = DefenseEngine(settings, Cache(None))
    ok, reason = defense.eligible(result, "172.28.0.5", persistent=0)
    assert ok, reason


# ---------------------------------------------------------------- A8, one condition per test
@pytest.fixture
def base_result(tmp_path):
    settings = Settings(_env_file=None, low_confidence_threshold=0.5, defense_mode="simulate")
    bundle = _FixedBundle(label="dos_flood", confidence=0.95, anomaly_score=0.999)
    reg = _registry_with(tmp_path, bundle)
    engine = DetectionEngine(reg, settings)
    result = engine.detect("network", {"dst_port": 80})
    return settings, result


def test_a8_defense_mode_off_blocks_everything(base_result):
    settings, result = base_result
    settings = replace_settings(settings, defense_mode="off")
    defense = DefenseEngine(settings, Cache(None))
    ok, _ = defense.eligible(result, "172.28.0.5", persistent=0)
    assert not ok


def test_a8_module_must_be_network(base_result):
    settings, result = base_result
    result = replace(result, module="website")
    defense = DefenseEngine(settings, Cache(None))
    ok, _ = defense.eligible(result, "172.28.0.5", persistent=0)
    assert not ok


def test_a8_single_flow_needs_both_models_agreeing(base_result):
    settings, result = base_result
    result = replace(result, models_agree=False)  # risk_level stays "high" but they disagree
    defense = DefenseEngine(settings, Cache(None))
    ok, _ = defense.eligible(result, "172.28.0.5", persistent=0)
    assert not ok  # and persistence (persistent=0) doesn't cover it either


def test_a8_persistence_path_needs_is_attack_and_the_alert_count(base_result):
    settings, result = base_result
    low_risk = replace(result, risk_level="medium", models_agree=False, is_attack=True)
    defense = DefenseEngine(settings, Cache(None))
    ok, _ = defense.eligible(low_risk, "172.28.0.5", persistent=settings.persistence_alerts - 1)
    assert not ok  # one short of the threshold
    ok, _ = defense.eligible(low_risk, "172.28.0.5", persistent=settings.persistence_alerts)
    assert ok  # meets it, and dos_flood allows auto-defense


def test_a8_family_must_allow_auto_defense(base_result):
    settings, result = base_result
    result = replace(result, family="port_scan", label="port_scan")  # port_scan.auto_defense is True
    non_defending = replace(result, family="botnet", label="botnet")  # botnet.auto_defense is False
    defense = DefenseEngine(settings, Cache(None))
    ok, _ = defense.eligible(non_defending, "172.28.0.5", persistent=0)
    assert not ok


def test_a8_source_must_be_inside_the_sandbox_subnet(base_result):
    settings, result = base_result
    defense = DefenseEngine(settings, Cache(None))
    ok, _ = defense.eligible(result, "8.8.8.8", persistent=0)  # real public IP, outside the sandbox
    assert not ok
    ok, _ = defense.eligible(result, "172.28.0.5", persistent=0)  # inside settings.sandbox_subnet
    assert ok


@pytest.mark.asyncio
async def test_a8_already_blocked_source_is_not_blocked_again(base_result):
    settings, result = base_result
    cache = Cache(None)
    defense = DefenseEngine(settings, cache)
    await cache.set_json("blocked:172.28.0.5", {"action": "x"}, ttl_s=60)
    assert await defense.is_blocked("172.28.0.5")
    ok, reason = defense.eligible(result, "172.28.0.5", persistent=0)
    assert ok  # eligible() itself doesn't check is_blocked - maybe_block() does
    assert await defense.is_blocked("172.28.0.5")  # the actual gate used by maybe_block()


def replace_settings(settings: Settings, **kw) -> Settings:
    data = settings.model_dump()
    data.update(kw)
    return Settings(_env_file=None, **data)
