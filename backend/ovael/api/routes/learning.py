"""Review queue and model registry."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select

from ...core.context import AppContext
from ...db.models import AuditLog, ReviewItem
from ...feature_extraction import describe
from ...ml.registry import ModelNotAvailable
from ...services import learning
from ..deps import get_ctx, require_admin
from ..schemas import Module, ModelVersionOut, RetrainResult, ReviewConfirm, ReviewItemOut, ReviewReject

router = APIRouter(prefix="/api", tags=["learning loop"])


@router.get("/review-queue", response_model=list[ReviewItemOut], summary="Hard examples")
async def review_queue(ctx: AppContext = Depends(get_ctx), module: Module | None = None,
                       status: str = "pending", limit: int = Query(50, ge=1, le=200)) -> list[ReviewItem]:
    q = select(ReviewItem).where(ReviewItem.status == status)
    if module:
        q = q.where(ReviewItem.module == module)
    async with ctx.db.read_session() as s:
        return list(await s.scalars(q.order_by(ReviewItem.created_at.desc()).limit(limit)))


async def _publish(ctx: AppContext, item: ReviewItem) -> ReviewItem:
    await ctx.bus.publish("review_item", ReviewItemOut.model_validate(item).model_dump(mode="json"))
    return item


@router.post("/review-queue/{item_id}/confirm", response_model=ReviewItemOut,
             summary="Confirm the final label of a hard example")
async def confirm(item_id: str, body: ReviewConfirm, ctx: AppContext = Depends(get_ctx),
                  actor: str = Depends(require_admin)) -> ReviewItem:
    try:
        item = await learning.confirm(ctx, item_id, body.label, body.note, actor)
    except ValueError as exc:
        raise HTTPException(409, str(exc))
    if item is None:
        raise HTTPException(404, "review item not found")
    return await _publish(ctx, item)


@router.post("/review-queue/{item_id}/reject", response_model=ReviewItemOut,
             summary="Discard a hard example (noise, not worth learning)")
async def reject(item_id: str, body: ReviewReject, ctx: AppContext = Depends(get_ctx),
                 actor: str = Depends(require_admin)) -> ReviewItem:
    try:
        item = await learning.reject(ctx, item_id, body.note, actor)
    except ValueError as exc:
        raise HTTPException(409, str(exc))
    if item is None:
        raise HTTPException(404, "review item not found")
    return await _publish(ctx, item)


@router.get("/models", response_model=list[ModelVersionOut], summary="Model versions per module")
async def list_models(ctx: AppContext = Depends(get_ctx), module: Module | None = None) -> list[dict]:
    mods = [module] if module else ["network", "website"]
    return [v for m in mods for v in ctx.registry.list_versions(m)]


@router.get("/models/{module}/schema", summary="Feature schema of the active model, with the normal baseline")
async def model_schema(module: Module, ctx: AppContext = Depends(get_ctx)) -> dict:
    bundle = ctx.registry.active(module)
    return {
        "module": module,
        "version": bundle.version,
        "threshold": bundle.threshold,
        "classes": bundle.classes,
        "features": [{"name": f, "description": describe(module, f), "baseline": bundle.baseline.get(f)}
                     for f in bundle.features],
    }


@router.post("/models/{module}/retrain", response_model=RetrainResult, status_code=202,
             summary="Retrain with confirmed reviews; promoted only if it beats the active model")
async def retrain(module: Module, ctx: AppContext = Depends(get_ctx),
                  actor: str = Depends(require_admin)) -> RetrainResult:
    queued = await ctx.jobs.submit_retrain(module)
    async with ctx.db.session() as s:
        s.add(AuditLog(actor=actor, action="model.retrain_requested", target=module, detail={"queued": queued}))
        await s.commit()
    return RetrainResult(queued=queued, module=module)


@router.post("/models/{module}/{version}/promote", response_model=ModelVersionOut,
             summary="Make a version active (also used to roll back)")
async def promote(module: Module, version: str, ctx: AppContext = Depends(get_ctx),
                  actor: str = Depends(require_admin)) -> dict:
    try:
        ctx.registry.promote(module, version)
        meta = ctx.registry.meta(module, version)
    except ModelNotAvailable as exc:
        raise HTTPException(404, str(exc))
    async with ctx.db.session() as s:
        s.add(AuditLog(actor=actor, action="model.promote", target=version, detail={}))
        await s.commit()
    await ctx.bus.publish("model_retrained", {"module": module, "version": version, "promoted": True,
                                              "reason": f"manually promoted by {actor}"})
    return {**meta, "status": "active"}
