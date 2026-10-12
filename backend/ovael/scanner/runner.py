"""One website scan, reusing the dataset crawler so live scans and training data are measured the
same way (same instrumentation, same tracker reference, same feature computation).

A `WebsiteScanner` keeps one Chromium alive and opens a fresh browser context per scan. A
semaphore caps concurrent scans, which caps memory: Chromium is the heaviest part of the system.
"""

from __future__ import annotations

import asyncio
import logging
import sys
import time
from pathlib import Path

from . import insights

log = logging.getLogger(__name__)


class ScanFailed(RuntimeError):
    pass


def _import_crawler(crawler_path: Path):
    if str(crawler_path) not in sys.path:
        sys.path.insert(0, str(crawler_path))
    from ovael_crawler import schema  # noqa: PLC0415
    from ovael_crawler.config import CrawlConfig  # noqa: PLC0415
    from ovael_crawler.crawler import Crawler  # noqa: PLC0415
    from ovael_crawler.reference import TrackerReference  # noqa: PLC0415

    return schema, CrawlConfig, Crawler, TrackerReference


def build_report(rec: dict, features: dict) -> dict:
    """The facts the report card shows next to the model's reasons."""
    final = rec.get("final") or {}
    trackers = (rec.get("tracker_summary") or {}).get("matched_hosts", [])
    trackers = sorted(trackers, key=lambda h: -h.get("request_count", 0))[:12]
    cookies = rec.get("cookie_summary") or {}
    nav = rec.get("navigation") or {}
    return {
        "final_url": final.get("url"),
        "title": final.get("title"),
        "http_status": final.get("http_status"),
        "crawl_status": rec["crawl"]["status"],
        "trackers": [{
            "hostname": h.get("hostname"), "requests": h.get("request_count"),
            "owner": h.get("owner_display_name") or h.get("owner_name"),
            "categories": h.get("categories", []),
        } for h in trackers],
        "third_party_cookie_domains": cookies.get("third_party_cookie_domains", [])[:20],
        "redirect_chain": [step.get("url") if isinstance(step, dict) else step
                           for step in nav.get("http_redirect_chain", [])][:10],
        "fingerprinting": {k: features.get(k) for k in (
            "canvas_readback_calls", "webgl_unmasked_info_queries", "offline_audio_contexts",
            "audio_api_calls", "other_fingerprinting_api_calls")},
        "counts": {k: features.get(k) for k in (
            "total_requests", "third_party_requests", "tracker_matched_requests",
            "unique_tracker_domains", "total_cookies", "third_party_cookies", "hidden_iframe_count",
            "redirect_count")},
        "blocked_destinations": len((rec.get("safety") or {}).get("blocked_destinations", [])),
    }


class WebsiteScanner:
    def __init__(self, crawler_path: Path, max_concurrent: int = 2, timeout_s: float = 90.0):
        self.schema, CrawlConfig, self.Crawler, TrackerReference = _import_crawler(crawler_path)
        self.cfg = CrawlConfig(workers=1, settle_s=3.0, navigation_timeout_s=25.0,
                               load_event_timeout_s=10.0, max_retries=1, overall_timeout_s=timeout_s,
                               collect_page_signals=True)
        self.ref = TrackerReference()
        self.timeout_s = timeout_s
        self.sem = asyncio.Semaphore(max_concurrent)
        self._pw_cm = None
        self._crawler = None

    async def start(self) -> None:
        from playwright.async_api import async_playwright

        self._pw_cm = async_playwright()
        pw = await self._pw_cm.__aenter__()
        self._crawler = self.Crawler(self.cfg, self.ref, store=None)
        self._crawler._pw = pw
        await self._crawler.get_browser()

    async def stop(self) -> None:
        if self._crawler and self._crawler.browser:
            await self._crawler.browser.close()
        if self._pw_cm:
            await self._pw_cm.__aexit__(None, None, None)

    async def scan(self, url: str, hostname: str, domain: str, scan_id: str) -> dict:
        if self._crawler is None:
            await self.start()
        entry = {"website_id": f"S{scan_id[:12]}", "tranco_rank": None, "original_domain": hostname,
                 "original_url": url, "candidate_urls": [url], "initial_registrable_domain": domain}
        async with self.sem:
            t0 = time.monotonic()
            attempts: list = []
            timed_out = False
            try:
                final = await asyncio.wait_for(self._crawler.visit(entry, attempts), self.timeout_s)
            except asyncio.TimeoutError:
                final, timed_out = (attempts[-1] if attempts else None), True
            rec, _, _ = self._crawler.build_record(entry, attempts, final, timed_out)
        status = rec["crawl"]["status"]
        if status not in ("success", "http_error"):
            raise ScanFailed(rec["crawl"].get("failure_reason") or status)
        features = self.schema.compute_features(rec, self.ref.categories)
        report = build_report(rec, features)
        try:
            report["insights"] = await insights.gather(rec, final.data, hostname, domain)
        except Exception as exc:  # the smart report is extra; the model's verdict stands without it
            log.warning("insights for %s failed: %s", hostname, exc)
        return {"features": features, "report": report,
                "seconds": round(time.monotonic() - t0, 2)}
