"""
Multiclass Model — classifies a flow's feature vector using a
RandomForestClassifier.

Predicts every label in feature_extraction.schema.LABELS (normal, ddos,
port_scan, exfiltration). It was briefly binary (normal/ddos) in Phase 1,
which silently mislabeled other attack types as ddos.

Training data is mock data (ml/mock_feature_generator.py, matches the
schema exactly) combined with the KDD Cup 1999 benchmark, adapted onto
the schema by ml/benchmark_adapter.py (approximate — see that module's
docstring), filtered down to TARGET_LABELS. Swap in real
captured data by replacing `generate_mock_dataset(...)`'s call in
`load_training_data()` with the networking teammate's real
feature-extraction output once it exists; nothing else needs to change
since both already conform to the same FeatureVector schema.
"""

import os

import joblib
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import accuracy_score, classification_report, confusion_matrix
from sklearn.model_selection import train_test_split

from feature_extraction.schema import LABELS, FeatureVector, to_vector
from ml.backend_models.benchmark_adapter import load_kddcup99_as_feature_vectors
from ml.backend_models.mock_feature_generator import generate_mock_dataset

DEFAULT_MODEL_PATH = os.path.join(os.path.dirname(__file__), "..", "models", "multiclass_model.joblib")

TARGET_LABELS = LABELS


def load_training_data(
    n_mock_per_class: int = 300, target_labels: tuple[str, ...] = TARGET_LABELS
) -> tuple[list[list[float]], list[str]]:
    """Combine mock + benchmark FeatureVectors into (X, y) ready for
    scikit-learn, restricted to target_labels."""
    rows = generate_mock_dataset(n_per_class=n_mock_per_class)
    rows += load_kddcup99_as_feature_vectors()
    rows = [row for row in rows if row.label in target_labels]

    X = [to_vector(row) for row in rows]
    y = [row.label for row in rows]
    return X, y


class MulticlassModel:
    """Wraps a fitted RandomForestClassifier with the schema-aware
    predict_one() interface the backend teammate should call."""

    def __init__(self, classifier: RandomForestClassifier | None = None):
        self.classifier = classifier or RandomForestClassifier(
            n_estimators=200, random_state=42, n_jobs=-1
        )

    def fit(self, X: list[list[float]], y: list[str]) -> "MulticlassModel":
        self.classifier.fit(X, y)
        return self

    def predict_one(self, feature_vector: FeatureVector) -> tuple[str, float]:
        """Input: a FeatureVector matching feature_extraction.schema.
        Output: (label, confidence) where confidence is the predicted
        class's probability."""
        x = [to_vector(feature_vector)]
        probs = self.classifier.predict_proba(x)[0]
        best_idx = probs.argmax()
        label = str(self.classifier.classes_[best_idx])
        confidence = float(probs[best_idx])
        return label, confidence

    def save(self, path: str = DEFAULT_MODEL_PATH) -> None:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        joblib.dump(self.classifier, path)

    @classmethod
    def load(cls, path: str = DEFAULT_MODEL_PATH) -> "MulticlassModel":
        return cls(classifier=joblib.load(path))


def train_default_model(save_path: str = DEFAULT_MODEL_PATH) -> MulticlassModel:
    X, y = load_training_data()
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=42, stratify=y
    )

    model = MulticlassModel().fit(X_train, y_train)

    y_pred = model.classifier.predict(X_test)
    labels = model.classifier.classes_
    print(f"Multiclass Model accuracy: {accuracy_score(y_test, y_pred):.4f}")
    print(classification_report(y_test, y_pred, zero_division=0))
    print(f"Confusion matrix (rows=true, cols=predicted, order={list(labels)}):")
    print(confusion_matrix(y_test, y_pred, labels=labels))

    model.save(save_path)
    print(f"Saved to {save_path}")
    return model


if __name__ == "__main__":
    train_default_model()
