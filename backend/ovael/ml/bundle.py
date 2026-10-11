"""A trained model pair (Random Forest + Isolation Forest) saved and loaded as one unit.

One bundle per module and version. Keeping both models, the feature list, the anomaly calibration
and the normal-traffic baseline together means a version can never be loaded with the wrong
feature order or the wrong calibration.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

import numpy as np
import pandas as pd
from sklearn.pipeline import Pipeline

from ..feature_extraction import describe

log = logging.getLogger(__name__)


@dataclass
class Prediction:
    label: str
    confidence: float
    anomaly_score: float
    probabilities: dict[str, float]


@dataclass
class ModelBundle:
    module: str
    version: str
    features: list[str]
    classes: list[str]
    benign_labels: list[str]
    classifier: Pipeline  # imputer -> RandomForestClassifier
    anomaly: Pipeline  # imputer -> IsolationForest (trained on normal behaviour only)
    calibration: np.ndarray  # sorted raw anomaly scores of normal training rows
    baseline: dict[str, float]  # median of each feature over normal training rows
    threshold: float
    metadata: dict = field(default_factory=dict)
    _explainer: object | None = field(default=None, repr=False, compare=False)

    # ------------------------------------------------------------------ inference
    def frame(self, rows: list[dict]) -> pd.DataFrame:
        df = pd.DataFrame([{f: r.get(f) for f in self.features} for r in rows], columns=self.features)
        return df.apply(pd.to_numeric, errors="coerce").astype(float)

    def anomaly_scores(self, X: pd.DataFrame) -> np.ndarray:
        raw = -self.anomaly.score_samples(X)  # higher = more unusual
        # Percentile against normal training traffic: 0.97 means "more unusual than 97% of the
        # normal flows the detector learned from".
        return np.searchsorted(self.calibration, raw, side="right") / len(self.calibration)

    def predict(self, rows: list[dict]) -> list[Prediction]:
        X = self.frame(rows)
        proba = self.classifier.predict_proba(X)
        classes = list(self.classifier.classes_)
        anomaly = self.anomaly_scores(X)
        out = []
        for i in range(len(rows)):
            j = int(np.argmax(proba[i]))
            out.append(Prediction(
                label=classes[j], confidence=float(proba[i, j]), anomaly_score=float(anomaly[i]),
                probabilities={c: round(float(p), 4) for c, p in zip(classes, proba[i]) if p >= 0.01},
            ))
        return out

    # ------------------------------------------------------------------ explanation
    def _get_explainer(self):
        if self._explainer is None:
            import shap  # heavy import, only when an explanation is requested

            self._explainer = shap.TreeExplainer(self.classifier[-1])
        return self._explainer

    def explain(self, row: dict, label: str, top_k: int = 6) -> list[dict]:
        X = self.frame([row])
        Xi = pd.DataFrame(self.classifier[:-1].transform(X), columns=self.features)
        classes = list(self.classifier.classes_)
        k = classes.index(label) if label in classes else 0
        try:
            sv = self._get_explainer().shap_values(Xi, check_additivity=False)
            if isinstance(sv, list):  # older SHAP: one array per class
                contrib = np.asarray(sv[k])[0]
            else:
                arr = np.asarray(sv)
                contrib = arr[0, :, k] if arr.ndim == 3 else arr[0]
            method = "shap"
        except Exception as exc:  # SHAP unavailable or failed: importance x deviation fallback
            log.warning("SHAP failed (%s); using importance fallback", exc)
            imp = self.classifier[-1].feature_importances_
            base = np.array([self.baseline.get(f, 0.0) for f in self.features])
            scale = np.abs(base) + 1.0
            contrib = imp * (Xi.iloc[0].to_numpy() - base) / scale
            method = "importance"
        order = np.argsort(-np.abs(contrib))[:top_k]
        return [{
            "feature": self.features[i],
            "description": describe(self.module, self.features[i]),
            "value": _clean(Xi.iloc[0, i]),
            "baseline": _clean(self.baseline.get(self.features[i])),
            "contribution": round(float(contrib[i]), 5),
            "method": method,
        } for i in order if abs(contrib[i]) > 0]

    def summary(self) -> dict:
        return {"module": self.module, "version": self.version, "classes": self.classes,
                "features": len(self.features), "threshold": self.threshold, **self.metadata}


def _clean(v) -> float | None:
    if v is None:
        return None
    v = float(v)
    return None if np.isnan(v) else round(v, 4)
