"""Browser extension: score the sites a user visits with the website model.

The extension measures each visit in the user's own browser and sends only the registrable domain
and the feature counts (never URLs, page content or cookie values). Nothing is stored here: the
verdict goes back to the extension, which keeps the history locally.
"""

from __future__ import annotations

import asyncio
import hashlib

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from ...core.context import AppContext
from ...feature_extraction.website_schema import WEBSITE_FEATURE_DESCRIPTIONS
from ...orchestrator import family_for
from ..deps import client_ip, get_ctx

router = APIRouter(prefix="/api/extension", tags=["extension"])

RATE_LIMIT = 60  # batches per client per minute; the extension sends one batch every few seconds at most


class VisitIn(BaseModel):
    domain: str = Field(..., max_length=253)
    features: dict[str, float | int | None]


class ScoreRequest(BaseModel):
    visits: list[VisitIn] = Field(..., min_length=1, max_length=50)


class VisitScore(BaseModel):
    domain: str
    label: str
    family: str
    family_name: str
    summary: str
    risk_level: str
    risk_score: float
    confidence: float
    is_unusual: bool
    model_version: str
    top_features: list[dict]


@router.post("/score", response_model=list[VisitScore], summary="Score visits measured by the browser extension")
async def score(body: ScoreRequest, request: Request, ctx: AppContext = Depends(get_ctx)) -> list[VisitScore]:
    key = hashlib.sha256(client_ip(request).encode()).hexdigest()[:32]
    allowed, retry = await ctx.cache.hit(f"ext:{key}", RATE_LIMIT, 60)
    if not allowed:
        raise HTTPException(429, f"too many visits; try again in {retry}s", headers={"Retry-After": str(retry)})
    results = await asyncio.to_thread(ctx.engine.detect_many, "website",
                                      [v.features for v in body.visits], True)
    out = []
    for v, r in zip(body.visits, results):
        for f in r.top_features:
            f.setdefault("description", WEBSITE_FEATURE_DESCRIPTIONS.get(f.get("feature"), f.get("feature")))
        out.append(VisitScore(domain=v.domain, label=r.label, family=r.family, family_name=r.family_name,
                              summary=family_for("website", r.family).summary, risk_level=r.risk_level,
                              risk_score=r.risk_score, confidence=r.confidence, is_unusual=r.is_unusual,
                              model_version=r.model_version, top_features=r.top_features))
    return out
