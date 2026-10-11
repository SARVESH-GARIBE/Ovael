"""Resumable Playwright crawler: one fresh browser context per website (per attempt)."""

from __future__ import annotations

import asyncio
import csv
import json
import logging
import os
import platform
import re
import secrets
import signal
import sys
import time
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

from playwright.async_api import Error as PlaywrightError
from playwright.async_api import TimeoutError as PlaywrightTimeout
from playwright.async_api import async_playwright

from . import SCHEMA_VERSION, config
from .config import CrawlConfig
from .domains import hostname_of, origin_of, registrable_domain, sanitize_url
from .reference import TrackerReference, registrable_or_host, utcnow
from .safety_proxy import SafetyProxy
from .schema import compute_features, csv_columns, summarize_requests

log = logging.getLogger("ovael.crawler")

TRANSIENT = {"timeout", "connect_timeout", "dns_timeout", "connection_error", "http_429", "http_503"}
UNREACHABLE = {"dns_failure", "connect_refused", "connect_failed", "tls_error"}
TRACKER_CSV_COLUMNS = [
    "website_id", "site_final_registrable_domain", "hostname", "matched_tracker_domain", "request_count",
    "resource_types", "same_entity_as_site", "owner_name", "owner_display_name", "owned_by", "categories",
    "categories_available", "fingerprinting_metadata_available", "fingerprinting_score",
    "cookies_prevalence", "prevalence", "default_action", "reference_source", "reference_sha256",
    "reference_retrieved_at",
]

DOM_STATS_JS = """() => ({elements: document.getElementsByTagName('*').length,
  text: document.body ? document.body.innerText.length : 0})"""

DOM_IFRAMES_JS = """() => Array.from(document.querySelectorAll('iframe')).map(el => {
  const r = el.getBoundingClientRect();
  let rendered = true;
  try { rendered = el.checkVisibility({opacityProperty: true, visibilityProperty: true}); }
  catch (e) { const cs = getComputedStyle(el);
    rendered = !(cs.display === 'none' || cs.visibility === 'hidden' || parseFloat(cs.opacity) === 0); }
  const tiny = el.clientWidth <= 1 || el.clientHeight <= 1;
  const offscreen = r.right <= 0 || r.bottom <= 0;
  return {hidden: !rendered || tiny || offscreen, not_rendered: !rendered, tiny, offscreen,
          w: Math.round(r.width), h: Math.round(r.height), src: el.src || null,
          srcdoc: el.hasAttribute('srcdoc'), sandbox: el.hasAttribute('sandbox')};
})"""


_ID_TOKEN = re.compile(r"(?<![A-Za-z0-9])(?=[A-Za-z0-9]*\d)[A-Za-z0-9]{8,}(?![A-Za-z0-9])")


def _redact_name(name: str) -> str:
    """Cookie names sometimes embed identifiers; alphanumeric tokens of 8+ chars containing a digit are redacted."""
    return _ID_TOKEN.sub("<redacted>", name)[:120]


def _scrub(obj, secrets_: list[str]):
    """Replace any occurrence of a cookie value inside saved strings."""
    if isinstance(obj, str):
        for v in secrets_:
            if v in obj:
                obj = obj.replace(v, "<redacted>")
        return obj
    if isinstance(obj, dict):
        return {k: _scrub(v, secrets_) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_scrub(v, secrets_) for v in obj]
    return obj


def _clean_msg(msg: str) -> str:
    first = (msg or "").strip().splitlines()[0] if msg else ""
    return re.sub(r"\?\S*", "?[query removed]", first)[:300]


# ----------------------------------------------------------------------------------------------
# Output store
# ----------------------------------------------------------------------------------------------
class OutputStore:
    def __init__(self, out_dir: Path, categories: list[str], ref_version: dict):
        self.dir = out_dir
        self.categories = categories
        self.ref_version = ref_version
        self.obs = out_dir / "website_observations.jsonl"
        self.req = out_dir / "request_observations.jsonl"
        self.cookies = out_dir / "cookie_metadata.jsonl"
        self.features = out_dir / "website_features.csv"
        self.trackers = out_dir / "tracker_matches.csv"
        self.manifest = out_dir / "crawl_manifest.json"
        self.log = out_dir / "crawl.log"
        self.lock = asyncio.Lock()

    # -- reading / repair --
    def load_records(self) -> dict[str, dict]:
        """website_observations.jsonl is the commit log: a website is done iff its record is here.
        A truncated trailing line (crash mid-write) is dropped."""
        records: dict[str, dict] = {}
        if not self.obs.exists():
            return records
        good_lines, dropped = [], 0
        for line in self.obs.read_text().splitlines():
            try:
                rec = json.loads(line)
                records[rec["website_id"]] = rec
                good_lines.append(line)
            except (json.JSONDecodeError, KeyError):
                dropped += 1
        if dropped or len(good_lines) != len(records):
            # keep the last record per website
            self._atomic_write(self.obs, "".join(json.dumps(r) + "\n" for r in records.values()))
            log.warning("repaired website_observations.jsonl", extra={"dropped_lines": dropped})
        return records

    def compact_evidence(self, done: set[str]) -> None:
        """Drop request/cookie lines from visits that never committed a website record."""
        for path in (self.req, self.cookies):
            if not path.exists():
                continue
            kept, removed = [], 0
            for line in path.read_text().splitlines():
                try:
                    if json.loads(line)["website_id"] in done:
                        kept.append(line)
                        continue
                except (json.JSONDecodeError, KeyError):
                    pass
                removed += 1
            if removed:
                self._atomic_write(path, "".join(l + "\n" for l in kept))
                log.info("compacted %s", path.name, extra={"removed_lines": removed})

    def rebuild_tables(self, records) -> None:
        """Regenerate both CSVs from the JSONL commit log (guarantees CSV/JSONL agreement)."""
        cols = csv_columns(self.categories)
        tmp = self.features.with_suffix(".csv.tmp")
        with open(tmp, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=cols)
            w.writeheader()
            for rec in records:
                w.writerow(_csv_row(compute_features(rec, self.categories)))
        tmp.replace(self.features)
        tmp = self.trackers.with_suffix(".csv.tmp")
        with open(tmp, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=TRACKER_CSV_COLUMNS)
            w.writeheader()
            for rec in records:
                w.writerows(self._tracker_rows(rec))
        tmp.replace(self.trackers)

    def _tracker_rows(self, rec: dict) -> list[dict]:
        rows = []
        site = (rec.get("final") or {}).get("registrable_domain")
        for h in (rec.get("tracker_summary") or {}).get("matched_hosts", []):
            rows.append(_csv_row({
                "website_id": rec["website_id"], "site_final_registrable_domain": site,
                "hostname": h["hostname"], "matched_tracker_domain": h["matched_tracker_domain"],
                "request_count": h["request_count"], "resource_types": ";".join(sorted(h["resource_types"])),
                "same_entity_as_site": h["same_entity_as_site"], "owner_name": h.get("owner_name"),
                "owner_display_name": h.get("owner_display_name"), "owned_by": h.get("owned_by"),
                "categories": ";".join(h.get("categories") or []),
                "categories_available": h.get("categories_available"),
                "fingerprinting_metadata_available": h.get("fingerprinting_metadata_available"),
                "fingerprinting_score": h.get("fingerprinting_score"),
                "cookies_prevalence": h.get("cookies_prevalence"), "prevalence": h.get("prevalence"),
                "default_action": h.get("default_action"), "reference_source": self.ref_version["source"],
                "reference_sha256": self.ref_version["sha256"],
                "reference_retrieved_at": self.ref_version["retrieved_at"],
            }))
        return rows

    # -- writing --
    @staticmethod
    def _atomic_write(path: Path, text: str) -> None:
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(text)
        tmp.replace(path)

    @staticmethod
    def _append(path: Path, text: str) -> None:
        if not text:
            return
        with open(path, "a") as f:
            f.write(text)
            f.flush()
            os.fsync(f.fileno())

    async def commit(self, rec: dict, requests: list[dict], cookies: list[dict]) -> None:
        async with self.lock:
            # evidence first, the website record last (the record is the commit marker)
            self._append(self.req, "".join(json.dumps(r) + "\n" for r in requests))
            self._append(self.cookies, "".join(json.dumps(c) + "\n" for c in cookies))
            self._append(self.obs, json.dumps(rec) + "\n")
            with open(self.features, "a", newline="") as f:
                csv.DictWriter(f, fieldnames=csv_columns(self.categories)).writerow(
                    _csv_row(compute_features(rec, self.categories)))
            rows = self._tracker_rows(rec)
            if rows:
                with open(self.trackers, "a", newline="") as f:
                    csv.DictWriter(f, fieldnames=TRACKER_CSV_COLUMNS).writerows(rows)

    def write_manifest(self, manifest: dict) -> None:
        manifest["updated_at"] = utcnow()
        self._atomic_write(self.manifest, json.dumps(manifest, indent=2))


def _csv_row(row: dict) -> dict:
    out = {}
    for k, v in row.items():
        if v is None:
            out[k] = ""
        elif isinstance(v, bool):
            out[k] = int(v)
        else:
            out[k] = v
    return out


def status_counts(manifest: dict, records: dict[str, dict]) -> dict:
    c = Counter(r["crawl"]["status"] for r in records.values())
    selected = len(manifest["selected"])
    attempted = len(records)
    return {
        "selected": selected,
        "attempted": attempted,
        "completed_observed": c["success"] + c["http_error"],
        "success": c["success"],
        "http_error": c["http_error"],
        "failed": c["failed"],
        "blocked_unsafe": c["blocked_unsafe"],
        "pending": selected - attempted,
        "complete": attempted == selected,
    }


# ----------------------------------------------------------------------------------------------
# One navigation attempt
# ----------------------------------------------------------------------------------------------
class AttemptResult:
    def __init__(self, url: str):
        self.url = url
        self.ok = False
        self.error_class: str | None = None
        self.error: str | None = None
        self.retry_after: float | None = None
        self.started_at = utcnow()
        self.data: dict = {}

    def summary(self) -> dict:
        return {"url": sanitize_url(self.url)["url"], "started_at": self.started_at, "ok": self.ok,
                "error_class": self.error_class, "error": self.error,
                "http_status": self.data.get("http_status"),
                "duration_seconds": self.data.get("attempt_seconds")}


class Crawler:
    def __init__(self, cfg: CrawlConfig, ref: TrackerReference, store: OutputStore,
                 secret_audit: Path | None = None):
        self.cfg = cfg
        self.ref = ref
        self.store = store
        self.secret_audit = secret_audit
        self.key = "__ovael_" + secrets.token_hex(6)
        self.binding = "__ovaelReport_" + secrets.token_hex(6)
        src = (config.PACKAGE_DIR / "instrumentation.js").read_text()
        self.instr_src = (src.replace("__KEY__", self.key).replace("__BINDING__", self.binding)
                          .replace("__MAX_EVENTS__", str(cfg.max_evidence_events)))
        self.browser = None
        self._pw = None
        self._browser_lock = asyncio.Lock()
        self.stop_event = asyncio.Event()
        self.stop_reason: str | None = None
        self.consecutive_5xx = 0
        self.requeued: Counter = Counter()

    async def get_browser(self):
        async with self._browser_lock:
            if self.browser is None or not self.browser.is_connected():
                if self.browser is not None:
                    log.warning("browser disconnected; relaunching")
                self.browser = await self._pw.chromium.launch(headless=self.cfg.headless,
                                                              args=self.cfg.launch_args)
            return self.browser

    # ------------------------------------------------------------------------------------------
    async def attempt(self, entry: dict, url: str) -> AttemptResult:
        cfg, res = self.cfg, AttemptResult(url)
        t_attempt = time.monotonic()
        proxy = SafetyProxy()
        await proxy.start()
        browser = await self.get_browser()
        context = None
        try:
            context = await browser.new_context(
                proxy={"server": proxy.url}, service_workers="block", accept_downloads=False,
                viewport={"width": cfg.viewport_width, "height": cfg.viewport_height}, locale=cfg.locale)
            docs: dict[str, dict] = {}

            def on_report(source, snap):
                if isinstance(snap, dict) and isinstance(snap.get("doc_id"), str):
                    docs[snap["doc_id"]] = snap
            await context.expose_binding(self.binding, on_report)
            await context.add_init_script(script=self.instr_src)
            page = await context.new_page()
            t0 = time.monotonic()
            reqs: list[dict] = []
            by_req: dict = {}
            main_navs: list[str] = []
            popups = [0]
            downloads = [0]

            def on_request(rq):
                try:
                    fr = rq.frame
                    kind = "main" if fr == page.main_frame else ("subframe" if fr.page == page else "other_page")
                except Exception:
                    kind = "unknown"
                s = sanitize_url(rq.url, cfg.max_path_chars)
                prev = by_req.get(rq.redirected_from) if rq.redirected_from is not None else None
                d = {"seq": len(reqs), "url": s["url"], "scheme": s["scheme"], "hostname": s["hostname"],
                     "query_param_count": s["query_param_count"], "method": rq.method,
                     "resource_type": rq.resource_type, "is_navigation_request": rq.is_navigation_request(),
                     "frame": kind, "redirected_from_seq": prev["seq"] if prev else None,
                     "t_offset_s": round(time.monotonic() - t0, 3), "status": None, "failed": False,
                     "failure": None, "content_type": None}
                reqs.append(d)
                by_req[rq] = d

            def on_response(rs):
                d = by_req.get(rs.request)
                if d is not None:
                    d["status"] = rs.status
                    ct = rs.headers.get("content-type")
                    d["content_type"] = ct.split(";")[0].strip()[:80] if ct else None

            def on_failed(rq):
                d = by_req.get(rq)
                if d is not None:
                    d["failed"] = True
                    d["failure"] = _clean_msg(rq.failure or "")

            def on_nav(fr):
                if fr == page.main_frame:
                    main_navs.append(fr.url)

            context.on("request", on_request)
            context.on("response", on_response)
            context.on("requestfailed", on_failed)
            context.on("page", lambda p: popups.__setitem__(0, popups[0] + 1))
            page.on("framenavigated", on_nav)
            page.on("download", lambda d: downloads.__setitem__(0, downloads[0] + 1))

            resp, nav_note = None, None
            try:
                resp = await page.goto(url, wait_until="domcontentloaded", timeout=cfg.navigation_timeout_s * 1000)
            except PlaywrightTimeout as e:
                res.error_class, res.error = "timeout", _clean_msg(str(e))
            except PlaywrightError as e:
                msg = str(e)
                if "interrupted by another navigation" in msg and page.url.startswith("http"):
                    nav_note = "interrupted_by_client_navigation"
                else:
                    res.error_class, res.error = self._classify(msg, proxy, reqs), _clean_msg(msg)
            nav_seconds = round(time.monotonic() - t0, 3)

            if res.error_class:
                if proxy.blocked:
                    res.error_class = "blocked_unsafe" if self._nav_blocked(proxy, reqs) else res.error_class
                res.data = {"attempt_seconds": round(time.monotonic() - t_attempt, 3),
                            "blocked": proxy.blocked[:]}
                return res

            status = resp.status if resp else _last_main_doc_status(reqs)
            if status in (429, 503):
                res.error_class, res.error = f"http_{status}", f"HTTP {status} on main document"
                ra = resp.headers.get("retry-after") if resp else None
                if ra and ra.strip().isdigit():
                    res.retry_after = min(float(ra), cfg.max_retry_after_s)
                res.data["http_status"] = status
                res.data["fallback_observation_possible"] = True
                # observe anyway so the final record can keep the response if retries run out
            load_fired = True
            try:
                await page.wait_for_load_state("load", timeout=cfg.load_event_timeout_s * 1000)
            except PlaywrightError:
                load_fired = False
            await asyncio.sleep(cfg.settle_s)

            res.data.update(await self._collect(entry, context, page, resp, reqs, by_req, main_navs, docs))
            res.data.update({"http_status": status, "navigation_seconds": nav_seconds,
                             "load_event_fired": load_fired, "nav_note": nav_note,
                             "popups": popups[0], "downloads_blocked": downloads[0],
                             "blocked": proxy.blocked[:],
                             "attempt_seconds": round(time.monotonic() - t_attempt, 3)})
            if not res.error_class:
                res.ok = True
            return res
        finally:
            if context is not None:
                try:
                    await asyncio.wait_for(context.close(), 15)
                except Exception:
                    pass
            await proxy.stop()

    @staticmethod
    def _nav_blocked(proxy: SafetyProxy, reqs: list[dict]) -> bool:
        blocked_hosts = {b["host"] for b in proxy.blocked}
        return any(r["frame"] == "main" and r["resource_type"] == "document" and r["hostname"] in blocked_hosts
                   for r in reqs) or not reqs

    @staticmethod
    def _classify(msg: str, proxy: SafetyProxy, reqs: list[dict]) -> str:
        if "Download is starting" in msg:
            return "download_blocked"
        if any(s in msg for s in ("ERR_TUNNEL_CONNECTION_FAILED", "ERR_EMPTY_RESPONSE", "ERR_PROXY")):
            host = hostname_of(msg.split(" at ")[-1].split()[0]) if " at " in msg else ""
            nav_hosts = [r["hostname"] for r in reqs if r["frame"] == "main" and r["resource_type"] == "document"]
            ev = proxy.last_event_for(nav_hosts[-1] if nav_hosts else host)
            if ev and ev["decision"] != "allowed":
                return {"non_public_address": "blocked_unsafe", "non_public_hostname": "blocked_unsafe",
                        "dns_failure": "dns_failure", "dns_timeout": "dns_timeout",
                        "connect_refused": "connect_refused", "connect_timeout": "connect_timeout",
                        }.get(ev["reason"], "connect_failed")
            return "connection_error"
        if "ERR_TIMED_OUT" in msg or "Timeout" in msg:
            return "timeout"
        if "ERR_NAME_NOT_RESOLVED" in msg:
            return "dns_failure"
        if "ERR_CONNECTION_REFUSED" in msg:
            return "connect_refused"
        if "ERR_CERT" in msg or "ERR_SSL" in msg or "ERR_BAD_SSL" in msg:
            return "tls_error"
        if any(s in msg for s in ("ERR_CONNECTION_RESET", "ERR_CONNECTION_CLOSED", "ERR_HTTP2",
                                   "ERR_CONNECTION_ABORTED", "ERR_NETWORK_CHANGED", "ERR_QUIC")):
            return "connection_error"
        if "ERR_TOO_MANY_REDIRECTS" in msg:
            return "too_many_redirects"
        if "ERR_ABORTED" in msg:
            return "aborted"
        if "ERR_BLOCKED_BY" in msg:
            return "blocked_by_browser_or_response"
        if "has been closed" in msg or "Target crashed" in msg:
            return "browser_error"
        return "other_error"

    async def _collect(self, entry, context, page, resp, reqs, by_req, main_navs, docs) -> dict:
        final_url = page.url
        final_host = hostname_of(final_url)
        site = registrable_or_host(final_host) if final_host else entry["initial_registrable_domain"]
        try:
            title = await asyncio.wait_for(page.title(), 5)
        except Exception:
            title = None

        # --- redirect chain ---
        chain = []
        rq = resp.request if resp else None
        while rq is not None:
            d = by_req.get(rq)
            chain.append({"url": sanitize_url(rq.url)["url"], "status": d["status"] if d else None})
            rq = rq.redirected_from
        chain.reverse()
        navs = [u for u in main_navs if u.startswith("http")]
        changes = sum(1 for a, b in zip(navs, navs[1:]) if a.split("#")[0] != b.split("#")[0])

        # --- frames ---
        main = page.main_frame
        main_origin = origin_of(main.url)
        children = [f for f in page.frames if f != main]
        frame_list = []
        for f in children:
            o = origin_of(f.url)
            frame_list.append({"url": sanitize_url(f.url)["url"], "origin": o,
                               "cross_origin": bool(o and o != main_origin)})
        try:
            page_stats = await asyncio.wait_for(page.evaluate(DOM_STATS_JS), 5)
        except Exception:
            page_stats = None
        dom = None
        try:
            dom = await asyncio.wait_for(page.evaluate(DOM_IFRAMES_JS), 5)
            for el in dom:
                el["src"] = sanitize_url(el["src"])["url"] if el.get("src") else None
        except Exception:
            dom = None

        # --- instrumentation: live documents (authoritative) + reports from replaced documents ---
        main_snapshot = None
        frames_eval_ok = 0
        getter = f"() => {{ const s = window['{self.key}']; return typeof s === 'function' ? s() : null; }}"
        for f in page.frames:
            try:
                snap = await asyncio.wait_for(f.evaluate(getter), 3)
            except Exception:
                continue
            if isinstance(snap, dict) and snap.get("doc_id"):
                frames_eval_ok += 1
                docs[snap["doc_id"]] = snap
                if f == main:
                    main_snapshot = snap
        totals: Counter = Counter()
        evidence = []
        for snap in docs.values():
            totals.update({k: int(v) for k, v in (snap.get("counts") or {}).items() if isinstance(v, (int, float))})
            for ev in snap.get("events") or []:
                if len(evidence) < 100:
                    evidence.append({**ev, "document_origin": snap.get("origin"), "is_top": snap.get("is_top")})
        instrumentation = {
            "status": "ok" if main_snapshot else "main_frame_unavailable",
            "documents": len(docs),
            "live_frames": len(page.frames),
            "live_frames_read": frames_eval_ok,
            "counts_all_documents": dict(totals),
            "counts_main_document": (main_snapshot or {}).get("counts"),
            "hooked_apis": (main_snapshot or {}).get("hooked"),
            "unavailable_apis": (main_snapshot or {}).get("failed"),
            "evidence_events": evidence,
        }

        # --- cookies ---
        crawl_epoch = time.time()
        raw = await context.cookies()
        cookies = []
        for c in raw:
            dom_c = (c.get("domain") or "").lstrip(".")
            regd = registrable_domain(dom_c) or (dom_c or None)
            party = "unattributed" if not regd else ("first" if regd == site else "third")
            exp = c.get("expires")
            session = exp is None or exp < 0
            cookies.append({
                "name": _redact_name(c.get("name") or ""), "domain": c.get("domain"), "host_only": not (c.get("domain") or "").startswith("."),
                "path": c.get("path"), "session": session,
                "expires_utc": None if session else datetime.fromtimestamp(exp, timezone.utc).isoformat(timespec="seconds"),
                "lifetime_days": None if session else round((exp - crawl_epoch) / 86400, 3),
                "secure": bool(c.get("secure")), "http_only": bool(c.get("httpOnly")),
                "same_site": c.get("sameSite"), "party": party, "cookie_registrable_domain": regd,
                "partitioned": bool(c.get("partitionKey")) if "partitionKey" in c else None,
            })
            if self.secret_audit and c.get("value") and len(c["value"]) >= 6:
                with open(self.secret_audit, "a") as f:  # smoke-test only, outside the output dir
                    f.write(c["value"] + "\n")
        return {"final_url": final_url, "final_host": final_host, "site": site, "title": title,
                "chain": chain, "main_navs": [sanitize_url(u)["url"] for u in navs],
                "client_side_url_changes": changes, "frames": frame_list, "dom_iframes": dom, "page_stats": page_stats,
                "instrumentation": instrumentation, "cookies": cookies, "requests": reqs,
                # in memory only: used to scrub saved strings, never written
                "secret_values": sorted({c["value"] for c in raw if len(c.get("value") or "") >= 8},
                                        key=len, reverse=True)}

    # ------------------------------------------------------------------------------------------
    async def visit(self, entry: dict, attempts: list[AttemptResult]) -> AttemptResult | None:
        """Try candidate URLs (https, https://www., http) with retries for transient errors."""
        last = None
        for url in entry["candidate_urls"]:
            retries = 0
            while True:
                res = await self.attempt(entry, url)
                attempts.append(res)
                last = res
                if res.ok or res.error_class == "blocked_unsafe":
                    return res
                if res.error_class in TRANSIENT and retries < self.cfg.max_retries:
                    delay = res.retry_after or self.cfg.backoff_base_s * (2 ** retries)
                    retries += 1
                    await asyncio.sleep(delay)
                    continue
                if res.error_class in UNREACHABLE:
                    break  # next candidate URL
                return res
        return last

    def build_record(self, entry: dict, attempts: list[AttemptResult], final: AttemptResult | None,
                     overall_timeout: bool) -> tuple[dict, list[dict], list[dict]]:
        wid = entry["website_id"]
        blocked = [b for a in attempts for b in a.data.get("blocked", [])]
        observed = final is not None and (final.ok or (final.error_class in ("http_429", "http_503")
                                                         and "requests" in final.data))
        rec = {
            "schema_version": SCHEMA_VERSION, "website_id": wid, "tranco_rank": entry.get("tranco_rank"),
            "original_domain": entry["original_domain"], "original_url": entry["original_url"],
            "initial_hostname": entry["original_domain"],
            "initial_registrable_domain": entry["initial_registrable_domain"],
            "crawl": {
                "status": None, "navigation_outcome": None, "failure_reason": None,
                "crawl_timestamp": attempts[-1].started_at if attempts else utcnow(),
                "finished_at": utcnow(), "attempts": [a.summary() for a in attempts],
                "overall_timeout": overall_timeout,
                "navigation_duration_seconds": None, "settle_seconds": self.cfg.settle_s,
            },
            "safety": {"blocked_destinations": [{"host": b["host"], "port": b["port"], "reason": b["reason"]}
                                                for b in blocked]},
            "labels": {"tracker_reference_flag_source": self.ref.version["source"], "security_label": None,
                       "manual_review_label": None, "label_source": None, "label_confidence": None,
                       "labeled_at": None,
                       "note": "No ground-truth labels. Tracker-list matches are observations, not labels."},
        }
        if not observed:
            if overall_timeout:
                cls, err = "overall_timeout", f"visit exceeded overall_timeout_s={self.cfg.overall_timeout_s}"
            elif final is None:
                cls, err = "not_attempted", "no attempt completed"
            else:
                cls, err = final.error_class, final.error
            rec["crawl"].update(status="blocked_unsafe" if cls == "blocked_unsafe" else "failed",
                                navigation_outcome=cls, failure_reason=err)
            rec["final"] = {"http_status": final.data.get("http_status") if final else None}
            rec["instrumentation"] = {"status": "not_run"}
            return rec, [], []

        d = final.data
        status = d["http_status"]
        rec["crawl"].update(
            status="http_error" if status is not None and status >= 400 else "success",
            navigation_outcome="load_event" if d["load_event_fired"] else "dom_content_loaded_only",
            failure_reason=final.error if not final.ok else None,
            navigation_duration_seconds=d["navigation_seconds"], navigation_note=d.get("nav_note"))
        site = d["site"]
        rec["final"] = {"url": sanitize_url(d["final_url"])["url"], "hostname": d["final_host"],
                        "registrable_domain": site, "title": (d["title"] or None) and d["title"][:300],
                        "http_status": status}

        requests = d["requests"]
        host_stats: dict[str, dict] = defaultdict(lambda: {"count": 0, "types": set()})
        for q in requests:
            q["website_id"] = wid
            if q["scheme"] in ("http", "https") and q["hostname"]:
                q["registrable_domain"] = registrable_or_host(q["hostname"])
                q["party"] = "first" if q["registrable_domain"] == site else "third"
                m = self.ref.match(q["hostname"])
                q["tracker_match_status"] = m["match_status"]
                q["matched_tracker_domain"] = m["matched_tracker_domain"]
                if q["party"] == "third":
                    hs = host_stats[q["hostname"]]
                    hs["count"] += 1
                    hs["types"].add(q["resource_type"])
            else:
                q["registrable_domain"] = q["party"] = q["tracker_match_status"] = q["matched_tracker_domain"] = None
        rec["request_summary"] = summarize_requests(requests)

        matched_hosts, tp_hosts, by_cat = [], [], Counter()
        tracker_reqs = same_entity_reqs = 0
        tracker_domains = set()
        for host, hs in sorted(host_stats.items()):
            m = self.ref.match(host)
            same = self.ref.same_entity(host, d["final_host"])
            tp_hosts.append({"hostname": host, "registrable_domain": registrable_or_host(host),
                             "request_count": hs["count"], "match_status": m["match_status"],
                             "matched_tracker_domain": m["matched_tracker_domain"], "entity": m.get("entity")})
            if m["match_status"] == "matched":
                tracker_reqs += hs["count"]
                tracker_domains.add(m["matched_tracker_domain"])
                if same:
                    same_entity_reqs += hs["count"]
                for cat in m["categories"]:
                    by_cat[cat] += hs["count"]
                matched_hosts.append({"hostname": host, "request_count": hs["count"],
                                      "resource_types": sorted(hs["types"]), "same_entity_as_site": same,
                                      **{k: v for k, v in m.items() if k not in ("match_status", "entity")}})
        rec["tracker_summary"] = {
            "reference": self.ref.version["source"], "reference_sha256": self.ref.version["sha256"],
            "tracker_matched_requests": tracker_reqs, "unique_tracker_domains": len(tracker_domains),
            "same_entity_tracker_requests": same_entity_reqs,
            "first_party_tracker_list_requests": sum(1 for q in requests if q.get("party") == "first"
                                                      and q.get("tracker_match_status") == "matched"),
            "requests_by_category": dict(by_cat),
            "third_party_hostnames_not_in_reference": sum(1 for h in tp_hosts if h["match_status"] != "matched"),
            "matched_hosts": matched_hosts, "third_party_hosts": tp_hosts,
        }

        cookies = d["cookies"]
        for c in cookies:
            c["website_id"] = wid
        lifetimes = [c["lifetime_days"] for c in cookies if c["lifetime_days"] is not None]
        rec["cookie_summary"] = {
            "observation": "context.cookies() once, after the settle period; cookies set and removed earlier are not seen",
            "total_cookies": len(cookies),
            "first_party_cookies": sum(c["party"] == "first" for c in cookies),
            "third_party_cookies": sum(c["party"] == "third" for c in cookies),
            "unattributed_cookies": sum(c["party"] == "unattributed" for c in cookies),
            "secure_cookies": sum(c["secure"] for c in cookies),
            "httponly_cookies": sum(c["http_only"] for c in cookies),
            "session_cookies": sum(c["session"] for c in cookies),
            "samesite_none_cookies": sum(c["same_site"] == "None" for c in cookies),
            "max_cookie_lifetime_days": max(lifetimes) if lifetimes else None,
            "third_party_cookie_domains": sorted({c["cookie_registrable_domain"] for c in cookies if c["party"] == "third"}),
        }
        rec["navigation"] = {
            "http_redirect_chain": d["chain"], "redirect_count": max(len(d["chain"]) - 1, 0),
            "main_frame_navigations": d["main_navs"], "client_side_url_changes": d["client_side_url_changes"],
            "cross_domain_redirect": bool(site and entry["initial_registrable_domain"]
                                          and site != entry["initial_registrable_domain"]),
            "load_event_fired": d["load_event_fired"], "popups_opened": d["popups"],
            "downloads_blocked": d["downloads_blocked"],
            "failed_navigation_attempts": [a.summary() for a in attempts if not a.ok],
        }
        ps = d.get("page_stats")
        rec["page"] = {"dom_available": ps is not None,
                       "dom_element_count": ps["elements"] if ps else None,
                       "visible_text_length": ps["text"] if ps else None}
        dom = d["dom_iframes"]
        rec["frames"] = {
            "iframe_count": len(d["frames"]),
            "cross_origin_iframe_count": sum(f["cross_origin"] for f in d["frames"]),
            "frames": d["frames"][:100],
            "dom_available": dom is not None,
            "dom_iframe_count": len(dom) if dom is not None else None,
            "hidden_iframe_count": sum(el["hidden"] for el in dom) if dom is not None else None,
            "dom_iframes": dom[:100] if dom is not None else None,
            "hidden_criterion": "checkVisibility({opacityProperty, visibilityProperty}) is false, OR content-box "
                                "width<=1px OR height<=1px (clientWidth/clientHeight), OR bounding box entirely at negative coordinates",
        }
        rec["instrumentation"] = d["instrumentation"]
        sv = d.pop("secret_values", [])
        if sv:
            rec, requests, cookies = _scrub(rec, sv), _scrub(requests, sv), _scrub(cookies, sv)
        return rec, requests, cookies

    # ------------------------------------------------------------------------------------------
    async def worker(self, n: int, queue: asyncio.Queue, manifest: dict, records: dict, total: int):
        while not self.stop_event.is_set():
            try:
                entry = queue.get_nowait()
            except asyncio.QueueEmpty:
                return
            attempts: list[AttemptResult] = []
            t = time.monotonic()
            timed_out = False
            final = None
            try:
                final = await asyncio.wait_for(self.visit(entry, attempts), self.cfg.overall_timeout_s)
            except asyncio.TimeoutError:
                timed_out = True
            except asyncio.CancelledError:
                raise
            except Exception as e:  # never let one site crash the run
                log.exception("unexpected error visiting %s", entry["original_domain"])
                bad = AttemptResult(entry["original_url"])
                bad.error_class, bad.error = "crawler_exception", _clean_msg(repr(e))
                attempts.append(bad)
                final = bad
                if (self.browser is None or not self.browser.is_connected()) and \
                        self.requeued[entry["website_id"]] < 1:
                    # browser died: retry the site once after the relaunch
                    self.requeued[entry["website_id"]] += 1
                    await queue.put(entry)
                    continue
            rec, reqs, cookies = self.build_record(entry, attempts, final, timed_out)
            st = rec["crawl"]["status"]
            if st == "failed" and not await connectivity_ok():
                self.stop_reason = "connectivity lost: probe of public resolvers failed; site left pending"
                log.error(self.stop_reason, extra={"website_id": entry["website_id"]})
                self.stop_event.set()
                return
            await self.store.commit(rec, reqs, cookies)
            records[rec["website_id"]] = rec
            hs = rec["final"].get("http_status")
            self.consecutive_5xx = self.consecutive_5xx + 1 if hs and hs >= 500 else 0
            if self.consecutive_5xx >= self.cfg.max_consecutive_server_errors:
                self.stop_reason = f"{self.consecutive_5xx} consecutive websites returned HTTP 5xx"
                self.stop_event.set()
            manifest["status"] = status_counts(manifest, records)
            self.store.write_manifest(manifest)
            done = len(records)
            rs = rec.get("request_summary") or {}
            ts = rec.get("tracker_summary") or {}
            log.info("site_done", extra={
                "website_id": rec["website_id"], "domain": entry["original_domain"], "status": st,
                "outcome": rec["crawl"]["navigation_outcome"], "requests": rs.get("total_requests"),
                "trackers": ts.get("tracker_matched_requests"), "seconds": round(time.monotonic() - t, 1),
                "progress": f"{done}/{total}"})
            await asyncio.sleep(self.cfg.inter_site_delay_s)


async def connectivity_ok() -> bool:
    for host in ("1.1.1.1", "8.8.8.8", "9.9.9.9"):
        try:
            _, w = await asyncio.wait_for(asyncio.open_connection(host, 443), 5)
            w.close()
            return True
        except (OSError, asyncio.TimeoutError):
            continue
    return False


# ----------------------------------------------------------------------------------------------
class JsonFormatter(logging.Formatter):
    STD = set(vars(logging.makeLogRecord({})).keys()) | {"message", "asctime"}

    def format(self, record):
        d = {"ts": datetime.fromtimestamp(record.created, timezone.utc).isoformat(timespec="seconds"),
             "level": record.levelname, "event": record.getMessage()}
        d.update({k: v for k, v in vars(record).items() if k not in self.STD})
        if record.exc_info:
            d["exc"] = self.formatException(record.exc_info)
        return json.dumps(d, default=str)


class ConsoleFormatter(logging.Formatter):
    def format(self, record):
        x = vars(record)
        if record.getMessage() == "site_done":
            return (f"[{x['progress']:>9}] {x['status']:<14} {x['domain']:<32} "
                    f"req={x['requests'] if x['requests'] is not None else '-':<5} "
                    f"trackers={x['trackers'] if x['trackers'] is not None else '-':<4} "
                    f"{x['outcome']} ({x['seconds']}s)")
        return f"{record.levelname}: {record.getMessage()}"


def setup_logging(log_path: Path) -> None:
    root = logging.getLogger("ovael")
    root.setLevel(logging.INFO)
    root.handlers.clear()
    fh = logging.FileHandler(log_path)
    fh.setFormatter(JsonFormatter())
    sh = logging.StreamHandler(sys.stdout)
    sh.setFormatter(ConsoleFormatter())
    root.addHandler(fh)
    root.addHandler(sh)


async def run_crawl(out_dir: Path, cfg: CrawlConfig, limit: int | None = None,
                    secret_audit: Path | None = None) -> dict:
    ref = TrackerReference()
    store = OutputStore(out_dir, ref.categories, ref.version)
    setup_logging(store.log)
    if not store.manifest.exists():
        raise SystemExit(f"{store.manifest} not found - run the 'select' (or 'smoke') command first")
    manifest = json.loads(store.manifest.read_text())
    if manifest.get("reference", {}).get("sha256") not in (None, ref.version["sha256"]):
        log.warning("tracker reference changed since the run started; matches are recomputed per record "
                    "with the current list - see manifest.reference_history")
        manifest.setdefault("reference_history", []).append(manifest["reference"])
    manifest["reference"] = ref.version
    records = store.load_records()
    store.compact_evidence(set(records))
    store.rebuild_tables(records.values())
    pending = [e for e in manifest["selected"] if e["website_id"] not in records]
    if limit is not None:
        pending = pending[:limit]
    run_info = {"started_at": utcnow(), "pending_at_start": len(manifest["selected"]) - len(records),
                "scheduled": len(pending), "config": cfg.to_dict()}
    manifest["crawl_config"] = cfg.to_dict()
    manifest.setdefault("runs", []).append(run_info)
    manifest["status"] = status_counts(manifest, records)
    store.write_manifest(manifest)
    log.info(f"resuming: {len(records)} recorded, {len(pending)} scheduled this run "
             f"({run_info['pending_at_start']} pending in total)")
    if not pending:
        run_info["finished_at"] = utcnow()
        store.write_manifest(manifest)
        return manifest["status"]

    crawler = Crawler(cfg, ref, store, secret_audit)
    queue: asyncio.Queue = asyncio.Queue()
    for e in pending:
        queue.put_nowait(e)
    loop = asyncio.get_running_loop()
    tasks: list[asyncio.Task] = []

    def on_signal():
        if not crawler.stop_event.is_set():
            crawler.stop_reason = "interrupted by signal; in-flight websites left pending"
            log.warning(crawler.stop_reason)
            crawler.stop_event.set()
            for t in tasks:
                t.cancel()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, on_signal)

    async with async_playwright() as pw:
        crawler._pw = pw
        browser = await crawler.get_browser()
        manifest["environment"] = {"python": sys.version.split()[0], "platform": platform.platform(),
                                   "playwright": _pkg_version("playwright"), "browser": "chromium",
                                   "browser_version": browser.version, "headless": cfg.headless,
                                   "user_agent": "Playwright Chromium default (headless)"}
        total = len(manifest["selected"])
        tasks.extend(asyncio.create_task(crawler.worker(i, queue, manifest, records, total))
                     for i in range(cfg.workers))
        await asyncio.gather(*tasks, return_exceptions=True)
        try:
            await asyncio.wait_for(crawler.browser.close(), 20)
        except Exception:
            pass
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.remove_signal_handler(sig)

    store.compact_evidence(set(records))
    store.rebuild_tables(records.values())
    run_info["finished_at"] = utcnow()
    run_info["stop_reason"] = crawler.stop_reason or ("completed" if queue.empty() else "limit reached")
    manifest["status"] = status_counts(manifest, records)
    store.write_manifest(manifest)
    s = manifest["status"]
    log.info(f"run finished ({run_info['stop_reason']}): selected={s['selected']} attempted={s['attempted']} "
             f"success={s['success']} http_error={s['http_error']} failed={s['failed']} "
             f"blocked_unsafe={s['blocked_unsafe']} pending={s['pending']}")
    return s


def _pkg_version(name: str) -> str | None:
    try:
        from importlib.metadata import version
        return version(name)
    except Exception:
        return None
