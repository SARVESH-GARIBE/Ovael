"""Website analysis: submit -> (cache | queue) -> scan -> detect + SHAP -> report -> scan_complete."""

from __future__ import annotations

import hashlib
import logging
import time

import httpx

from ..api.schemas import DetectionOut, ScanOut
from ..core import metrics
from ..core.context import AppContext
from ..db.models import Detection, Scan, utcnow
from ..scanner import url_guard
from . import pipeline

log = logging.getLogger(__name__)


class RateLimited(Exception):
    def __init__(self, retry_after: int):
        self.retry_after = retry_after


def _cache_key(domain: str) -> str:
    return f"scan:domain:{domain}"


async def submit(ctx: AppContext, raw_url: str, client_ip: str) -> Scan:
    s = ctx.settings
    checked = await url_guard.check(raw_url, s.max_url_length)  # raises UnsafeURL
    client_hash = hashlib.sha256(client_ip.encode()).hexdigest()[:32]
    allowed, retry = await ctx.cache.hit(f"scan:{client_hash}", s.scan_rate_limit, s.scan_rate_window_s)
    if not allowed:
        raise RateLimited(retry)

    cached = await ctx.cache.get_json(_cache_key(checked.domain))
    async with ctx.db.session() as session:
        if cached:
            scan = Scan(url=checked.url, domain=checked.domain, status="completed", cached=True,
                        detection_id=cached["detection_id"], report=cached["report"],
                        finished_at=utcnow(), client_hash=client_hash)
        else:
            scan = Scan(url=checked.url, domain=checked.domain, status="queued", client_hash=client_hash)
        session.add(scan)
        await session.commit()
    metrics.SCANS.labels("cached" if cached else "queued").inc()
    if not cached:
        await ctx.jobs.submit_scan(scan.id)
    return scan


async def _scan_features(ctx: AppContext, scan: Scan) -> dict:
    s = ctx.settings
    if s.scanner_url:
        async with httpx.AsyncClient(timeout=s.scan_timeout_s + 30) as client:
            r = await client.post(f"{s.scanner_url}/scan", json={"url": scan.url, "scan_id": scan.id})
            if r.status_code >= 400:
                raise RuntimeError(r.json().get("detail", r.text) if r.headers.get("content-type", "").startswith("application/json") else r.text)
            return r.json()
    if ctx.scanner is None:
        from ..scanner.runner import WebsiteScanner

        ctx.scanner = WebsiteScanner(s.crawler_path, s.max_concurrent_scans, s.scan_timeout_s)
    checked = url_guard.normalize(scan.url)
    return await ctx.scanner.scan(checked.url, checked.hostname, checked.domain, scan.id)


async def run_scan(ctx: AppContext, scan_id: str) -> None:
    async with ctx.db.session() as session:
        scan = await session.get(Scan, scan_id)
        if scan is None or scan.status not in ("queued", "running"):
            return
        scan.status = "running"
        await session.commit()
    await ctx.bus.publish("scan_update", ScanOut.model_validate(scan).model_dump(mode="json"))

    t0 = time.monotonic()
    metrics.SCANS_RUNNING.inc()
    detection = None
    try:
        out = await _scan_features(ctx, scan)
        [detection] = await pipeline.process(ctx, "website", [{"features": out["features"], "meta": {}}],
                                             scan_id=scan.id, explain=True)
        scan.status, scan.report, scan.detection_id = "completed", out["report"], detection.id
        await ctx.cache.set_json(_cache_key(scan.domain), {"detection_id": detection.id, "report": out["report"]},
                                 ctx.settings.scan_cache_ttl_s)
    except Exception as exc:
        log.warning("scan %s failed: %s", scan_id, exc)
        scan.status, scan.error = "failed", str(exc)[:500]
    finally:
        metrics.SCANS_RUNNING.dec()
    scan.finished_at = utcnow()
    metrics.SCANS.labels(scan.status).inc()
    metrics.SCAN_LATENCY.observe(time.monotonic() - t0)
    async with ctx.db.session() as session:
        await session.merge(scan)
        await session.commit()

    payload = ScanOut.model_validate(scan).model_dump(mode="json")
    payload["detection"] = DetectionOut.model_validate(detection).model_dump(mode="json") if detection else None
    await ctx.bus.publish("scan_complete", payload)


async def load_detection(ctx: AppContext, detection_id: str | None) -> Detection | None:
    if not detection_id:
        return None
    async with ctx.db.session() as session:
        return await session.get(Detection, detection_id)
