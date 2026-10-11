"""PostgreSQL schema (SQLite works too, for development and tests)."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def new_id() -> str:
    return uuid.uuid4().hex


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    type_annotation_map = {dict: JSON, list: JSON, datetime: DateTime(timezone=True)}


class _Ids:
    """Assign the id and timestamp at construction, not at flush, so related rows and live events
    can reference a row before it is written."""

    def __init__(self, **kw):
        kw.setdefault("id", new_id())
        if "created_at" in self.__table__.c:
            kw.setdefault("created_at", utcnow())
        super().__init__(**kw)


class Detection(_Ids, Base):
    """One detect() result, from either module. Every result is kept with its model version."""

    __tablename__ = "detections"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
    module: Mapped[str] = mapped_column(String(16))
    origin: Mapped[str] = mapped_column(String(16), default="live")  # live | simulated | manual
    # contract fields
    label: Mapped[str] = mapped_column(String(64))
    confidence: Mapped[float] = mapped_column(Float)
    anomaly_score: Mapped[float] = mapped_column(Float)
    risk_level: Mapped[str] = mapped_column(String(16))
    top_features: Mapped[list] = mapped_column(default=list)
    model_version: Mapped[str] = mapped_column(String(64))
    # orchestrator output
    family: Mapped[str] = mapped_column(String(32))
    risk_score: Mapped[float] = mapped_column(Float)
    is_attack: Mapped[bool] = mapped_column(Boolean)
    is_unusual: Mapped[bool] = mapped_column(Boolean)
    models_agree: Mapped[bool] = mapped_column(Boolean)
    action: Mapped[str] = mapped_column(String(32))
    breakdown: Mapped[dict] = mapped_column(default=dict)
    probabilities: Mapped[dict] = mapped_column(default=dict)
    features: Mapped[dict] = mapped_column(default=dict)
    # network metadata
    src_ip: Mapped[str | None] = mapped_column(String(45))
    dst_ip: Mapped[str | None] = mapped_column(String(45))
    src_port: Mapped[int | None] = mapped_column(Integer)
    dst_port: Mapped[int | None] = mapped_column(Integer)
    protocol: Mapped[int | None] = mapped_column(Integer)
    # links
    incident_id: Mapped[str | None] = mapped_column(ForeignKey("incidents.id"))
    scan_id: Mapped[str | None] = mapped_column(String(32))

    __table_args__ = (
        Index("ix_detections_module_created", "module", "created_at"),
        Index("ix_detections_risk_created", "risk_level", "created_at"),
        Index("ix_detections_src_ip", "src_ip"),
        Index("ix_detections_incident", "incident_id"),
    )


class Incident(_Ids, Base):
    """Detections from the same source and family inside the incident window, grouped.

    A flood is thousands of detections; the alert feed shows one incident with a counter.
    """

    __tablename__ = "incidents"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    module: Mapped[str] = mapped_column(String(16))
    family: Mapped[str] = mapped_column(String(32))
    label: Mapped[str] = mapped_column(String(64))
    src_ip: Mapped[str | None] = mapped_column(String(45))
    dst_ip: Mapped[str | None] = mapped_column(String(45))
    first_seen: Mapped[datetime] = mapped_column(default=utcnow)
    last_seen: Mapped[datetime] = mapped_column(default=utcnow)
    detection_count: Mapped[int] = mapped_column(Integer, default=1)
    risk_level: Mapped[str] = mapped_column(String(16))
    max_risk_score: Mapped[float] = mapped_column(Float)
    status: Mapped[str] = mapped_column(String(16), default="open")  # open | mitigated | closed
    last_detection_id: Mapped[str | None] = mapped_column(String(32))

    __table_args__ = (Index("ix_incidents_key", "module", "src_ip", "family", "last_seen"),)


class Scan(_Ids, Base):
    __tablename__ = "scans"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
    finished_at: Mapped[datetime | None] = mapped_column()
    url: Mapped[str] = mapped_column(Text)
    domain: Mapped[str] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(16), default="queued")  # queued|running|completed|failed
    error: Mapped[str | None] = mapped_column(Text)
    cached: Mapped[bool] = mapped_column(Boolean, default=False)
    detection_id: Mapped[str | None] = mapped_column(String(32))
    report: Mapped[dict] = mapped_column(default=dict)  # page facts + evidence for the report card
    client_hash: Mapped[str | None] = mapped_column(String(64))

    __table_args__ = (Index("ix_scans_domain_created", "domain", "created_at"),)


class DefenseAction(_Ids, Base):
    __tablename__ = "defense_actions"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
    action: Mapped[str] = mapped_column(String(16))  # block
    target_ip: Mapped[str] = mapped_column(String(45))
    status: Mapped[str] = mapped_column(String(16))  # applied | simulated | failed | undone
    mode: Mapped[str] = mapped_column(String(16))  # agent | simulate
    reason: Mapped[str] = mapped_column(Text)
    detection_id: Mapped[str | None] = mapped_column(String(32))
    incident_id: Mapped[str | None] = mapped_column(String(32))
    undone_at: Mapped[datetime | None] = mapped_column()
    undone_by: Mapped[str | None] = mapped_column(String(64))
    error: Mapped[str | None] = mapped_column(Text)

    __table_args__ = (Index("ix_actions_target_status", "target_ip", "status"),)


class ReviewItem(_Ids, Base):
    """A hard example: the models disagreed in the flagged way, or the classifier was unsure."""

    __tablename__ = "review_items"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
    module: Mapped[str] = mapped_column(String(16))
    detection_id: Mapped[str] = mapped_column(String(32))
    reason: Mapped[str] = mapped_column(String(32))  # normal_but_unusual | low_confidence
    predicted_label: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(16), default="pending")  # pending|confirmed|rejected
    final_label: Mapped[str | None] = mapped_column(String(64))
    note: Mapped[str | None] = mapped_column(Text)
    reviewer: Mapped[str | None] = mapped_column(String(64))
    reviewed_at: Mapped[datetime | None] = mapped_column()
    used_in_version: Mapped[str | None] = mapped_column(String(64))
    features: Mapped[dict] = mapped_column(default=dict)
    context: Mapped[dict] = mapped_column(default=dict)

    __table_args__ = (Index("ix_review_module_status", "module", "status", "created_at"),)


class AuditLog(Base):
    __tablename__ = "audit_log"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
    actor: Mapped[str] = mapped_column(String(64))
    action: Mapped[str] = mapped_column(String(64))
    target: Mapped[str | None] = mapped_column(String(128))
    detail: Mapped[dict] = mapped_column(default=dict)
