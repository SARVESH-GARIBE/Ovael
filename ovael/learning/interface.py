"""
Learning — architectural placeholder ONLY.

This establishes where Learning will plug in later (e.g. retraining
from validated hard examples). There is no concrete implementation
here, and this interface is NOT wired into ovael/pipeline/pipeline.py —
Stage 1's pipeline does not call Learning at all.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class Learner(ABC):
    """Abstract placeholder for a future Learning component."""

    @abstractmethod
    def learn(self, *args: Any, **kwargs: Any) -> Any:
        """Signature intentionally unconstrained: what Learning
        consumes and produces is not decided in Stage 1."""
        raise NotImplementedError
