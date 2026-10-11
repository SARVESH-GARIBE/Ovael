"""Retrain -> evaluate on the fixed held-out set -> promote only if better.

Runs in a background worker (Celery when configured, otherwise a thread), never on the live
detection path. A failed or worse retrain leaves the active model untouched.
"""

from __future__ import annotations

import logging

import pandas as pd

from ..config import Settings
from ..ml import datasets
from ..ml.registry import ModelRegistry
from ..ml.train import evaluate, split, train_bundle

log = logging.getLogger(__name__)
MAX_FALSE_ALARM_REGRESSION = 0.02


def retrain(module: str, settings: Settings, registry: ModelRegistry,
            reviewed: pd.DataFrame | None = None, *, always_promote: bool = False) -> dict:
    base, label_source = datasets.load_base(module, settings)
    train_df, holdout = split(base)
    if reviewed is not None and len(reviewed):
        train_df = pd.concat([train_df, reviewed], ignore_index=True)
        label_source += f"+reviewed({len(reviewed)})"

    version = registry.next_version(module)
    candidate = train_bundle(module, train_df, holdout, version=version,
                             threshold=settings.anomaly_threshold, label_source=label_source,
                             novel=datasets.novel_probe(module),
                             extra_meta={"reviewed_samples": 0 if reviewed is None else int(len(reviewed))})
    registry.save(candidate)
    new = candidate.metadata["metrics"]

    current_version = registry.active_version(module)
    old = None
    if current_version and not always_promote:
        try:
            old = evaluate(registry.load(module, current_version), holdout, datasets.novel_probe(module))
        except Exception as exc:  # e.g. the old model was trained on a different feature schema
            log.warning("could not re-evaluate %s on the current held-out set: %s", current_version, exc)

    if old is None:
        promoted, reason = True, "no comparable active model"
    elif new["macro_f1"] < old["macro_f1"]:
        promoted, reason = False, f"macro F1 {new['macro_f1']} < active {old['macro_f1']}"
    elif ((new.get("anomaly_false_alarm_rate") or 0) - (old.get("anomaly_false_alarm_rate") or 0)
          > MAX_FALSE_ALARM_REGRESSION):
        promoted, reason = False, "anomaly false-alarm rate regressed"
    else:
        promoted, reason = True, f"macro F1 {new['macro_f1']} >= active {old['macro_f1']}"

    if promoted:
        registry.promote(module, version)
    log.info("retrain %s: promoted=%s (%s)", version, promoted, reason)
    return {"module": module, "version": version, "promoted": promoted, "reason": reason,
            "metrics": new, "previous_version": current_version, "previous_metrics": old}
