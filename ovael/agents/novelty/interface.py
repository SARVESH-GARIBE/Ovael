"""
Novelty Agent interface.

This ABC is the contract every Novelty Agent implementation (stub or
real) must satisfy. Stage 1 ships exactly one implementation — the
deterministic stub in stub.py. Which real algorithm eventually fills
this in (Isolation Forest, OCSVM, LOF, autoencoder, ...) is explicitly
out of scope here.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from ovael.contracts.schemas import FeatureVector, NoveltyResult


class NoveltyDetector(ABC):
    """Abstract interface for any Novelty Agent implementation."""

    @abstractmethod
    def detect(self, features: FeatureVector) -> NoveltyResult:
        """Given a FeatureVector, return a NoveltyResult."""
        raise NotImplementedError
