"""Crawl configuration. Every value here is recorded in crawl_manifest.json."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path

PACKAGE_DIR = Path(__file__).resolve().parent
COLLECTION_DIR = PACKAGE_DIR.parent
DEFAULT_TRANCO_CSV = COLLECTION_DIR / "top-1m.csv"
REFERENCE_DIR = COLLECTION_DIR / "reference"
TDS_PATH = REFERENCE_DIR / "extension-tds.json"
TDS_META_PATH = REFERENCE_DIR / "extension-tds.meta.json"
TDS_URL = "https://staticcdn.duckduckgo.com/trackerblocking/v5/current/extension-tds.json"
URLHAUS_PATH = REFERENCE_DIR / "urlhaus-hostfile.txt"
URLHAUS_META_PATH = REFERENCE_DIR / "urlhaus-hostfile.meta.json"
URLHAUS_URL = "https://urlhaus.abuse.ch/downloads/hostfile/"
TRANCO_META_PATH = REFERENCE_DIR / "tranco-list.meta.json"
SMOKE_SITES = COLLECTION_DIR / "smoke_sites.txt"


@dataclass
class CrawlConfig:
    workers: int = 3
    headless: bool = True
    # page.goto() waits for DOMContentLoaded up to this many seconds.
    navigation_timeout_s: float = 30.0
    # After DOMContentLoaded, wait up to this long for the window "load" event.
    load_event_timeout_s: float = 15.0
    # Fixed settling period after load (or load timeout) before observations are read.
    settle_s: float = 5.0
    # Hard cap for one website including retries/fallbacks; the visit is abandoned after it.
    overall_timeout_s: float = 150.0
    # Retries of the same URL for transient failures (timeouts, resets, HTTP 429/503).
    max_retries: int = 2
    backoff_base_s: float = 3.0
    max_retry_after_s: float = 30.0
    # Courtesy pause each worker takes between websites.
    inter_site_delay_s: float = 1.0
    # Stop the run when this many consecutive websites end with HTTP 5xx on the main document.
    max_consecutive_server_errors: int = 20
    viewport_width: int = 1366
    viewport_height: int = 768
    locale: str = "en-US"
    # Maximum fingerprinting/storage evidence events kept per document.
    max_evidence_events: int = 25
    # Path component of saved URLs is truncated to this many characters.
    max_path_chars: int = 200
    launch_args: list[str] = field(default_factory=lambda: [
        "--disable-quic",  # QUIC (UDP) cannot traverse the filtering proxy
        "--force-webrtc-ip-handling-policy=disable_non_proxied_udp",
        "--disable-background-networking",
    ])

    def to_dict(self) -> dict:
        return asdict(self)
