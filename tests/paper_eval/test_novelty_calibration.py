"""Locks in A4: a(x) is a percentile rank in [0, 1] against the training-benign calibration set,
and flags about 1% of that same calibration set at tau = 0.99 (by construction of the percentile
definition in ovael/ml/bundle.py). Uses the real train_bundle() on the project's own synthetic
generator - no real/CICIDS2017 data needed for this check.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from ovael.feature_extraction import SCHEMAS
from ovael.ml import synthetic, train as mltrain


def _xy(df: pd.DataFrame) -> pd.DataFrame:
    return df.reindex(columns=SCHEMAS["network"]).apply(pd.to_numeric, errors="coerce").astype(float)


def _bundle():
    df = synthetic.generate(n_per_class=400, seed=11)
    train_df, holdout = mltrain.split(df)
    return mltrain.train_bundle("network", train_df, holdout, version="paper_eval_calib",
                                threshold=0.99, label_source="paper_eval"), train_df


def test_percentile_rank_is_in_0_1():
    bundle, train_df = _bundle()
    X = _xy(train_df)
    scores = bundle.anomaly_scores(X)
    assert (scores >= 0.0).all() and (scores <= 1.0).all()


def test_tau_0_99_flags_about_one_percent_of_the_benign_calibration_set():
    bundle, _ = _bundle()
    # The calibration array *is* the sorted raw scores of the benign training rows (ml/train.py);
    # scoring those same rows back through anomaly_scores() must reproduce ~1% above tau=0.99,
    # since the percentile is defined as rank-within-calibration.
    from ovael.orchestrator.taxonomy import is_benign_label

    df = synthetic.generate(n_per_class=2000, seed=11)
    train_df, holdout = mltrain.split(df)
    bundle = mltrain.train_bundle("network", train_df, holdout, version="paper_eval_calib2",
                                  threshold=0.99, label_source="paper_eval")
    benign_train = train_df[train_df["label"].apply(lambda v: is_benign_label("network", v))]
    X = _xy(benign_train)
    scores = bundle.anomaly_scores(X)
    flagged_rate = float((scores > 0.99).mean())
    assert abs(flagged_rate - 0.01) <= 0.01, f"flagged {flagged_rate:.4f} of benign calibration rows, expected ~0.01"
