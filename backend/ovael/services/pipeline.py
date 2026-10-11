"""The live path for one batch of feature vectors, shared by both modules:

    detect() -> incident grouping -> save -> hard examples -> auto-defense -> push to dashboard

Push volume is controlled here, because a flood can produce thousands of detections a second and
no browser should receive all of them:
  * alerts (risk above low) are pushed once when their incident opens, then at most once per
    `incident_push_interval_s` per incident, each carrying the incident's running count;
  * normal traffic is sampled to a few events a second so the theater still shows calm flows.
Everything is still saved; the push is a view, the database is the record.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections import defaultdict
from datetime import timedelta

from sqlalchemy import select

from ..api.schemas import ActionOut, IncidentOut, LiveDetection, ReviewItemOut
from ..core import metrics
from ..core.context import AppContext
from ..core.detect import DetectionResult
from ..db.models import Detection, Incident, ReviewItem, utcnow

log = logging.getLogger(__name__)
BENIGN_PUSH_PER_S = 4


def _review_reason(r: DetectionResult) -> str:
    return "normal_but_unusual" if r.risk_level == "suspicious" else "low_confidence"


async def _incident_for(session, ctx: AppContext, r: DetectionResult, meta: dict,
                        cache: dict) -> tuple[Incident | None, bool]:
    if r.risk_level == "low":
        return None, False
    key = (r.module, meta.get("src_ip"), r.family)
    if key in cache:
        return cache[key], False
    since = utcnow() - timedelta(seconds=ctx.settings.incident_window_s)
    inc = await session.scalar(
        select(Incident).where(Incident.module == r.module, Incident.src_ip == meta.get("src_ip"),
                               Incident.family == r.family, Incident.status != "closed",
                               Incident.last_seen >= since)
        .order_by(Incident.last_seen.desc()).limit(1))
    created = inc is None
    if created:
        inc = Incident(module=r.module, family=r.family, label=r.label, src_ip=meta.get("src_ip"),
                       dst_ip=meta.get("dst_ip"), risk_level=r.risk_level, max_risk_score=r.risk_score,
                       detection_count=0)
        session.add(inc)
        await session.flush()
    cache[key] = inc
    return inc, created


_LEVEL_ORDER = {"low": 0, "suspicious": 1, "medium": 2, "high": 3}


def _should_push(ctx: AppContext, det: Detection, incident: Incident | None, created: bool) -> bool:
    now = time.monotonic()
    if incident is None:
        bucket = ctx.state.setdefault("benign_push", [0.0, 0])
        if now - bucket[0] >= 1.0:
            bucket[0], bucket[1] = now, 0
        bucket[1] += 1
        return bucket[1] <= BENIGN_PUSH_PER_S
    last = ctx.state.setdefault("incident_push", {})
    if created or now - last.get(incident.id, 0.0) >= ctx.settings.incident_push_interval_s:
        last[incident.id] = now
        if len(last) > 10_000:
            last.clear()
        return True
    return False


async def process(ctx: AppContext, module: str, items: list[dict], *, origin: str = "live",
                  scan_id: str | None = None, explain: bool = False) -> list[Detection]:
    """`items` are {"features": {...}, "meta": {...}} dicts. Returns the saved detections."""
    t0 = time.perf_counter()
    results = await asyncio.to_thread(ctx.engine.detect_many, module, [i["features"] for i in items], explain)
    metrics.DETECT_LATENCY.labels(module).observe(time.perf_counter() - t0)

    events: list[tuple[str, dict]] = []
    saved: list[Detection] = []
    to_explain: list[tuple[Detection, dict]] = []
    async with ctx.db.session() as session:
        incidents: dict = {}
        new_incidents: set[str] = set()
        for item, r in zip(items, results):
            meta = item.get("meta") or {}
            incident, created = await _incident_for(session, ctx, r, meta, incidents)
            det = Detection(
                module=module, origin=origin, label=r.label, confidence=r.confidence,
                anomaly_score=r.anomaly_score, risk_level=r.risk_level, top_features=r.top_features,
                model_version=r.model_version, family=r.family, risk_score=r.risk_score,
                is_attack=r.is_attack, is_unusual=r.is_unusual, models_agree=r.models_agree,
                action=r.action, breakdown=r.breakdown, probabilities=r.probabilities,
                features=item["features"], src_ip=meta.get("src_ip"), dst_ip=meta.get("dst_ip"),
                src_port=meta.get("src_port"), dst_port=meta.get("dst_port"),
                protocol=meta.get("protocol"), scan_id=scan_id,
                incident_id=incident.id if incident else None)
            session.add(det)
            saved.append(det)
            metrics.DETECTIONS.labels(module, r.risk_level).inc()

            if incident is not None:
                incident.detection_count += 1
                incident.last_seen = utcnow()
                incident.last_detection_id = det.id
                if r.risk_score > incident.max_risk_score:
                    incident.max_risk_score = r.risk_score
                if _LEVEL_ORDER[r.risk_level] > _LEVEL_ORDER[incident.risk_level]:
                    incident.risk_level = r.risk_level
                if created:
                    new_incidents.add(incident.id)
                    if not explain:
                        to_explain.append((det, item["features"]))

            if r.needs_review:
                review = ReviewItem(module=module, detection_id=det.id, reason=_review_reason(r),
                                    predicted_label=r.label, features=item["features"],
                                    context={"anomaly_score": r.anomaly_score, "confidence": r.confidence,
                                             "probabilities": r.probabilities, "src_ip": meta.get("src_ip"),
                                             "scan_id": scan_id})
                session.add(review)
                metrics.REVIEW_QUEUE.labels(module, review.reason).inc()
                if incident is None or incident.id in new_incidents:
                    events.append(("review_item", review))

            action = await ctx.defense.maybe_block(session, r, det.id, incident.id if incident else None,
                                                   meta.get("src_ip"))
            if action is not None:
                if incident is not None and action.status in ("applied", "simulated"):
                    incident.status = "mitigated"
                events.append(("defense_action", action))

            if _should_push(ctx, det, incident, incident is not None and incident.id in new_incidents):
                events.append(("new_detection", (det, incident)))
            if incident is not None and incident.id in new_incidents:
                events.append(("incident_update", incident))
        await session.commit()

    # Reasons for the first detection of each new incident, so the side panel has them.
    if to_explain:
        try:
            explained = await asyncio.to_thread(
                lambda: [ctx.engine.explain(module, f, d.label, d.model_version) for d, f in to_explain])
            async with ctx.db.session() as session:
                for (det, _), feats in zip(to_explain, explained):
                    det.top_features = feats
                    await session.merge(det)
                await session.commit()
        except Exception as exc:
            log.warning("explaining new incidents failed: %s", exc)

    blocked_cache: dict[str, bool] = {}
    for type_, obj in events:
        if type_ == "new_detection":
            det, incident = obj
            ip = det.src_ip
            if ip not in blocked_cache:
                blocked_cache[ip] = await ctx.defense.is_blocked(ip)
            payload = LiveDetection.model_validate(det).model_copy(update={
                "blocked": blocked_cache[ip],
                "incident_count": incident.detection_count if incident else 1})
            await ctx.bus.publish("new_detection", payload.model_dump(mode="json"))
        elif type_ == "defense_action":
            await ctx.bus.publish("defense_action", ActionOut.model_validate(obj).model_dump(mode="json"))
        elif type_ == "review_item":
            await ctx.bus.publish("review_item", ReviewItemOut.model_validate(obj).model_dump(mode="json"))
        elif type_ == "incident_update":
            await ctx.bus.publish("incident_update", IncidentOut.model_validate(obj).model_dump(mode="json"))
    return saved


def group_counts(detections: list[Detection]) -> dict:
    out: dict = defaultdict(int)
    for d in detections:
        out[d.risk_level] += 1
    return dict(out)
