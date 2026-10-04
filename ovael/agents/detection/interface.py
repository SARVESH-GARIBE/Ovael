"""
Detection Agent interface.

This ABC is the contract every Detection Agent implementation (stub or
real) must satisfy. Stage 1 ships exactly one implementation — the
deterministic stub in stub.py. Which real algorithm eventually fills
this in is explicitly out of scope here.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from ovael.contracts.schemas import DetectionResult, FeatureVector


class DetectionModel(ABC):
    """Abstract interface for any Detection Agent implementation."""

    @abstractmethod
    def predict(self, features: FeatureVector) -> DetectionResult:
        """Given a FeatureVector, return a DetectionResult."""
        raise NotImplementedError
