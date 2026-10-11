"""Single source of truth for the website_features.csv schema and feature computation.

Missing-value convention (applies to every numeric field):
  * an empty cell / null means "not measured" (visit failed, or the instrumentation that produces
    the field did not return data). It is NEVER silently replaced by 0.
  * 0 means "measured, and nothing was observed during the observation window".
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass

from .reference import slug

NA_FAILED = "empty when crawl_status is failed/blocked_unsafe (no page was observed)"
NA_INSTR = NA_FAILED + "; also empty when the main-frame instrumentation snapshot could not be read"
NA_DOM = NA_FAILED + "; also empty when the top-document DOM could not be evaluated"


@dataclass(frozen=True)
class Field:
    name: str
    dtype: str
    group: str
    description: str
    missing: str = NA_FAILED


FIELDS: list[Field] = [
    # --- identification / crawl metadata -------------------------------------------------------
    Field("website_id", "string", "metadata", "Stable identifier: T<rank> for Tranco sites, S<n> for smoke-test entries.", "never empty"),
    Field("tranco_rank", "integer", "metadata", "Rank in the source Tranco list (empty for smoke-test entries).", "empty for non-Tranco entries"),
    Field("original_domain", "string", "metadata", "Hostname as listed in the source list.", "never empty"),
    Field("original_url", "string", "metadata", "First URL attempted (https://<domain>/ unless a full URL was supplied).", "never empty"),
    Field("initial_registrable_domain", "string", "metadata", "eTLD+1 of the listed hostname (Public Suffix List).", "empty if the host is an IP literal"),
    Field("final_url", "string", "metadata", "Final main-frame URL after redirects, with query string and fragment removed.", NA_FAILED),
    Field("final_hostname", "string", "metadata", "Hostname of final_url.", NA_FAILED),
    Field("final_registrable_domain", "string", "metadata", "eTLD+1 of final_hostname; first/third-party attribution is relative to this.", NA_FAILED),
    Field("page_title", "string", "metadata", "document.title at observation time.", "empty if failed or the page has no title"),
    Field("dom_element_count", "integer", "metadata", "Elements in the top-level document at observation time (helps identify blank/challenge pages).", NA_DOM),
    Field("visible_text_length", "integer", "metadata", "Length of document.body.innerText at observation time.", NA_DOM),
    Field("crawl_status", "category", "metadata", "success | http_error (main document HTTP status >= 400; page still observed) | failed (no page) | blocked_unsafe (destination resolved to a non-public address).", "never empty"),
    Field("navigation_outcome", "category", "metadata", "load_event | dom_content_loaded_only (load event did not fire within the limit) | error class for failures.", "never empty"),
    Field("failure_reason", "string", "metadata", "Error message / class for failed visits (sanitised).", "empty for observed pages"),
    Field("http_status", "integer", "metadata", "HTTP status of the final main-document response.", "empty if no response was received"),
    Field("attempt_count", "integer", "metadata", "Number of navigation attempts made (retries + scheme/host fallbacks).", "never empty"),
    Field("retries", "integer", "metadata", "attempt_count - 1.", "never empty"),
    Field("crawl_timestamp", "datetime", "metadata", "UTC ISO-8601 time the final attempt started.", "never empty"),
    Field("instrumentation_status", "category", "metadata", "ok | main_frame_unavailable | not_run (page not observed).", "never empty"),
    # --- network requests ----------------------------------------------------------------------
    Field("total_requests", "integer", "requests", "HTTP(S) requests observed by Playwright request events during the visit (each redirect hop counts).", NA_FAILED),
    Field("successful_requests", "integer", "requests", "Requests that received a response with status < 400 and did not fail.", NA_FAILED),
    Field("failed_requests", "integer", "requests", "Requests that emitted requestfailed (network error, abort, blocked by safety proxy).", NA_FAILED),
    Field("http_error_requests", "integer", "requests", "Requests whose response status was >= 400.", NA_FAILED),
    Field("first_party_requests", "integer", "requests", "Requests whose registrable domain equals final_registrable_domain.", NA_FAILED),
    Field("third_party_requests", "integer", "requests", "Requests whose registrable domain differs from final_registrable_domain.", NA_FAILED),
    Field("unique_request_hostnames", "integer", "requests", "Distinct request hostnames.", NA_FAILED),
    Field("unique_request_domains", "integer", "requests", "Distinct request registrable domains.", NA_FAILED),
    Field("unique_third_party_domains", "integer", "requests", "Distinct third-party registrable domains.", NA_FAILED),
    Field("document_requests", "integer", "requests", "resource_type == document (main frame + iframes).", NA_FAILED),
    Field("script_requests", "integer", "requests", "resource_type == script.", NA_FAILED),
    Field("image_requests", "integer", "requests", "resource_type == image.", NA_FAILED),
    Field("stylesheet_requests", "integer", "requests", "resource_type == stylesheet.", NA_FAILED),
    Field("xhr_fetch_requests", "integer", "requests", "resource_type in {xhr, fetch}.", NA_FAILED),
    Field("font_requests", "integer", "requests", "resource_type == font.", NA_FAILED),
    Field("media_requests", "integer", "requests", "resource_type == media.", NA_FAILED),
    Field("websocket_requests", "integer", "requests", "resource_type == websocket.", NA_FAILED),
    Field("other_requests", "integer", "requests", "Any other resource_type (ping, beacon, manifest, texttrack, eventsource, other ...).", NA_FAILED),
    Field("iframe_requests", "integer", "requests", "Document requests issued for a non-main frame (iframe navigations).", NA_FAILED),
    Field("subframe_requests", "integer", "requests", "All requests attributed by Playwright to a non-main frame.", NA_FAILED),
    # --- trackers --------------------------------------------------------------------------------
    Field("tracker_matched_requests", "integer", "trackers", "Third-party requests whose hostname (or a parent domain) is a tracker entry in the reference list.", NA_FAILED),
    Field("unique_tracker_domains", "integer", "trackers", "Distinct matched tracker-list domains among third-party requests.", NA_FAILED),
    Field("tracker_request_ratio", "float", "trackers", "tracker_matched_requests / total_requests.", NA_FAILED + "; empty when total_requests == 0"),
    Field("third_party_hostnames_not_in_reference", "integer", "trackers", "Distinct third-party hostnames NOT found in the reference list (unknown status, not 'benign').", NA_FAILED),
    # --- cookies ---------------------------------------------------------------------------------
    Field("total_cookies", "integer", "cookies", "Cookies in the browser context (context.cookies()) at the end of the settle period.", NA_FAILED),
    Field("first_party_cookies", "integer", "cookies", "Cookies whose domain's registrable domain equals final_registrable_domain.", NA_FAILED),
    Field("third_party_cookies", "integer", "cookies", "Cookies whose domain's registrable domain differs from final_registrable_domain.", NA_FAILED),
    Field("unattributed_cookies", "integer", "cookies", "Cookies whose domain could not be mapped to a registrable domain.", NA_FAILED),
    Field("secure_cookies", "integer", "cookies", "Cookies with the Secure flag.", NA_FAILED),
    Field("httponly_cookies", "integer", "cookies", "Cookies with the HttpOnly flag.", NA_FAILED),
    Field("session_cookies", "integer", "cookies", "Cookies without an expiry (session cookies).", NA_FAILED),
    Field("samesite_none_cookies", "integer", "cookies", "Cookies with SameSite=None.", NA_FAILED),
    Field("max_cookie_lifetime_days", "float", "cookies", "Longest persistent-cookie lifetime (expiry - crawl time) in days.", NA_FAILED + "; empty when no persistent cookies"),
    # --- storage ---------------------------------------------------------------------------------
    Field("localstorage_write_count", "integer", "storage", "Calls to localStorage.setItem/removeItem/clear, summed over all instrumented documents.", NA_INSTR),
    Field("sessionstorage_write_count", "integer", "storage", "Calls to sessionStorage.setItem/removeItem/clear, summed over all instrumented documents.", NA_INSTR),
    Field("localstorage_read_count", "integer", "storage", "Calls to localStorage.getItem/key.", NA_INSTR),
    Field("sessionstorage_read_count", "integer", "storage", "Calls to sessionStorage.getItem/key.", NA_INSTR),
    Field("document_cookie_writes", "integer", "storage", "Assignments to document.cookie.", NA_INSTR),
    Field("storage_api_calls", "integer", "storage", "indexedDB.open + caches.open + navigator.storage.estimate/persist/persisted calls.", NA_INSTR),
    Field("storage_accessed", "boolean", "storage", "1 if any instrumented Web Storage read/write or storage-API call was observed.", NA_INSTR),
    Field("storage_modified", "boolean", "storage", "1 if any Web Storage write or document.cookie write was observed.", NA_INSTR),
    # --- fingerprinting indicators -------------------------------------------------------------
    Field("canvas_api_calls", "integer", "fingerprinting", "canvas_readback_calls + canvas_text_calls + isPointInPath calls.", NA_INSTR),
    Field("canvas_readback_calls", "integer", "fingerprinting", "toDataURL + toBlob + getImageData + OffscreenCanvas.convertToBlob.", NA_INSTR),
    Field("canvas_text_calls", "integer", "fingerprinting", "fillText + strokeText + measureText (2D context).", NA_INSTR),
    Field("webgl_api_calls", "integer", "fingerprinting", "getContext(webgl*) + getParameter + getExtension + getSupportedExtensions + getShaderPrecisionFormat + readPixels + getContextAttributes (WebGL1+2).", NA_INSTR),
    Field("webgl_unmasked_info_queries", "integer", "fingerprinting", "getParameter(UNMASKED_VENDOR_WEBGL | UNMASKED_RENDERER_WEBGL) calls.", NA_INSTR),
    Field("audio_api_calls", "integer", "fingerprinting", "AudioContext/OfflineAudioContext construction + createOscillator/createDynamicsCompressor/createAnalyser + startRendering + getFloatFrequencyData + getChannelData.", NA_INSTR),
    Field("offline_audio_contexts", "integer", "fingerprinting", "OfflineAudioContext constructions.", NA_INSTR),
    Field("other_fingerprinting_api_calls", "integer", "fingerprinting", "document.fonts.check + navigator.getBattery + mediaDevices.enumerateDevices + RTCPeerConnection construction + permissions.query.", NA_INSTR),
    Field("instrumented_documents", "integer", "fingerprinting", "Number of documents (main frame + iframes, incl. replaced documents) that returned an instrumentation snapshot.", NA_FAILED),
    # --- navigation / frames ---------------------------------------------------------------------
    Field("redirect_count", "integer", "navigation", "HTTP redirect hops in the main-document request chain.", NA_FAILED),
    Field("client_side_url_changes", "integer", "navigation", "Main-frame URL changes after the initial navigation committed (JS/meta redirects, history API).", NA_FAILED),
    Field("cross_domain_redirect", "boolean", "navigation", "1 if final_registrable_domain differs from initial_registrable_domain.", NA_FAILED),
    Field("iframe_count", "integer", "navigation", "Child frames (any depth) in page.frames at observation time.", NA_FAILED),
    Field("dom_iframe_count", "integer", "navigation", "<iframe> elements in the top-level document.", NA_DOM),
    Field("hidden_iframe_count", "integer", "navigation", "Top-document <iframe> elements that are not rendered (checkVisibility() false incl. opacity/visibility), have a content-box (clientWidth/clientHeight) width or height <= 1px, or lie entirely at negative coordinates.", NA_DOM),
    Field("cross_origin_iframe_count", "integer", "navigation", "Child frames whose URL origin differs from the main frame origin (about:blank/srcdoc frames excluded).", NA_FAILED),
    Field("navigation_duration_seconds", "float", "navigation", "Time for page.goto() of the final attempt to reach DOMContentLoaded.", NA_FAILED),
    Field("load_event_fired", "boolean", "navigation", "1 if the window load event fired within load_event_timeout_s.", NA_FAILED),
    Field("blocked_unsafe_destinations", "integer", "navigation", "Connections refused by the safety proxy because the destination was not a public address.", "never empty"),
    # --- labels (kept separate from features) ---------------------------------------------------
    Field("has_tracker_reference_match", "boolean", "labels", "1 if tracker_matched_requests > 0. A reference-list observation, NOT a maliciousness label.", NA_FAILED),
    Field("security_label", "category", "labels", "Independently verified security label. Not collected by the crawler.", "empty until independently labelled"),
    Field("manual_review_label", "category", "labels", "Manual review label. Not collected by the crawler.", "empty until manually reviewed"),
    Field("label_source", "string", "labels", "Source of security_label / manual_review_label.", "empty until labelled"),
    Field("label_confidence", "float", "labels", "Confidence of the label (0-1).", "empty until labelled"),
    Field("labeled_at", "datetime", "labels", "UTC time the label was assigned.", "empty until labelled"),
]

CORE_COLUMNS = [f.name for f in FIELDS]


def category_columns(categories: list[str]) -> list[str]:
    return [f"tracker_requests_cat_{slug(c)}" for c in categories]


def csv_columns(categories: list[str]) -> list[str]:
    cols = CORE_COLUMNS[:]
    idx = cols.index("third_party_hostnames_not_in_reference") + 1
    return cols[:idx] + category_columns(categories) + cols[idx:]


HTTP_SCHEMES = ("http", "https")
OTHER_TYPES_EXCLUDED = {"document", "script", "image", "stylesheet", "xhr", "fetch", "font", "media", "websocket"}


def _sum(counts: dict, pred) -> int:
    return sum(v for k, v in counts.items() if pred(k))


def compute_features(rec: dict, categories: list[str]) -> dict:
    """Flatten one website observation record into the CSV feature row."""
    crawl, final = rec["crawl"], rec.get("final") or {}
    row = {c: None for c in csv_columns(categories)}
    row.update({
        "website_id": rec["website_id"], "tranco_rank": rec.get("tranco_rank"),
        "original_domain": rec["original_domain"], "original_url": rec["original_url"],
        "initial_registrable_domain": rec.get("initial_registrable_domain"),
        "crawl_status": crawl["status"], "navigation_outcome": crawl["navigation_outcome"],
        "failure_reason": crawl.get("failure_reason"), "http_status": final.get("http_status"),
        "attempt_count": len(crawl["attempts"]), "retries": max(len(crawl["attempts"]) - 1, 0),
        "crawl_timestamp": crawl["crawl_timestamp"],
        "instrumentation_status": rec.get("instrumentation", {}).get("status", "not_run"),
        "blocked_unsafe_destinations": len(rec.get("safety", {}).get("blocked_destinations", [])),
    })
    labels = rec.get("labels", {})
    for k in ("security_label", "manual_review_label", "label_source", "label_confidence", "labeled_at"):
        row[k] = labels.get(k)
    if crawl["status"] not in ("success", "http_error"):
        return row

    row.update({"final_url": final.get("url"), "final_hostname": final.get("hostname"),
                "final_registrable_domain": final.get("registrable_domain"), "page_title": final.get("title")})

    pg = rec.get("page") or {}
    if pg.get("dom_available"):
        row["dom_element_count"] = pg["dom_element_count"]
        row["visible_text_length"] = pg["visible_text_length"]

    r = rec["request_summary"]
    row.update({k: r[k] for k in (
        "total_requests", "successful_requests", "failed_requests", "http_error_requests",
        "first_party_requests", "third_party_requests", "unique_request_hostnames",
        "unique_request_domains", "unique_third_party_domains", "iframe_requests", "subframe_requests")})
    types = r["resource_types"]
    row["document_requests"] = types.get("document", 0)
    row["script_requests"] = types.get("script", 0)
    row["image_requests"] = types.get("image", 0)
    row["stylesheet_requests"] = types.get("stylesheet", 0)
    row["xhr_fetch_requests"] = types.get("xhr", 0) + types.get("fetch", 0)
    row["font_requests"] = types.get("font", 0)
    row["media_requests"] = types.get("media", 0)
    row["websocket_requests"] = types.get("websocket", 0)
    row["other_requests"] = sum(v for k, v in types.items() if k not in OTHER_TYPES_EXCLUDED)

    t = rec["tracker_summary"]
    row["tracker_matched_requests"] = t["tracker_matched_requests"]
    row["unique_tracker_domains"] = t["unique_tracker_domains"]
    row["tracker_request_ratio"] = (round(t["tracker_matched_requests"] / r["total_requests"], 6)
                                    if r["total_requests"] else None)
    row["third_party_hostnames_not_in_reference"] = t["third_party_hostnames_not_in_reference"]
    for cat, col in zip(categories, category_columns(categories)):
        row[col] = t["requests_by_category"].get(cat, 0)
    row["has_tracker_reference_match"] = int(t["tracker_matched_requests"] > 0)

    c = rec["cookie_summary"]
    for k in ("total_cookies", "first_party_cookies", "third_party_cookies", "unattributed_cookies",
              "secure_cookies", "httponly_cookies", "session_cookies", "samesite_none_cookies",
              "max_cookie_lifetime_days"):
        row[k] = c[k]

    nav = rec["navigation"]
    row.update({
        "redirect_count": nav["redirect_count"], "client_side_url_changes": nav["client_side_url_changes"],
        "cross_domain_redirect": int(bool(nav["cross_domain_redirect"])),
        "navigation_duration_seconds": crawl.get("navigation_duration_seconds"),
        "load_event_fired": int(bool(nav["load_event_fired"])),
    })
    fr = rec["frames"]
    row["iframe_count"] = fr["iframe_count"]
    row["cross_origin_iframe_count"] = fr["cross_origin_iframe_count"]
    if fr.get("dom_available"):
        row["dom_iframe_count"] = fr["dom_iframe_count"]
        row["hidden_iframe_count"] = fr["hidden_iframe_count"]

    inst = rec["instrumentation"]
    row["instrumented_documents"] = inst["documents"]
    if inst["status"] == "ok":
        cnt = inst["counts_all_documents"]
        g = cnt.get
        row["localstorage_write_count"] = g("storage.localStorage.write", 0)
        row["sessionstorage_write_count"] = g("storage.sessionStorage.write", 0)
        row["localstorage_read_count"] = g("storage.localStorage.read", 0)
        row["sessionstorage_read_count"] = g("storage.sessionStorage.read", 0)
        row["document_cookie_writes"] = g("document.cookie.write", 0)
        row["storage_api_calls"] = _sum(cnt, lambda k: k.startswith("storageapi."))
        storage_any = _sum(cnt, lambda k: k.startswith("storage.") or k.startswith("storageapi."))
        row["storage_accessed"] = int(storage_any > 0)
        row["storage_modified"] = int(_sum(cnt, lambda k: k.endswith(".write") and (k.startswith("storage.") or k.startswith("document.cookie"))) > 0)
        readback = sum(g(k, 0) for k in ("canvas.toDataURL", "canvas.toBlob", "canvas.getImageData", "canvas.offscreen.convertToBlob"))
        text = sum(g(k, 0) for k in ("canvas.fillText", "canvas.strokeText", "canvas.measureText"))
        row["canvas_readback_calls"] = readback
        row["canvas_text_calls"] = text
        row["canvas_api_calls"] = readback + text + g("canvas.isPointInPath", 0)
        row["webgl_unmasked_info_queries"] = g("webgl.unmaskedInfoQuery", 0)
        row["webgl_api_calls"] = (_sum(cnt, lambda k: k.startswith("webgl.") and k != "webgl.unmaskedInfoQuery")
                                  + _sum(cnt, lambda k: k.startswith("canvas.getContext.") and "webgl" in k))
        row["offline_audio_contexts"] = g("OfflineAudioContext()", 0)
        row["audio_api_calls"] = (_sum(cnt, lambda k: k.startswith("audio."))
                                  + sum(g(k, 0) for k in ("AudioContext()", "OfflineAudioContext()", "webkitAudioContext()")))
        row["other_fingerprinting_api_calls"] = _sum(cnt, lambda k: k.startswith("other.")) + g("RTCPeerConnection()", 0)
    return row


def summarize_requests(requests: list[dict]) -> dict:
    http = [q for q in requests if q["scheme"] in HTTP_SCHEMES]
    types = Counter(q["resource_type"] for q in http)
    statuses = Counter(str(q["status"]) if q["status"] is not None else "no_response" for q in http)
    hosts = {q["hostname"] for q in http}
    third = [q for q in http if q["party"] == "third"]
    return {
        "total_requests": len(http),
        "non_http_requests": len(requests) - len(http),
        "successful_requests": sum(1 for q in http if not q["failed"] and q["status"] is not None and q["status"] < 400),
        "failed_requests": sum(1 for q in http if q["failed"]),
        "http_error_requests": sum(1 for q in http if q["status"] is not None and q["status"] >= 400),
        "incomplete_requests": sum(1 for q in http if not q["failed"] and q["status"] is None),
        "first_party_requests": sum(1 for q in http if q["party"] == "first"),
        "third_party_requests": len(third),
        "unique_request_hostnames": len(hosts),
        "unique_request_domains": len({q["registrable_domain"] for q in http}),
        "unique_third_party_domains": len({q["registrable_domain"] for q in third}),
        "iframe_requests": sum(1 for q in http if q["resource_type"] == "document" and q["frame"] == "subframe"),
        "subframe_requests": sum(1 for q in http if q["frame"] == "subframe"),
        "resource_types": dict(types),
        "status_distribution": dict(statuses),
    }
