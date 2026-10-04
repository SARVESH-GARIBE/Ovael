"""
Stage 1 data contracts — the shapes passed between pipeline stages.

These are the only "real" objects in Stage 1: everything that produces
or consumes them (feature extraction, detection, novelty, orchestration,
risk analysis) is a stub or placeholder, but the contracts themselves
are meant to be the stable interface later stages build against.

All contracts are frozen (immutable) dataclasses. This is a deliberate,
low-cost choice: it makes "the orchestrator combines results without
altering either input" a property Python enforces for us, rather than
something tests have to take on faith.

Each contract carries a free-form `metadata: dict` for forward
compatibility — later stages can attach extra context without changing
the contract's shape.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class RawTraffic:
    """One observed unit of network traffic, before any feature
    extraction. Stage 1 does not define a real capture pipeline — this
    is the shape that a (future) real capture layer must produce."""

    source_ip: str
    destination_ip: str
    source_port: int
    destination_port: int
    protocol: str
    payload_size: int
    timestamp: float
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class FeatureVector:
    """The output of feature extraction. In Stage 1, feature extraction
    is a pass-through stub, so `features` below is a placeholder dict,
    not real engineered features."""

    source_ip: str
    destination_ip: str
    source_port: int
    destination_port: int
    protocol: str
    payload_size: int
    timestamp: float
    features: dict[str, float] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class DetectionResult:
    """Output of the Detection Agent. Stage 1 only ships a deterministic
    stub implementation — `predicted_class` and `confidence` below carry
    no real meaning until a real model exists."""

    predicted_class: str
    confidence: float
    model_name: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class NoveltyResult:
    """Output of the Novelty Agent. Stage 1 only ships a deterministic
    stub implementation — `is_novel` and `novelty_score` below carry no
    real meaning until a real model exists."""

    is_novel: bool
    novelty_score: float
    model_name: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class OrchestrationContext:
    """The orchestrator's output: DetectionResult and NoveltyResult
    bundled together with the FeatureVector they were computed from.
    Stage 1's orchestrator performs bundling only — no agreement/
    disagreement handling, no weighting. That combination logic is an
    explicitly open research decision, not invented here."""

    feature_vector: FeatureVector
    detection_result: DetectionResult
    novelty_result: NoveltyResult
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class RiskAssessment:
    """Output of Risk Analysis. Stage 1's risk analysis is a fixed
    placeholder — `risk_score`, `severity`, and `status` below are not a
    real risk formula and must not be read as meaningful."""

    risk_score: float
    severity: str
    status: str
    rationale: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class FinalAssessment:
    """The pipeline's end-to-end output: every intermediate artifact
    plus the final RiskAssessment, so a caller can inspect the whole
    chain a given sample traveled through."""

    raw_traffic: RawTraffic
    feature_vector: FeatureVector
    detection_result: DetectionResult
    novelty_result: NoveltyResult
    orchestration_context: OrchestrationContext
    risk_assessment: RiskAssessment
    metadata: dict[str, Any] = field(default_factory=dict)
