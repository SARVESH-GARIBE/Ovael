"""Website behaviour feature schema: the model-input subset of the crawler's CSV columns.

The crawler (`dataset_collection/ovael_crawler/schema.py`) owns how each value is computed. This
file only chooses which of its columns the models see. Identity, status and label columns are
excluded, and so are the per-category tracker counts that only a handful of sites ever hit.
"""

from __future__ import annotations

# Features the weak-labelling rules read (ml/labeling.py), plus everything derived from the same
# tracker list. They are kept OUT of the model: if the model could see them it would only learn to
# copy the rules (5-fold CV macro F1 0.94, but meaningless). Without them it has to predict the
# label from general page behaviour (macro F1 0.86 vs a 0.35 majority baseline on 336 sites),
# which shows tracking is visible in behaviour, not just in a blocklist. The scanner still reports
# these values as evidence on the report card.
LABEL_RULE_FEATURES: list[str] = [
    "tracker_matched_requests",
    "unique_tracker_domains",
    "tracker_request_ratio",
    "third_party_hostnames_not_in_reference",
    "tracker_requests_cat_advertising",
    "tracker_requests_cat_analytics",
    "tracker_requests_cat_ad_motivated_tracking",
    "tracker_requests_cat_session_replay",
    "tracker_requests_cat_ad_fraud",
    "tracker_requests_cat_social_network",
    "tracker_requests_cat_malware",
    "third_party_cookies",
    "canvas_readback_calls",
    "webgl_unmasked_info_queries",
    "audio_api_calls",
    "offline_audio_contexts",
]

WEBSITE_FEATURES: list[str] = [
    "dom_element_count",
    "total_requests",
    "failed_requests",
    "first_party_requests",
    "third_party_requests",
    "unique_request_hostnames",
    "unique_third_party_domains",
    "script_requests",
    "image_requests",
    "xhr_fetch_requests",
    "websocket_requests",
    "iframe_requests",
    "total_cookies",
    "samesite_none_cookies",
    "max_cookie_lifetime_days",
    "localstorage_write_count",
    "sessionstorage_write_count",
    "document_cookie_writes",
    "storage_api_calls",
    "canvas_text_calls",
    "webgl_api_calls",
    "other_fingerprinting_api_calls",
    "redirect_count",
    "client_side_url_changes",
    "cross_domain_redirect",
    "iframe_count",
    "hidden_iframe_count",
    "cross_origin_iframe_count",
]

WEBSITE_FEATURE_DESCRIPTIONS: dict[str, str] = {
    "tracker_matched_requests": "Requests to known tracker domains",
    "unique_tracker_domains": "Distinct tracker domains",
    "tracker_request_ratio": "Share of requests that go to trackers",
    "third_party_requests": "Third-party requests",
    "unique_third_party_domains": "Distinct third-party domains",
    "third_party_hostnames_not_in_reference": "Third-party hosts not in the tracker list",
    "third_party_cookies": "Third-party cookies",
    "samesite_none_cookies": "Cross-site cookies (SameSite=None)",
    "max_cookie_lifetime_days": "Longest cookie lifetime (days)",
    "canvas_readback_calls": "Canvas pixel readbacks (fingerprinting)",
    "webgl_unmasked_info_queries": "GPU identity queries (fingerprinting)",
    "audio_api_calls": "Audio API calls",
    "offline_audio_contexts": "Offline audio contexts (fingerprinting)",
    "other_fingerprinting_api_calls": "Other fingerprinting API calls",
    "tracker_requests_cat_session_replay": "Session-replay tracker requests",
    "tracker_requests_cat_malware": "Requests to hosts tagged as malware",
    "hidden_iframe_count": "Hidden iframes",
    "cross_origin_iframe_count": "Cross-origin iframes",
    "redirect_count": "Redirects",
    "cross_domain_redirect": "Redirected to another domain",
    "localstorage_write_count": "localStorage writes",
    "document_cookie_writes": "Cookies written by script",
    "dom_element_count": "Page elements",
    "total_requests": "Requests",
    "failed_requests": "Failed requests",
    "first_party_requests": "First-party requests",
    "unique_request_hostnames": "Distinct hosts contacted",
    "script_requests": "Scripts loaded",
    "image_requests": "Images loaded",
    "xhr_fetch_requests": "Background (XHR/fetch) requests",
    "websocket_requests": "WebSocket connections",
    "iframe_requests": "Iframe loads",
    "tracker_requests_cat_advertising": "Advertising tracker requests",
    "tracker_requests_cat_analytics": "Analytics tracker requests",
    "tracker_requests_cat_ad_motivated_tracking": "Ad-motivated tracking requests",
    "tracker_requests_cat_ad_fraud": "Ad-fraud detection requests",
    "tracker_requests_cat_social_network": "Social network tracker requests",
    "total_cookies": "Cookies",
    "sessionstorage_write_count": "sessionStorage writes",
    "storage_api_calls": "Storage API calls",
    "canvas_text_calls": "Canvas text drawing",
    "webgl_api_calls": "WebGL API calls",
    "client_side_url_changes": "Client-side URL changes",
    "iframe_count": "Iframes",
}
