"""Review queue decisions and the retrain job that consumes them."""

from __future__ import annotations

import asyncio
import logging

import pandas as pd
from sqlalchemy import func, select

from ..core.context import AppContext
from ..db.models import AuditLog, ReviewItem, utcnow
from ..learning_loop.retrain import retrain

log = logging.getLogger(__name__)


async def _unused_confirmed(session, module: str) -> int:
    return await session.scalar(
        select(func.count()).select_from(ReviewItem)
        .where(ReviewItem.module == module, ReviewItem.status == "confirmed",
               ReviewItem.used_in_version.is_(None))) or 0


async def confirm(ctx: AppContext, item_id: str, label: str, note: str | None, actor: str) -> ReviewItem | None:
    async with ctx.db.session() as session:
        item = await session.get(ReviewItem, item_id)
        if item is None:
            return None
        if item.status != "pending":
            raise ValueError(f"item is already {item.status}")
        item.status, item.final_label, item.note = "confirmed", label.strip().lower(), note
        item.reviewer, item.reviewed_at = actor, utcnow()
        session.add(AuditLog(actor=actor, action="review.confirm", target=item.id,
                             detail={"label": item.final_label, "predicted": item.predicted_label}))
        await session.commit()
        pending = await _unused_confirmed(session, item.module)
    if pending >= ctx.settings.retrain_min_new_samples:
        await ctx.jobs.submit_retrain(item.module)
    return item


async def reject(ctx: AppContext, item_id: str, note: str | None, actor: str) -> ReviewItem | None:
    async with ctx.db.session() as session:
        item = await session.get(ReviewItem, item_id)
        if item is None:
            return None
        if item.status != "pending":
            raise ValueError(f"item is already {item.status}")
        item.status, item.note, item.reviewer, item.reviewed_at = "rejected", note, actor, utcnow()
        session.add(AuditLog(actor=actor, action="review.reject", target=item.id, detail={}))
        await session.commit()
    return item


async def run_retrain(ctx: AppContext, module: str, actor: str = "learning_loop") -> dict:
    async with ctx.db.session() as session:
        items = list(await session.scalars(
            select(ReviewItem).where(ReviewItem.module == module, ReviewItem.status == "confirmed")))
    reviewed = pd.DataFrame([{**i.features, "label": i.final_label} for i in items]) if items else None
    await ctx.bus.publish("model_retraining", {"module": module, "reviewed_samples": len(items)})
    try:
        result = await asyncio.to_thread(retrain, module, ctx.settings, ctx.registry, reviewed)
    except Exception as exc:
        log.exception("retrain %s failed", module)
        await ctx.bus.publish("model_retrained", {"module": module, "promoted": False, "error": str(exc)})
        return {"module": module, "promoted": False, "error": str(exc)}
    async with ctx.db.session() as session:
        for i in items:
            if i.used_in_version is None:
                i.used_in_version = result["version"]
                await session.merge(i)
        session.add(AuditLog(actor=actor, action="model.retrain", target=result["version"],
                             detail={k: result[k] for k in ("promoted", "reason", "previous_version")}))
        await session.commit()
    await ctx.bus.publish("model_retrained", result)
    return result
