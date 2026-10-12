"""Training and evaluation for one module.

The held-out split is deterministic (fixed seed over the base dataset), so every retrain is scored
on the same held-out rows. Reviewed samples from the learning loop are only ever added to the
training side. That is what makes "promote only if it beats the current model on the same held-out
set" a fair comparison.
"""

from __future__ import annotations

import hashlib
import logging
from datetime import datetime, timezone

import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest, RandomForestClassifier
from sklearn.impute import SimpleImputer
from sklearn.metrics import accuracy_score, f1_score, roc_auc_score
from sklearn.preprocessing import FunctionTransformer
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline

from ..feature_extraction import SCHEMAS
from ..orchestrator.taxonomy import is_benign_label
from .bundle import ModelBundle

log = logging.getLogger(__name__)
SEED = 42
MIN_CLASS_ROWS = 4


def _log_scale(X):
    return np.log1p(np.clip(X, 0, None))


def _auroc(neg: np.ndarray, pos: np.ndarray) -> float | None:
    if not len(neg) or not len(pos):
        return None
    return round(float(roc_auc_score(np.r_[np.zeros(len(neg)), np.ones(len(pos))], np.r_[neg, pos])), 4)


def dataset_fingerprint(df: pd.DataFrame) -> str:
    return hashlib.sha256(pd.util.hash_pandas_object(df, index=False).values.tobytes()).hexdigest()[:16]


def split(df: pd.DataFrame, test_size: float = 0.2) -> tuple[pd.DataFrame, pd.DataFrame]:
    counts = df["label"].value_counts()
    keep = df[df["label"].isin(counts[counts >= MIN_CLASS_ROWS].index)]
    dropped = sorted(set(df["label"]) - set(keep["label"]))
    if dropped:
        log.warning("classes with fewer than %d rows left out of the split: %s", MIN_CLASS_ROWS, dropped)
    train, test = train_test_split(keep, test_size=test_size, random_state=SEED, stratify=keep["label"])
    return train, test


def _xy(module: str, df: pd.DataFrame) -> tuple[pd.DataFrame, pd.Series]:
    cols = SCHEMAS[module]
    X = df.reindex(columns=cols).apply(pd.to_numeric, errors="coerce").astype(float)
    return X, df["label"].astype(str)


def cross_validated_f1(module: str, df: pd.DataFrame, folds: int = 5) -> float:
    from sklearn.model_selection import StratifiedKFold, cross_val_predict

    X, y = _xy(module, df)
    model = Pipeline([
        ("impute", SimpleImputer(strategy="median", keep_empty_features=True)),
        ("rf", RandomForestClassifier(n_estimators=200, class_weight="balanced_subsample",
                                      min_samples_leaf=2, n_jobs=-1, random_state=SEED)),
    ])
    pred = cross_val_predict(model, X, y, cv=StratifiedKFold(folds, shuffle=True, random_state=SEED))
    return round(float(f1_score(y, pred, average="macro")), 4)


def evaluate(bundle: ModelBundle, holdout: pd.DataFrame, novel: pd.DataFrame | None = None) -> dict:
    X, y = _xy(bundle.module, holdout)
    preds = bundle.predict(X.to_dict("records"))
    y_pred = [p.label for p in preds]
    anomaly = np.array([p.anomaly_score for p in preds])
    benign = y.apply(lambda v: is_benign_label(bundle.module, v)).to_numpy()
    labels = sorted(set(y))
    metrics = {
        "accuracy": round(float(accuracy_score(y, y_pred)), 4),
        "macro_f1": round(float(f1_score(y, y_pred, average="macro", labels=labels, zero_division=0)), 4),
        "per_class_f1": {c: round(float(s), 4) for c, s in zip(
            labels, f1_score(y, y_pred, average=None, labels=labels, zero_division=0))},
        "holdout_rows": int(len(holdout)),
        # Share of normal held-out rows the anomaly detector calls unusual (false alarms).
        "anomaly_false_alarm_rate": round(float((anomaly[benign] > bundle.threshold).mean()), 4) if benign.any() else None,
        # Share of attack held-out rows it calls unusual.
        "anomaly_attack_rate": round(float((anomaly[~benign] > bundle.threshold).mean()), 4) if (~benign).any() else None,
        # Threshold-free: how well the anomaly score ranks attacks above normal traffic.
        "anomaly_auroc_attacks": _auroc(anomaly[benign], anomaly[~benign]),
    }
    if novel is not None and len(novel):
        nX, _ = _xy(bundle.module, novel)
        novel_scores = bundle.anomaly_scores(nX)
        metrics["novel_detection_rate"] = round(float((novel_scores > bundle.threshold).mean()), 4)
        metrics["anomaly_auroc_unknown"] = _auroc(anomaly[benign], novel_scores)
        metrics["unknown_rows"] = int(len(novel))
    return metrics


def train_bundle(module: str, train_df: pd.DataFrame, holdout: pd.DataFrame, *, version: str,
                 threshold: float, label_source: str, novel: pd.DataFrame | None = None,
                 extra_meta: dict | None = None) -> ModelBundle:
    X, y = _xy(module, train_df)
    benign = y.apply(lambda v: is_benign_label(module, v)).to_numpy()
    if not benign.any():
        raise ValueError(f"{module}: no normal rows to train the anomaly detector on")

    classifier = Pipeline([
        ("impute", SimpleImputer(strategy="median", keep_empty_features=True)),
        ("rf", RandomForestClassifier(n_estimators=200, class_weight="balanced_subsample",
                                      min_samples_leaf=2, n_jobs=-1, random_state=SEED)),
    ])
    classifier.fit(X, y)

    # Rates and byte counts span many orders of magnitude; on a log scale the forest isolates
    # by shape instead of by a few huge values. On CIC-IDS2017 this lifted AUROC from 0.82 to
    # 0.87 for known attacks and from 0.58 to 0.71 for the held-out botnet.
    anomaly = Pipeline([
        ("impute", SimpleImputer(strategy="median", keep_empty_features=True)),
        ("log", FunctionTransformer(_log_scale, feature_names_out="one-to-one")),
        ("iforest", IsolationForest(n_estimators=200, random_state=SEED, n_jobs=-1)),
    ])
    Xb = X[benign]
    anomaly.fit(Xb)
    calibration = np.sort(-anomaly.score_samples(Xb))
    # Training uses every core; serving uses one. Per-call thread fan-out costs more than it saves
    # on request-sized batches, and the API already serves requests concurrently.
    classifier[-1].n_jobs = 1
    anomaly[-1].n_jobs = 1
    baseline = {c: float(v) for c, v in Xb.median(numeric_only=True).fillna(0).items()}

    bundle = ModelBundle(
        module=module, version=version, features=list(X.columns), classes=sorted(set(y)),
        benign_labels=sorted({v for v in y if is_benign_label(module, v)}),
        classifier=classifier, anomaly=anomaly, calibration=calibration, baseline=baseline,
        threshold=threshold,
        metadata={
            "trained_at": datetime.now(timezone.utc).isoformat(),
            "label_source": label_source,
            "train_rows": int(len(train_df)),
            "class_counts": {k: int(v) for k, v in y.value_counts().items()},
            "dataset_fingerprint": dataset_fingerprint(train_df.reindex(columns=[*X.columns, "label"])),
            **(extra_meta or {}),
        },
    )
    bundle.metadata["metrics"] = evaluate(bundle, holdout, novel)
    if len(train_df) + len(holdout) < 5000:
        # Small datasets: a single held-out split is noisy, so also report 5-fold CV.
        bundle.metadata["metrics"]["cv_macro_f1"] = cross_validated_f1(module, pd.concat([train_df, holdout]))
    log.info("trained %s: %s", version, bundle.metadata["metrics"])
    return bundle
