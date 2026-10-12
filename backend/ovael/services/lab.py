"""Research lab: the learning-loop experiment and the evasion sweep.

Learning-loop experiment ("does it actually learn?"):
  1. probe  - show the active model a behaviour it was never trained on (exfiltration-like flows);
              store the detections and queue every flow for review, tagged with the probe id
  2. teach  - an analyst names the behaviour; every flow of that probe is confirmed with that label
              and the model is retrained (promoted only if it is not worse on the held-out set)
  3. probe again with fresh flows of the same behaviour, and compare the two probes

Probes only score and store. They never trigger auto-defense and are not pushed as live alerts, so
an experiment cannot block anything or flood the dashboard.
"""

from __future__ import annotations

import asyncio
import uuid
from collections import Counter

import numpy as np
from sqlalchemy import select

from ..core.context import AppContext
from ..db.models import Detection, ReviewItem, utcnow
from ..ml import adversarial
from ..ml.flow_source import get_flow_source
from . import learning

# The behaviour no training class covers: real CIC-IDS2017 botnet flows held out of training when
# the real dataset is imported, otherwise the synthetic exfiltration-like class.
PROBE_BEHAVIOUR = "novel"


def _summary(results, probe_id: str, n: int, source: str = "") -> dict:
    levels = Counter(r.risk_level for r in results)
    labels = Counter(r.label for r in results)
    families = Counter(r.family for r in results)
    return {
        "probe_id": probe_id,
        "flows": n,
        "flow_source": source,
        "model_version": results[0].model_version if results else None,
        "recognized": round(sum(r.is_attack for r in results) / n, 4),
        "unusual": round(sum(r.is_unusual for r in results) / n, 4),
        "mean_confidence": round(float(np.mean([r.confidence for r in results])), 4),
        "levels": {lvl: levels.get(lvl, 0) for lvl in ("high", "medium", "suspicious", "low")},
        "labels": dict(labels.most_common(4)),
        "families": dict(families.most_common(3)),
        "needs_review": sum(r.needs_review for r in results),
    }


async def probe(ctx: AppContext, n: int = 40) -> dict:
    rng = np.random.default_rng()
    source = get_flow_source(ctx.settings)
    items = [source.sample(PROBE_BEHAVIOUR, rng) for _ in range(n)]
    results = await asyncio.to_thread(ctx.engine.detect_many, "network", [f for f, _ in items])
    probe_id = uuid.uuid4().hex[:12]
    async with ctx.db.session() as s:
        for (features, meta), r in zip(items, results):
            det = Detection(
                module="network", origin="lab", label=r.label, confidence=r.confidence,
                anomaly_score=r.anomaly_score, risk_level=r.risk_level, top_features=[],
                model_version=r.model_version, family=r.family, risk_score=r.risk_score,
                is_attack=r.is_attack, is_unusual=r.is_unusual, models_agree=r.models_agree,
                action="none", breakdown=r.breakdown, probabilities=r.probabilities, features=features,
                src_ip=meta["src_ip"], dst_ip=meta["dst_ip"], src_port=meta["src_port"],
                dst_port=meta["dst_port"], protocol=meta["protocol"])
            s.add(det)
            s.add(ReviewItem(module="network", detection_id=det.id, reason="lab_probe",
                             predicted_label=r.label, features=features,
                             context={"probe_id": probe_id, "anomaly_score": r.anomaly_score,
                                      "confidence": r.confidence, "probabilities": r.probabilities,
                                      "src_ip": meta["src_ip"]}))
        await s.commit()
    return _summary(results, probe_id, n, source.name)


async def teach(ctx: AppContext, probe_id: str, label: str, actor: str) -> dict:
    label = label.strip().lower().replace(" ", "_")
    async with ctx.db.session() as s:
        items = list(await s.scalars(select(ReviewItem).where(
            ReviewItem.reason == "lab_probe", ReviewItem.status == "pending")))
        items = [i for i in items if (i.context or {}).get("probe_id") == probe_id]
        for i in items:
            i.status, i.final_label, i.reviewer, i.reviewed_at = "confirmed", label, actor, utcnow()
        await s.commit()
    if not items:
        raise ValueError("no pending flows for this probe (already taught?)")
    result = await learning.run_retrain(ctx, "network", actor=actor)
    return {"labelled": len(items), "label": label, **result}


async def evasion(ctx: AppContext, attack: str, technique: str, steps: int, n: int) -> dict:
    source = get_flow_source(ctx.settings)
    return await asyncio.to_thread(adversarial.sweep, ctx.engine, attack, technique, steps, n, 7, source)
