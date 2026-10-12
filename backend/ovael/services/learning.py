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


async def suggestions(ctx: AppContext, module: str, limit: int = 200) -> dict[str, dict]:
    from ..learning_loop.suggest import suggest

    async with ctx.db.read_session() as session:
        pending = list(await session.scalars(
            select(ReviewItem).where(ReviewItem.module == module, ReviewItem.status == "pending")
            .order_by(ReviewItem.created_at.desc()).limit(limit)))
        confirmed = list(await session.scalars(
            select(ReviewItem).where(ReviewItem.module == module, ReviewItem.status == "confirmed")
            .order_by(ReviewItem.reviewed_at.desc()).limit(1000)))
    try:
        bundle = ctx.registry.active(module)
        benign, known = set(bundle.benign_labels), set(bundle.classes)
    except Exception:
        benign, known = {"benign"}, None
    return await asyncio.to_thread(suggest, module, pending, confirmed, benign, known)


async def confirm_batch(ctx: AppContext, decisions: list[tuple[str, str]], note: str | None,
                        actor: str) -> dict:
    """Confirm many items at once. Items that are no longer pending are skipped, not failed."""
    labels = {item_id: label.strip().lower() for item_id, label in decisions}
    async with ctx.db.session() as session:
        items = list(await session.scalars(select(ReviewItem).where(ReviewItem.id.in_(list(labels)))))
        done, modules = [], set()
        for item in items:
            if item.status != "pending":
                continue
            item.status, item.final_label, item.note = "confirmed", labels[item.id], note
            item.reviewer, item.reviewed_at = actor, utcnow()
            done.append(item)
            modules.add(item.module)
        session.add(AuditLog(actor=actor, action="review.confirm_batch", target=f"{len(done)} items",
                             detail={"labels": _count(i.final_label for i in done)}))
        await session.commit()
        pending_counts = {m: await _unused_confirmed(session, m) for m in modules}
    for m, n in pending_counts.items():
        if n >= ctx.settings.retrain_min_new_samples:
            await ctx.jobs.submit_retrain(m)
    return {"confirmed": len(done), "skipped": len(decisions) - len(done),
            "labels": _count(i.final_label for i in done)}


def _count(values) -> dict[str, int]:
    out: dict[str, int] = {}
    for v in values:
        out[v] = out.get(v, 0) + 1
    return out


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
