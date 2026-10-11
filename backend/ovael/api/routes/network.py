"""Network protection: sensor ingest, detections, incidents, defense actions."""

from __future__ import annotations

import asyncio
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select

from ...core.context import AppContext
from ...db.models import DefenseAction, Detection, Incident
from ...services import pipeline
from ..deps import get_ctx, require_admin, require_sensor
from ..schemas import (ActionOut, DetectionDetail, DetectionOut, DetectRequest, FlowBatch,
                       FlowBatchResult, IncidentOut, Module, RiskLevel)

router = APIRouter(prefix="/api", tags=["network"])


@router.post("/flows", response_model=FlowBatchResult, summary="Ingest flows from the sandbox sensor")
async def ingest_flows(batch: FlowBatch, ctx: AppContext = Depends(get_ctx),
                       _: str = Depends(require_sensor)) -> FlowBatchResult:
    items = [{"features": f.features,
              "meta": {"src_ip": f.src_ip, "dst_ip": f.dst_ip, "src_port": f.src_port,
                       "dst_port": f.dst_port if f.dst_port is not None else f.features.get("dst_port"),
                       "protocol": f.protocol if f.protocol is not None else f.features.get("protocol")}}
             for f in batch.flows]
    saved = await pipeline.process(ctx, "network", items, origin=batch.origin)
    blocked = sorted({d.src_ip for d in saved if d.src_ip and await ctx.defense.is_blocked(d.src_ip)})
    return FlowBatchResult(accepted=len(saved), alerts=sum(d.risk_level != "low" for d in saved),
                           blocked_sources=blocked)


@router.post("/detect", summary="Run detect() on one feature vector without saving it")
async def detect_once(req: DetectRequest, ctx: AppContext = Depends(get_ctx),
                      _: str = Depends(require_admin)) -> dict:
    result = await asyncio.to_thread(ctx.engine.detect, req.module, req.features, req.explain)
    return result.to_dict()


@router.get("/detections", response_model=list[DetectionOut], summary="Recent detections (alert feed)")
async def list_detections(
    ctx: AppContext = Depends(get_ctx),
    module: Module | None = None,
    risk_level: list[RiskLevel] | None = Query(None),
    alerts_only: bool = False,
    origin: str | None = None,
    src_ip: str | None = None,
    before: datetime | None = Query(None, description="Cursor: created_at of the last item seen"),
    limit: int = Query(50, ge=1, le=200),
) -> list[Detection]:
    q = select(Detection)
    if module:
        q = q.where(Detection.module == module)
    if risk_level:
        q = q.where(Detection.risk_level.in_(risk_level))
    if alerts_only:
        q = q.where(Detection.risk_level != "low")
    if origin:
        q = q.where(Detection.origin == origin)
    if src_ip:
        q = q.where(Detection.src_ip == src_ip)
    if before:
        q = q.where(Detection.created_at < before)
    async with ctx.db.read_session() as s:
        return list(await s.scalars(q.order_by(Detection.created_at.desc()).limit(limit)))


@router.get("/detections/{detection_id}", response_model=DetectionDetail)
async def get_detection(detection_id: str, explain: bool = True,
                        ctx: AppContext = Depends(get_ctx)) -> Detection:
    async with ctx.db.session() as s:
        det = await s.get(Detection, detection_id)
        if det is None:
            raise HTTPException(404, "detection not found")
        if explain and not det.top_features and det.risk_level != "low":
            # SHAP on demand (section 2.3): computed once, then stored with the detection.
            det.top_features = await asyncio.to_thread(
                ctx.engine.explain, det.module, det.features, det.label, det.model_version)
            await s.commit()
        return det


@router.get("/incidents", response_model=list[IncidentOut], summary="Grouped alerts")
async def list_incidents(ctx: AppContext = Depends(get_ctx), module: Module | None = None,
                         status: str | None = None, limit: int = Query(50, ge=1, le=200)) -> list[Incident]:
    q = select(Incident)
    if module:
        q = q.where(Incident.module == module)
    if status:
        q = q.where(Incident.status == status)
    async with ctx.db.read_session() as s:
        return list(await s.scalars(q.order_by(Incident.last_seen.desc()).limit(limit)))


@router.get("/incidents/{incident_id}")
async def get_incident(incident_id: str, ctx: AppContext = Depends(get_ctx)) -> dict:
    async with ctx.db.read_session() as s:
        inc = await s.get(Incident, incident_id)
        if inc is None:
            raise HTTPException(404, "incident not found")
        dets = await s.scalars(select(Detection).where(Detection.incident_id == incident_id)
                               .order_by(Detection.created_at.desc()).limit(50))
        actions = await s.scalars(select(DefenseAction).where(DefenseAction.incident_id == incident_id))
        return {"incident": IncidentOut.model_validate(inc),
                "detections": [DetectionOut.model_validate(d) for d in dets],
                "actions": [ActionOut.model_validate(a) for a in actions]}


@router.get("/actions", response_model=list[ActionOut], summary="Defense action log")
async def list_actions(ctx: AppContext = Depends(get_ctx), limit: int = Query(50, ge=1, le=200)) -> list[DefenseAction]:
    async with ctx.db.read_session() as s:
        return list(await s.scalars(select(DefenseAction).order_by(DefenseAction.created_at.desc()).limit(limit)))


@router.post("/actions/{action_id}/undo", response_model=ActionOut, summary="Undo a block")
async def undo_action(action_id: str, ctx: AppContext = Depends(get_ctx),
                      actor: str = Depends(require_admin)) -> DefenseAction:
    async with ctx.db.session() as s:
        try:
            action = await ctx.defense.undo(s, action_id, actor)
        except ValueError as exc:
            raise HTTPException(409, str(exc))
        if action is None:
            raise HTTPException(404, "action not found")
        if action.incident_id:
            inc = await s.get(Incident, action.incident_id)
            if inc is not None and inc.status == "mitigated":
                inc.status = "open"
        await s.commit()
    payload = ActionOut.model_validate(action).model_dump(mode="json")
    await ctx.bus.publish("defense_action", payload)
    return action
