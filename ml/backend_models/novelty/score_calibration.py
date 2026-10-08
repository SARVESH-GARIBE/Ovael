"""
Converts IsolationForest's raw anomaly score into a 0-1 percentile
relative to the training distribution of normal traffic.

Convention: raw anomaly score = -classifier.score_samples(X), so higher
always means "more anomalous" (score_samples itself is the opposite:
higher = more normal). The calibrated percentile answers "what fraction
of normal training flows looked at least this anomalous?" — 0.99 means
this flow is more anomalous than 99% of known-normal traffic.
"""

import numpy as np


class ScoreCalibrator:
    def __init__(self):
        self._sorted_training_scores: np.ndarray | None = None

    def fit(self, raw_anomaly_scores: np.ndarray) -> "ScoreCalibrator":
        self._sorted_training_scores = np.sort(raw_anomaly_scores)
        return self

    def transform(self, raw_anomaly_score: float) -> float:
        if self._sorted_training_scores is None:
            raise RuntimeError("ScoreCalibrator must be fit() before transform()")
        rank = np.searchsorted(self._sorted_training_scores, raw_anomaly_score)
        return float(rank) / len(self._sorted_training_scores)
