"""Research lab endpoints: evasion sweeps and the learning-loop experiment."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from ...core.context import AppContext
from ...ml.adversarial import ATTACKS, TECHNIQUES
from ...services import lab
from ..deps import get_ctx, require_admin

router = APIRouter(prefix="/api/lab", tags=["research lab"])


class EvasionRequest(BaseModel):
    attack: Literal["dos_flood", "port_scan", "slow_dos", "brute_force", "web_attack"] = "dos_flood"
    technique: Literal["slow_down", "pad_packets", "spread_out", "mimic"] = "mimic"
    steps: int = Field(11, ge=3, le=21)
    flows: int = Field(80, ge=10, le=300)


class ProbeRequest(BaseModel):
    flows: int = Field(40, ge=10, le=200)


class TeachRequest(BaseModel):
    probe_id: str = Field(..., min_length=4, max_length=32)
    label: str = Field("exfiltration", min_length=2, max_length=40, pattern=r"^[A-Za-z][A-Za-z0-9 _-]*$")


@router.get("/evasion/options", summary="Attacks and modification techniques for the evasion sweep")
async def evasion_options() -> dict:
    return {"attacks": ATTACKS, "techniques": TECHNIQUES}


@router.post("/evasion", summary="Modify an attack step by step and measure both models at each step")
async def evasion(body: EvasionRequest, ctx: AppContext = Depends(get_ctx)) -> dict:
    return await lab.evasion(ctx, body.attack, body.technique, body.steps, body.flows)


@router.post("/learning/probe", summary="Show the model a behaviour it was never trained on")
async def learning_probe(body: ProbeRequest, ctx: AppContext = Depends(get_ctx),
                         _: str = Depends(require_admin)) -> dict:
    return await lab.probe(ctx, body.flows)


@router.post("/learning/teach", summary="Label a probe's flows and retrain")
async def learning_teach(body: TeachRequest, ctx: AppContext = Depends(get_ctx),
                         actor: str = Depends(require_admin)) -> dict:
    try:
        return await lab.teach(ctx, body.probe_id, body.label, actor)
    except ValueError as exc:
        raise HTTPException(409, str(exc))
