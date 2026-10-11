"""Prometheus metrics exposed at /metrics on every instance."""

from __future__ import annotations

from prometheus_client import Counter, Gauge, Histogram

HTTP_REQUESTS = Counter("ovael_http_requests_total", "HTTP requests", ["method", "route", "status"])
HTTP_LATENCY = Histogram("ovael_http_request_seconds", "HTTP latency", ["method", "route"])
DETECTIONS = Counter("ovael_detections_total", "detect() results", ["module", "risk_level"])
DETECT_LATENCY = Histogram("ovael_detect_seconds", "detect() batch latency", ["module"],
                           buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5))
SCANS = Counter("ovael_scans_total", "Website scans", ["status"])
SCAN_LATENCY = Histogram("ovael_scan_seconds", "Website scan duration",
                         buckets=(2, 5, 10, 20, 30, 45, 60, 90, 120))
SCANS_RUNNING = Gauge("ovael_scans_running", "Scans in progress on this instance")
DEFENSE_ACTIONS = Counter("ovael_defense_actions_total", "Defense actions", ["action", "status"])
EVENTS_PUBLISHED = Counter("ovael_events_published_total", "Live events", ["type"])
WS_CLIENTS = Gauge("ovael_ws_clients", "Connected WebSocket clients on this instance")
WS_DROPPED = Counter("ovael_ws_dropped_events_total", "Events dropped for slow WebSocket clients")
REVIEW_QUEUE = Counter("ovael_review_items_total", "Hard examples queued", ["module", "reason"])
