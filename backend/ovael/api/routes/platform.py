"""Health, taxonomy, statistics and the traffic simulator."""

from __future__ import annotations

from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from sqlalchemy import func, select

from ... import __version__
from ...core.context import AppContext
from ...db.models import DefenseAction, Detection, Incident, ReviewItem, utcnow
from ...feature_extraction import SCHEMAS
from ...orchestrator import families
from ...orchestrator.decision import BANDS
from ...simulator.traffic import SCENARIOS
from ..deps import get_ctx, require_admin
from ..schemas import Module, SimulateRequest

router = APIRouter(tags=["platform"])


@router.get("/api/health/live", summary="Process is up")
async def live() -> dict:
    return {"ok": True}


@router.get("/api/health/ready", summary="Ready for traffic: database reachable, models loaded")
async def ready(response: Response, ctx: AppContext = Depends(get_ctx)) -> dict:
    checks = {}
    try:
        checks["database"] = await ctx.db.ping()
    except Exception:
        checks["database"] = False
    if ctx.redis is not None:
        try:
            checks["redis"] = bool(await ctx.redis.ping())
        except Exception:
            checks["redis"] = False
    for m in ("network", "website"):
        checks[f"model_{m}"] = ctx.registry.available(m)
    ok = all(checks.values())
    if not ok:
        response.status_code = 503
    return {"ok": ok, "instance": ctx.settings.instance_id, "version": __version__, "checks": checks}


@router.get("/metrics", include_in_schema=False)
async def prometheus() -> Response:
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


@router.get("/api/taxonomy", tags=["platform"], summary="Attack families, severity weights, how each attack works")
async def taxonomy(module: Module | None = None) -> dict:
    return {
        "families": [f.to_dict() for f in families(module)],
        "risk_bands": {k.value: list(v) for k, v in BANDS.items()},
        "decision_table": [
            {"classifier": "attack", "anomaly": "unusual", "risk_level": "high",
             "network": "Alert, auto-defense allowed", "website": "Known tracker behaviour that is also unusual"},
            {"classifier": "attack", "anomaly": "normal", "risk_level": "medium",
             "network": "Alert only", "website": "A typical known tracker"},
            {"classifier": "normal", "anomaly": "unusual", "risk_level": "suspicious",
             "network": "Alert, saved for review", "website": "Possible unknown tracker, saved for review"},
            {"classifier": "normal", "anomaly": "normal", "risk_level": "low",
             "network": "No action", "website": "Nothing flagged"},
        ],
    }


@router.get("/api/system", summary="Active models, feature schemas and runtime mode")
async def system(ctx: AppContext = Depends(get_ctx)) -> dict:
    s = ctx.settings
    models = {}
    for m in ("network", "website"):
        try:
            models[m] = ctx.registry.active(m).summary()
        except Exception as exc:
            models[m] = {"error": str(exc)}
    return {
        "instance": s.instance_id, "version": __version__, "env": s.env,
        "defense_mode": s.defense_mode, "simulator": s.enable_simulator,
        "infrastructure": {"redis": bool(s.redis_url), "queue": bool(s.celery_broker_url),
                           "scanner_service": bool(s.scanner_url), "read_replica": bool(s.database_read_url)},
        "models": models, "feature_counts": {m: len(c) for m, c in SCHEMAS.items()},
    }


def _minute_bucket(dialect: str):
    if dialect == "postgresql":
        return func.date_trunc("minute", Detection.created_at)
    return func.strftime("%Y-%m-%dT%H:%M:00", Detection.created_at)


@router.get("/api/stats/summary", summary="Counts for the dashboard")
async def stats(ctx: AppContext = Depends(get_ctx), module: Module | None = None,
                window_minutes: int = Query(60, ge=1, le=7 * 24 * 60)) -> dict:
    since = utcnow() - timedelta(minutes=window_minutes)
    base = [Detection.created_at >= since] + ([Detection.module == module] if module else [])
    async with ctx.db.read_session() as s:
        dialect = s.bind.dialect.name
        by_level = dict((await s.execute(select(Detection.risk_level, func.count())
                                         .where(*base).group_by(Detection.risk_level))).all())
        by_family = dict((await s.execute(select(Detection.family, func.count())
                                          .where(*base, Detection.risk_level != "low")
                                          .group_by(Detection.family))).all())
        bucket = _minute_bucket(dialect).label("bucket")
        rows = (await s.execute(select(bucket, Detection.risk_level, func.count())
                                .where(*base).group_by(bucket, Detection.risk_level).order_by(bucket))).all()
        open_incidents = await s.scalar(select(func.count()).select_from(Incident)
                                        .where(Incident.status == "open", Incident.last_seen >= since))
        pending_reviews = await s.scalar(select(func.count()).select_from(ReviewItem)
                                         .where(ReviewItem.status == "pending"))
        active_blocks = await s.scalar(select(func.count()).select_from(DefenseAction)
                                       .where(DefenseAction.status.in_(("applied", "simulated"))))
    timeline: dict[str, dict] = {}
    for b, level, n in rows:
        key = b if isinstance(b, str) else b.isoformat()
        timeline.setdefault(key, {"t": key, "low": 0, "suspicious": 0, "medium": 0, "high": 0})[level] = n
    return {"window_minutes": window_minutes, "by_risk_level": by_level, "by_family": by_family,
            "timeline": list(timeline.values()), "open_incidents": open_incidents or 0,
            "pending_reviews": pending_reviews or 0, "active_blocks": active_blocks or 0,
            "total": sum(by_level.values())}


def _simulator(ctx: AppContext):
    if not ctx.settings.enable_simulator:
        raise HTTPException(404, "simulator disabled")
    if "simulator" not in ctx.state:
        from ...simulator.traffic import Simulator

        ctx.state["simulator"] = Simulator(ctx)
    return ctx.state["simulator"]


@router.get("/api/simulate", tags=["simulator"], summary="Simulator status and scenarios")
async def sim_status(ctx: AppContext = Depends(get_ctx)) -> dict:
    return {**_simulator(ctx).status, "scenarios": list(SCENARIOS)}


@router.post("/api/simulate", tags=["simulator"],
             summary="Push synthetic sandbox flows through the real pipeline")
async def sim_start(body: SimulateRequest, ctx: AppContext = Depends(get_ctx),
                    _: str = Depends(require_admin)) -> dict:
    try:
        return _simulator(ctx).start(body.scenario, body.duration_s)
    except KeyError:
        raise HTTPException(422, f"unknown scenario; choose one of {list(SCENARIOS)}")


@router.delete("/api/simulate", tags=["simulator"], summary="Stop the simulator")
async def sim_stop(ctx: AppContext = Depends(get_ctx), _: str = Depends(require_admin)) -> dict:
    _simulator(ctx).stop()
    return {"running": False}
