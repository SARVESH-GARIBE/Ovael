"""Runtime settings. Every value can be overridden with an OVAEL_* environment variable.

Optional infrastructure (Redis, Celery broker, scanner service, defense agent, read replica) is
off when its URL is unset. The backend then falls back to an in-process implementation, so a
single `uvicorn` process is a complete system for development and demos.
"""

from __future__ import annotations

import socket
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parent.parent
REPO_DIR = BACKEND_DIR.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="OVAEL_", env_file=".env", extra="ignore")

    env: Literal["dev", "test", "prod"] = "dev"
    instance_id: str = socket.gethostname()  # container hostname behind the load balancer
    log_level: str = "INFO"
    cors_origins: list[str] = ["http://localhost:5173"]

    # Data layer
    database_url: str = f"sqlite+aiosqlite:///{BACKEND_DIR / 'ovael.db'}"
    database_read_url: str | None = None  # read replica for dashboard queries
    db_pool_size: int = 10
    auto_create_schema: bool = True  # dev convenience; compose runs the one-shot `migrate` service

    # Optional infrastructure
    redis_url: str | None = None
    celery_broker_url: str | None = None
    scanner_url: str | None = None  # isolated scanner service; unset = scan in-process
    defense_agent_url: str | None = None  # agent inside the victim container

    # Auth: bearer tokens. Unset in dev means open access (a warning is logged at startup).
    admin_token: str | None = None
    sensor_token: str | None = None

    # Models
    model_dir: Path = BACKEND_DIR / "model_store"
    anomaly_threshold: float = 0.99  # anomaly_score above this = "unusual" (~1% of normal traffic)
    website_dataset: Path = REPO_DIR / "dataset_collection" / "output" / "website_features.csv"
    network_dataset: Path = BACKEND_DIR / "data" / "network_flows.csv"
    crawler_path: Path = REPO_DIR / "dataset_collection"

    # Website scans
    scan_rate_limit: int = 10  # scans per client per window
    scan_rate_window_s: int = 60
    scan_cache_ttl_s: int = 6 * 3600
    max_concurrent_scans: int = 2  # caps Chromium instances per worker
    scan_timeout_s: float = 90.0
    max_url_length: int = 2048

    # Defense
    defense_mode: Literal["off", "simulate", "agent"] = "simulate"
    sandbox_subnet: str = "172.28.0.0/16"
    defense_token: str | None = None

    # Learning loop
    retrain_min_new_samples: int = 25
    low_confidence_threshold: float = 0.5

    # Live push
    ws_client_queue: int = 500
    incident_window_s: int = 60
    incident_push_interval_s: float = 0.5

    enable_simulator: bool = True  # POST /api/simulate drives synthetic traffic through the real pipeline


@lru_cache
def get_settings() -> Settings:
    return Settings()
