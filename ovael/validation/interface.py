"""
Validation — architectural placeholder ONLY.

This establishes where Validation will plug in later (e.g. confirming a
flagged/hard sample against ground truth before it feeds back into
learning). There is no concrete implementation here, and this interface
is NOT wired into ovael/pipeline/pipeline.py — Stage 1's pipeline does
not call Validation at all.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class Validator(ABC):
    """Abstract placeholder for a future Validation component."""

    @abstractmethod
    def validate(self, *args: Any, **kwargs: Any) -> Any:
        """Signature intentionally unconstrained: what Validation
        consumes and produces is not decided in Stage 1."""
        raise NotImplementedError
