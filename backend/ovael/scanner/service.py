"""Isolated scanner service (architecture section 7.1).

Runs in its own container on a network that can reach the internet but NOT the database or Redis.
Workers call it over HTTP and get features back; the scanner never sees any other data.

    uvicorn ovael.scanner.service:app --host 0.0.0.0 --port 9200
"""

from __future__ import annotations

import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel

from .runner import ScanFailed, WebsiteScanner
from .url_guard import UnsafeURL, check

TOKEN = os.environ.get("OVAEL_SCANNER_TOKEN")
scanner = WebsiteScanner(
    Path(os.environ.get("OVAEL_CRAWLER_PATH", "/app/dataset_collection")),
    max_concurrent=int(os.environ.get("OVAEL_MAX_CONCURRENT_SCANS", "2")),
    timeout_s=float(os.environ.get("OVAEL_SCAN_TIMEOUT_S", "90")),
)


@asynccontextmanager
async def lifespan(_: FastAPI):
    await scanner.start()
    yield
    await scanner.stop()


app = FastAPI(title="ovael scanner", lifespan=lifespan, docs_url=None, redoc_url=None)


class ScanRequest(BaseModel):
    url: str
    scan_id: str


@app.get("/health")
def health() -> dict:
    return {"ok": True}


@app.post("/scan")
async def scan(req: ScanRequest, authorization: str | None = Header(default=None)) -> dict:
    if TOKEN and authorization != f"Bearer {TOKEN}":
        raise HTTPException(401, "bad token")
    try:
        checked = await check(req.url)  # checked again here: never trust the caller
    except UnsafeURL as exc:
        raise HTTPException(422, str(exc))
    try:
        return await scanner.scan(checked.url, checked.hostname, checked.domain, req.scan_id)
    except ScanFailed as exc:
        raise HTTPException(502, f"scan failed: {exc}")
