"""FastAPI application factory.

    uvicorn ovael.api.app:app --host 0.0.0.0 --port 8000

Instances are stateless (state lives in PostgreSQL, Redis and the shared model store), so any
number of them can run behind the load balancer and any instance can serve any request.
"""

from __future__ import annotations

import logging
import time
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse

from .. import __version__
from ..config import Settings, get_settings
from ..core import metrics
from ..core.context import build_context
from ..core.logging import setup_logging
from ..ml.registry import ModelNotAvailable
from ..scanner.url_guard import UnsafeURL
from ..services.scans import RateLimited
from . import ws
from .routes import learning, network, platform, website

log = logging.getLogger(__name__)


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    setup_logging(settings.log_level)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        ctx = await build_context(settings)
        app.state.ctx = ctx
        if settings.admin_token is None or settings.sensor_token is None:
            log.warning("admin/sensor tokens not set: write endpoints are open (fine for dev, not for prod)")
        for m in ("network", "website"):
            if not ctx.registry.available(m):
                log.warning("no active %s model; run `python -m ovael.cli train %s`", m, m)
        log.info("instance %s ready", settings.instance_id)
        yield
        await ctx.close()

    app = FastAPI(
        title="ovael.ai API",
        version=__version__,
        description="Network protection + website analysis on one detection contract.",
        lifespan=lifespan,
        docs_url="/api/docs",
        redoc_url=None,
        openapi_url="/api/openapi.json",
    )
    app.add_middleware(GZipMiddleware, minimum_size=1024)
    app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origins, allow_credentials=True,
                       allow_methods=["*"], allow_headers=["*"])

    @app.middleware("http")
    async def observe(request: Request, call_next):
        rid = request.headers.get("x-request-id") or uuid.uuid4().hex[:16]
        t0 = time.perf_counter()
        response = await call_next(request)
        route = request.scope.get("route")
        path = getattr(route, "path", "unmatched")
        elapsed = time.perf_counter() - t0
        metrics.HTTP_REQUESTS.labels(request.method, path, response.status_code).inc()
        metrics.HTTP_LATENCY.labels(request.method, path).observe(elapsed)
        response.headers["x-request-id"] = rid
        response.headers["x-served-by"] = settings.instance_id
        if path not in ("/metrics", "/api/health/live", "/api/health/ready"):
            log.info("%s %s %s %.1fms", request.method, path, response.status_code, elapsed * 1000,
                     extra={"request_id": rid})
        return response

    @app.exception_handler(UnsafeURL)
    async def _unsafe(_: Request, exc: UnsafeURL):
        return JSONResponse({"detail": str(exc)}, status_code=422)

    @app.exception_handler(RateLimited)
    async def _limited(_: Request, exc: RateLimited):
        return JSONResponse({"detail": f"too many scans; try again in {exc.retry_after}s"},
                            status_code=429, headers={"Retry-After": str(exc.retry_after)})

    @app.exception_handler(ModelNotAvailable)
    async def _no_model(_: Request, exc: ModelNotAvailable):
        return JSONResponse({"detail": str(exc)}, status_code=503)

    for r in (network.router, website.router, learning.router, platform.router, ws.router):
        app.include_router(r)
    return app


app = create_app()
