"""
Novelty Detector — flags flows that don't look normal, including
attack types it has never seen a label for. Uses IsolationForest,
trained ONLY on rows labelled "normal" (per feature_extraction.schema),
never on attack examples.

Training data is mock "normal" rows only (ml/mock_feature_generator.py),
NOT mixed with the KDD Cup 1999 benchmark the way the Multiclass Model
is. Tried mixing in benchmark-normal rows first: at 97k benchmark rows
vs a few hundred mock rows, the benchmark scale (KDD99's byte/duration
units, approximated through ml/benchmark_adapter.py) completely
dominated the learned "normal" region, so genuinely normal mock-schema
traffic scored as anomalous ~52% of the time. Since real captured data
will match the mock schema's scale, not KDD99's, mock-only is both
truer to the original spec and empirically the right call here. Swap in
real captured normal traffic by replacing `generate_mock_dataset()`'s
call in `train_default_model()` once the networking teammate's real
feature-extraction output exists.
"""

import os

import joblib
import numpy as np
from sklearn.ensemble import IsolationForest

from feature_extraction.schema import FeatureVector, NORMAL_LABEL, to_vector
from ml.backend_models.mock_feature_generator import generate_mock_dataset
from ml.backend_models.novelty.score_calibration import ScoreCalibrator

DEFAULT_MODEL_PATH = os.path.join(os.path.dirname(__file__), "..", "models", "novelty_model.joblib")
DEFAULT_CALIBRATOR_PATH = os.path.join(os.path.dirname(__file__), "..", "models", "novelty_calibrator.joblib")


def _split(rows: list, test_fraction: float = 0.2, seed: int = 42) -> tuple[list, list]:
    rng = np.random.default_rng(seed)
    indices = rng.permutation(len(rows))
    n_test = int(len(rows) * test_fraction)
    test_idx, train_idx = set(indices[:n_test]), set(indices[n_test:])
    train = [rows[i] for i in sorted(train_idx)]
    test = [rows[i] for i in sorted(test_idx)]
    return train, test


class NoveltyModel:
    """Wraps a fitted IsolationForest + ScoreCalibrator with the
    schema-aware predict_one() interface the backend teammate should
    call."""

    def __init__(
        self,
        classifier: IsolationForest | None = None,
        calibrator: ScoreCalibrator | None = None,
    ):
        self.classifier = classifier or IsolationForest(
            n_estimators=200, contamination="auto", random_state=42, n_jobs=-1
        )
        self.calibrator = calibrator or ScoreCalibrator()

    def fit(self, X_normal: list[list[float]]) -> "NoveltyModel":
        self.classifier.fit(X_normal)
        raw_scores = -self.classifier.score_samples(X_normal)
        self.calibrator.fit(raw_scores)
        return self

    def predict_one(self, feature_vector: FeatureVector) -> float:
        """Input: a FeatureVector matching feature_extraction.schema.
        Output: anomaly score calibrated to [0, 1] — see
        score_calibration.py for the exact definition."""
        x = [to_vector(feature_vector)]
        raw_score = -self.classifier.score_samples(x)[0]
        return self.calibrator.transform(raw_score)

    def save(
        self,
        model_path: str = DEFAULT_MODEL_PATH,
        calibrator_path: str = DEFAULT_CALIBRATOR_PATH,
    ) -> None:
        os.makedirs(os.path.dirname(model_path), exist_ok=True)
        joblib.dump(self.classifier, model_path)
        joblib.dump(self.calibrator, calibrator_path)

    @classmethod
    def load(
        cls,
        model_path: str = DEFAULT_MODEL_PATH,
        calibrator_path: str = DEFAULT_CALIBRATOR_PATH,
    ) -> "NoveltyModel":
        return cls(
            classifier=joblib.load(model_path),
            calibrator=joblib.load(calibrator_path),
        )


def train_default_model(
    model_path: str = DEFAULT_MODEL_PATH,
    calibrator_path: str = DEFAULT_CALIBRATOR_PATH,
) -> NoveltyModel:
    # Held out separately from training so the evaluation below is on
    # genuinely unseen mock-normal traffic, not points the model already
    # memorized the shape of.
    mock_normal_rows = [
        row for row in generate_mock_dataset(n_per_class=2000) if row.label == NORMAL_LABEL
    ]
    mock_normal_train, mock_normal_test = _split(mock_normal_rows)

    X_train = [to_vector(r) for r in mock_normal_train]
    model = NoveltyModel().fit(X_train)

    attack_rows = [
        row for row in generate_mock_dataset(n_per_class=200) if row.label != NORMAL_LABEL
    ]
    normal_test_scores = [model.predict_one(r) for r in mock_normal_test]
    attack_scores = [model.predict_one(r) for r in attack_rows]

    print(f"Novelty Detector trained on {len(X_train)} mock-normal flows")
    print(f"Held-out mock-normal — mean {np.mean(normal_test_scores):.3f}, "
          f"median {np.median(normal_test_scores):.3f}")
    print(f"Mock attacks         — mean {np.mean(attack_scores):.3f}, "
          f"median {np.median(attack_scores):.3f}")
    threshold = 0.95
    detection_rate = np.mean([s > threshold for s in attack_scores])
    false_positive_rate = np.mean([s > threshold for s in normal_test_scores])
    print(f"At threshold {threshold}: detection rate {detection_rate:.2%}, "
          f"false positive rate {false_positive_rate:.2%}")

    model.save(model_path, calibrator_path)
    print(f"Saved to {model_path} and {calibrator_path}")
    return model


if __name__ == "__main__":
    train_default_model()
