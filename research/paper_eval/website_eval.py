"""Part B3 (website data facts), A10 verification, and C7 (website model) for the paper eval.

Runs the actual ovael.ml.train pipeline (same RandomForestClassifier / IsolationForest / fold
settings, same seed) against the real dataset_collection crawl output. Does not alter or retrain
the bundled website-v1 model on disk: everything here is a separate, local fit.
"""
from __future__ import annotations

import json

import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest, RandomForestClassifier
from sklearn.impute import SimpleImputer
from sklearn.metrics import (
    accuracy_score, confusion_matrix, f1_score, precision_recall_fscore_support, roc_auc_score,
)
from sklearn.model_selection import StratifiedKFold, cross_val_predict
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import FunctionTransformer

from common import RESULTS_DIR, git_commit, save_csv, save_json

from ovael.config import get_settings
from ovael.feature_extraction.website_schema import LABEL_RULE_FEATURES, WEBSITE_FEATURES
from ovael.ml import datasets, labeling, train as mltrain
from ovael.orchestrator.taxonomy import is_benign_label

SEED = mltrain.SEED  # 42, read from source, not re-typed


def _log_scale(X):
    return np.log1p(np.clip(X, 0, None))


def xy(df: pd.DataFrame, cols: list[str]) -> tuple[pd.DataFrame, pd.Series]:
    X = df.reindex(columns=cols).apply(pd.to_numeric, errors="coerce").astype(float)
    return X, df["label"].astype(str)


def rf_pipeline() -> Pipeline:
    # Exactly ovael.ml.train.cross_validated_f1 / train_bundle's classifier recipe.
    return Pipeline([
        ("impute", SimpleImputer(strategy="median", keep_empty_features=True)),
        ("rf", RandomForestClassifier(n_estimators=200, class_weight="balanced_subsample",
                                      min_samples_leaf=2, n_jobs=-1, random_state=SEED)),
    ])


def cv_macro_f1(df: pd.DataFrame, cols: list[str], folds: int = 5) -> tuple[float, np.ndarray]:
    X, y = xy(df, cols)
    pred = cross_val_predict(rf_pipeline(), X, y, cv=StratifiedKFold(folds, shuffle=True, random_state=SEED))
    return round(float(f1_score(y, pred, average="macro")), 4), pred


def majority_baseline(y: pd.Series) -> dict:
    majority = y.value_counts().idxmax()
    pred = pd.Series(majority, index=y.index)
    return {
        "majority_class": majority,
        "accuracy": round(float(accuracy_score(y, pred)), 4),
        "macro_f1": round(float(f1_score(y, pred, average="macro", labels=sorted(y.unique()), zero_division=0)), 4),
    }


def full_eval(df: pd.DataFrame, label: str) -> dict:
    """Train/holdout split (same recipe as ovael.ml.train.split/train_bundle), full metrics."""
    train_df, holdout = mltrain.split(df)
    bundle = mltrain.train_bundle("website", train_df, holdout, version=f"paper_eval_{label}",
                                  threshold=get_settings().anomaly_threshold, label_source="paper_eval")
    X, y = xy(holdout, WEBSITE_FEATURES)
    preds = bundle.predict(X.to_dict("records"))
    y_pred = [p.label for p in preds]
    anomaly = np.array([p.anomaly_score for p in preds])
    benign = y.apply(lambda v: is_benign_label("website", v)).to_numpy()
    labels_sorted = sorted(set(y) | set(y_pred))
    prec, rec, f1, support = precision_recall_fscore_support(y, y_pred, labels=labels_sorted, zero_division=0)
    cm = confusion_matrix(y, y_pred, labels=labels_sorted)
    auroc_tracking = None
    if benign.any() and (~benign).any():
        auroc_tracking = round(float(roc_auc_score(
            np.r_[np.zeros(int(benign.sum())), np.ones(int((~benign).sum()))],
            np.r_[anomaly[benign], anomaly[~benign]])), 4)
    importances = bundle.classifier[-1].feature_importances_
    top10 = sorted(zip(WEBSITE_FEATURES, importances), key=lambda t: -t[1])[:10]
    return {
        "label": label,
        "train_rows": int(len(train_df)),
        "holdout_rows": int(len(holdout)),
        "accuracy": round(float(accuracy_score(y, y_pred)), 4),
        "macro_f1": round(float(f1_score(y, y_pred, average="macro", labels=labels_sorted, zero_division=0)), 4),
        "per_class": {c: {"precision": round(float(p), 4), "recall": round(float(r), 4),
                          "f1": round(float(f), 4), "support": int(s)}
                      for c, p, r, f, s in zip(labels_sorted, prec, rec, f1, support)},
        "confusion_matrix": {"labels": labels_sorted, "matrix": cm.tolist()},
        "class_counts": {k: int(v) for k, v in df["label"].value_counts().items()},
        "anomaly_false_alarm_rate": round(float((anomaly[benign] > bundle.threshold).mean()), 4) if benign.any() else None,
        "anomaly_attack_rate": round(float((anomaly[~benign] > bundle.threshold).mean()), 4) if (~benign).any() else None,
        "auroc_tracking_vs_benign": auroc_tracking,
        "top10_features": [{"feature": f, "importance": round(float(i), 5)} for f, i in top10],
        "majority_baseline": majority_baseline(y),
        "seed": SEED, "folds": 5,
    }


def main():
    settings = get_settings()
    raw = pd.read_csv(settings.website_dataset)
    status_counts = raw["crawl_status"].value_counts().to_dict()

    # ----- B3: dataset facts -----
    usable = raw[raw["crawl_status"].isin(labeling.USABLE_STATUSES)]
    labelled = labeling.label_website_dataset(raw)
    b3 = {
        "total_rows_in_csv": int(len(raw)),
        "crawl_status_counts": {k: int(v) for k, v in status_counts.items()},
        "usable_rows_by_status_only": int(len(usable)),
        "usable_rows_after_instrumentation_filter": int(len(labelled)),
        "http_error_rows_in_usable": int((labelled["crawl_status"] == "http_error").sum()),
        "label_counts": {k: int(v) for k, v in labelled["label"].value_counts().items()},
        "label_counts_per_status": {
            status: {k: int(v) for k, v in labelled[labelled["crawl_status"] == status]["label"].value_counts().items()}
            for status in labelled["crawl_status"].unique()
        },
        "training_rows_used_by_load_base": None,  # filled below
    }
    base_df, label_source = datasets.load_base("website", settings)
    b3["training_rows_used_by_load_base"] = int(len(base_df))
    b3["label_source"] = label_source
    print("B3:", json.dumps(b3, indent=2))
    save_json("B3_website_dataset_facts.json", b3)

    # ----- A10 verification: with vs without the 16 label-rule features -----
    cols_without = WEBSITE_FEATURES
    cols_with = WEBSITE_FEATURES + LABEL_RULE_FEATURES
    f1_without, _ = cv_macro_f1(base_df, cols_without)
    f1_with, _ = cv_macro_f1(base_df, cols_with)
    maj = majority_baseline(base_df["label"].astype(str))
    leakage = {
        "claim_in_website_schema_py_comment": {
            "cv_macro_f1_with_rule_features": 0.94, "cv_macro_f1_without_rule_features": 0.86,
            "majority_baseline": 0.35,
        },
        "measured": {
            "cv_macro_f1_with_rule_features": f1_with,
            "cv_macro_f1_without_rule_features": f1_without,
            "majority_baseline_accuracy": maj["accuracy"],
            "majority_baseline_macro_f1": maj["macro_f1"],
            "majority_class": maj["majority_class"],
        },
        "folds": 5, "seed": SEED, "rows": int(len(base_df)),
        "note": "majority_baseline is over the full base_df label distribution (3 classes), not "
                "per-fold; see which of accuracy/macro_f1 matches the code comment's 0.35.",
    }
    print("A10 leakage check:", json.dumps(leakage, indent=2))
    save_json("A10_website_leakage_check.json", leakage)

    # ----- C7: full held-out evaluation, with and without the 85 http_error rows -----
    c7_all = full_eval(base_df, "with_http_error_rows")
    only_success = raw[raw["crawl_status"] == "success"]
    labelled_success_only = labeling.label_website_dataset(only_success)
    c7_success_only = full_eval(labelled_success_only, "success_only")
    c7 = {"with_http_error_rows": c7_all, "success_only_rows": c7_success_only,
          "git_commit": git_commit()}
    print("C7:", json.dumps(c7, indent=2))
    save_json("C7_website_model_eval.json", c7)

    save_csv("C7_confusion_matrix_with_http_error.csv",
             pd.DataFrame(c7_all["confusion_matrix"]["matrix"],
                         index=c7_all["confusion_matrix"]["labels"],
                         columns=c7_all["confusion_matrix"]["labels"]).reset_index(names="true_label"))
    save_csv("C7_top10_features.csv", pd.DataFrame(c7_all["top10_features"]))


if __name__ == "__main__":
    main()
