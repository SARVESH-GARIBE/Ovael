"""
STUB — Novelty Agent.

Deterministic dummy output only. No real novelty/anomaly algorithm is
selected or implemented here — that choice is explicit future work.
The output is intentionally and visibly fake so nothing downstream can
mistake it for a real novelty assessment.
"""

from __future__ import annotations

from ovael.agents.novelty.interface import NoveltyDetector
from ovael.contracts.schemas import FeatureVector, NoveltyResult

PLACEHOLDER_IS_NOVEL = False
PLACEHOLDER_NOVELTY_SCORE = 0.0


class StubNoveltyDetector(NoveltyDetector):
    """Always returns the same obviously-fake NoveltyResult, regardless
    of input."""

    def detect(self, features: FeatureVector) -> NoveltyResult:
        return NoveltyResult(
            is_novel=PLACEHOLDER_IS_NOVEL,
            novelty_score=PLACEHOLDER_NOVELTY_SCORE,
            model_name="StubNoveltyDetector",
            metadata={"stub": True},
        )
