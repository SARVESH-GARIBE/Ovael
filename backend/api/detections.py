"""
Detections endpoints. Storage is in-memory for now (backend/db not
built yet); everything is synchronous, no queue.

POST /detections is new relative to the API contract table (which only
lists GETs) — it is the entry point that feeds a feature vector in.
"""

import uuid
from datetime import datetime, timezone
from functools import lru_cache
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from feature_extraction.schema import FeatureVector
from learning_loop.hard_example_store import HardExampleStore
from ml.backend_models.multiclass.model import MulticlassModel
from ml.backend_models.novelty.model import NoveltyModel
from orchestrator.pipeline import detect

router = APIRouter(prefix="/detections", tags=["detections"])


class FeatureVectorIn(BaseModel):
    src_ip: str
    dst_ip: str
    src_port: int = Field(ge=0, le=65535)
    dst_port: int = Field(ge=0, le=65535)
    protocol: Literal["TCP", "UDP", "ICMP"]
    byte_count: float = Field(ge=0)
    duration: float = Field(ge=0)
    packet_rate: float = Field(ge=0)
    packet_count: int = Field(ge=0)
    simulation_id: str | None = None


class DetectionStore:
    def __init__(self):
        self._items: dict[str, dict] = {}

    def add(self, detection: dict) -> None:
        self._items[detection["id"]] = detection

    def get(self, detection_id: str) -> dict | None:
        return self._items.get(detection_id)

    def recent(self, limit: int) -> list[dict]:
        return sorted(self._items.values(), key=lambda d: d["timestamp"], reverse=True)[:limit]


@lru_cache(maxsize=1)
def get_models() -> tuple[MulticlassModel, NoveltyModel]:
    return MulticlassModel.load(), NoveltyModel.load()


@lru_cache(maxsize=1)
def get_detection_store() -> DetectionStore:
    return DetectionStore()


@lru_cache(maxsize=1)
def get_hard_example_store() -> HardExampleStore:
    return HardExampleStore()


@router.post("", status_code=201)
def create_detection(
    body: FeatureVectorIn,
    models=Depends(get_models),
    detections: DetectionStore = Depends(get_detection_store),
    hard_examples: HardExampleStore = Depends(get_hard_example_store),
):
    fields = body.model_dump(exclude={"simulation_id"})
    feature_vector = FeatureVector(**fields)
    try:
        result = detect(feature_vector, *models)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    if result.decision.is_hard_example:
        hard_examples.add(
            feature_vector, (result.label, result.confidence), result.novelty_score, body.simulation_id
        )

    detection = {
        "id": str(uuid.uuid4()),
        "simulation_id": body.simulation_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "multiclass": {"label": result.label, "confidence": result.confidence},
        "novelty": {"score": result.novelty_score},
        "risk_score": result.risk_score,
        "severity": result.severity,
        "explanation": None,
        # Additive fields beyond the frozen contract shape:
        "verdict": result.decision.verdict,
        "is_hard_example": result.decision.is_hard_example,
    }
    detections.add(detection)
    return detection


@router.get("")
def list_detections(limit: int = 50, detections: DetectionStore = Depends(get_detection_store)):
    return detections.recent(limit)


@router.get("/{detection_id}")
def get_detection(detection_id: str, detections: DetectionStore = Depends(get_detection_store)):
    detection = detections.get(detection_id)
    if detection is None:
        raise HTTPException(status_code=404, detail="detection not found")
    return detection
