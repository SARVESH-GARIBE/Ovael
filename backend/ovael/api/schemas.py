"""Request and response models. FastAPI turns these into the OpenAPI document at /api/openapi.json,
which is the API contract the frontend is written against. WebSocket events carry the same shapes.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Annotated, Literal

from pydantic import AfterValidator, BaseModel, ConfigDict, Field


def _utc(d: datetime | None) -> datetime | None:
    # SQLite hands timestamps back without a zone; they are always stored in UTC.
    return d.replace(tzinfo=timezone.utc) if d is not None and d.tzinfo is None else d


UTC = Annotated[datetime, AfterValidator(_utc)]

Module = Literal["network", "website"]
RiskLevel = Literal["low", "suspicious", "medium", "high"]


class _Orm(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class TopFeature(BaseModel):
    feature: str
    description: str
    value: float | None
    baseline: float | None
    contribution: float
    method: str


class DetectionOut(_Orm):
    id: str
    created_at: UTC
    module: Module
    origin: str
    # detect() contract
    label: str
    confidence: float
    anomaly_score: float
    risk_level: RiskLevel
    top_features: list[TopFeature]
    model_version: str
    # orchestrator
    family: str
    risk_score: float
    is_attack: bool
    is_unusual: bool
    models_agree: bool
    action: str
    breakdown: dict
    probabilities: dict
    # network metadata
    src_ip: str | None = None
    dst_ip: str | None = None
    src_port: int | None = None
    dst_port: int | None = None
    protocol: int | None = None
    incident_id: str | None = None
    scan_id: str | None = None


class DetectionDetail(DetectionOut):
    features: dict


class LiveDetection(DetectionOut):
    """What a new_detection event carries."""

    blocked: bool = False
    incident_count: int = 1


class IncidentOut(_Orm):
    id: str
    module: Module
    family: str
    label: str
    src_ip: str | None
    dst_ip: str | None
    first_seen: UTC
    last_seen: UTC
    detection_count: int
    risk_level: RiskLevel
    max_risk_score: float
    status: str
    last_detection_id: str | None


class ScanCreate(BaseModel):
    url: str = Field(..., max_length=2048, examples=["https://example.com"])


class ScanOut(_Orm):
    id: str
    created_at: UTC
    finished_at: UTC | None
    url: str
    domain: str
    status: Literal["queued", "running", "completed", "failed"]
    error: str | None
    cached: bool
    detection_id: str | None
    report: dict


class ScanDetail(ScanOut):
    detection: DetectionOut | None = None


class ActionOut(_Orm):
    id: str
    created_at: UTC
    action: str
    target_ip: str
    status: str
    mode: str
    reason: str
    detection_id: str | None
    incident_id: str | None
    undone_at: UTC | None
    undone_by: str | None
    error: str | None


class ReviewItemOut(_Orm):
    id: str
    created_at: UTC
    module: Module
    detection_id: str
    reason: str
    predicted_label: str
    status: str
    final_label: str | None
    note: str | None
    reviewer: str | None
    reviewed_at: UTC | None
    used_in_version: str | None
    context: dict


class ReviewConfirm(BaseModel):
    label: str = Field(..., min_length=1, max_length=64,
                       description="Final label: an existing class, 'benign', or a new class name")
    note: str | None = Field(None, max_length=2000)


class ReviewDecision(BaseModel):
    id: str = Field(..., max_length=32)
    label: str = Field(..., min_length=1, max_length=64)


class ReviewBatch(BaseModel):
    items: list[ReviewDecision] = Field(..., min_length=1, max_length=500)
    note: str | None = Field(None, max_length=2000)


class ReviewReject(BaseModel):
    note: str | None = Field(None, max_length=2000)


class DetectRequest(BaseModel):
    module: Module
    features: dict[str, float | int | None]
    explain: bool = True


class FlowIn(BaseModel):
    features: dict[str, float | int | None]
    src_ip: str | None = None
    dst_ip: str | None = None
    src_port: int | None = None
    dst_port: int | None = None
    protocol: int | None = None


class FlowBatch(BaseModel):
    flows: list[FlowIn] = Field(..., min_length=1, max_length=2000)
    origin: Literal["live", "simulated"] = "live"


class FlowBatchResult(BaseModel):
    accepted: int
    alerts: int
    blocked_sources: list[str]


class SimulateRequest(BaseModel):
    scenario: str = Field("full_demo", examples=["full_demo", "dos_flood", "port_scan", "novel"])
    duration_s: float = Field(20, ge=2, le=300)


class ModelVersionOut(BaseModel):
    model_config = ConfigDict(extra="allow", protected_namespaces=())
    module: Module
    version: str
    status: str
    classes: list[str]
    trained_at: str | None = None
    label_source: str | None = None
    metrics: dict = {}


class RetrainResult(BaseModel):
    queued: bool
    module: Module
