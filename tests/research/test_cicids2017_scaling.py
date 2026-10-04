"""Scaler statistics are computed from train values only - asserted
directly by independently recomputing train-only statistics (streamed,
not loaded whole - see _helpers.streaming_mean_std) and comparing, not
just by checking the scaler's effect. The same fitted parameters are
applied unchanged to test and test_unknown."""

import numpy as np
import pytest

from research.datasets.cicids2017.featurize import feature_columns
from research.datasets.cicids2017.scale import (
    apply_scaler_streaming,
    fit_scaler_streaming,
    load_scaler,
    save_scaler,
)
from _helpers import count_rows, streaming_mean_std


@pytest.fixture(scope="module")
def scaling_setup(featurized_result):
    import pyarrow.parquet as pq

    train_path = featurized_result["train"]
    all_columns = pq.ParquetFile(train_path).schema_arrow.names
    columns = [c for c in all_columns if c.startswith("feature_")]
    scaler = fit_scaler_streaming(train_path, columns)
    return featurized_result, columns, scaler


def test_scaler_mean_and_scale_match_train_only_statistics_directly(scaling_setup):
    featurized, columns, scaler = scaling_setup
    expected_mean, expected_std = streaming_mean_std(featurized["train"], columns)

    np.testing.assert_allclose(scaler.mean_, expected_mean, rtol=1e-6)
    np.testing.assert_allclose(
        scaler.scale_, np.where(expected_std == 0, 1.0, expected_std), rtol=1e-6
    )


def test_scaler_statistics_do_not_match_combined_train_and_test(scaling_setup):
    # Direct demonstration that fitting is scoped to train: a scaler
    # fit on train+test combined would see different statistics unless
    # the two distributions happen to coincide exactly. Confirms the
    # fit above is NOT accidentally equivalent to fitting on everything.
    featurized, columns, scaler = scaling_setup

    train_mean, _ = streaming_mean_std(featurized["train"], columns)
    # Approximate "train+test combined" mean via a weighted average of
    # the two independently-streamed means - avoids ever concatenating
    # the two files in memory.
    n_train = count_rows(featurized["train"])
    n_test = count_rows(featurized["test"])
    test_mean, _ = streaming_mean_std(featurized["test"], columns)
    combined_mean = (train_mean * n_train + test_mean * n_test) / (n_train + n_test)

    if not np.allclose(combined_mean, train_mean):
        assert not np.allclose(scaler.mean_, combined_mean)
    # If they do coincide (e.g. every feature column has zero variance,
    # as Stage 1's current placeholder behavior would for an empty
    # flow_features dict), there's nothing distinguishing to assert
    # here - the train-only recomputation test above is still the
    # direct, authoritative check.


def test_same_fitted_scaler_applied_unchanged_to_test_and_test_unknown(scaling_setup, tmp_path):
    featurized, columns, scaler = scaling_setup
    mean_before = scaler.mean_.copy()
    scale_before = scaler.scale_.copy()

    apply_scaler_streaming(featurized["test"], scaler, columns, tmp_path / "test_scaled.parquet")
    apply_scaler_streaming(
        featurized["test_unknown"], scaler, columns, tmp_path / "test_unknown_scaled.parquet"
    )

    np.testing.assert_array_equal(scaler.mean_, mean_before)
    np.testing.assert_array_equal(scaler.scale_, scale_before)


def test_apply_scaler_does_not_discard_unscaled_version(scaling_setup, tmp_path):
    featurized, columns, scaler = scaling_setup
    scaled_path = tmp_path / "test_unknown_scaled.parquet"

    rows_written = apply_scaler_streaming(featurized["test_unknown"], scaler, columns, scaled_path)

    assert featurized["test_unknown"].exists()  # unscaled file untouched
    assert rows_written == count_rows(featurized["test_unknown"])
    assert count_rows(scaled_path) == count_rows(featurized["test_unknown"])


def test_apply_scaler_actually_scales_the_feature_columns(scaling_setup, tmp_path):
    featurized, columns, scaler = scaling_setup
    scaled_path = tmp_path / "test_unknown_scaled.parquet"
    apply_scaler_streaming(featurized["test_unknown"], scaler, columns, scaled_path)

    scaled_mean, scaled_std = streaming_mean_std(scaled_path, columns)
    # Scaled against TRAIN's statistics, not test_unknown's own - so
    # this need not be exactly 0/1, but must differ from the raw values
    # whenever train's scale differs from a no-op (scale=1, mean=0).
    raw_mean, _ = streaming_mean_std(featurized["test_unknown"], columns)
    non_trivial = ~np.isclose(scaler.mean_, 0.0) | ~np.isclose(scaler.scale_, 1.0)
    if non_trivial.any():
        assert not np.allclose(scaled_mean[non_trivial], raw_mean[non_trivial])


def test_scaler_round_trips_through_saved_parameters(scaling_setup, tmp_path):
    featurized, columns, scaler = scaling_setup
    path = tmp_path / "scaler.json"
    save_scaler(scaler, columns, path)

    reloaded, reloaded_columns = load_scaler(path)
    assert reloaded_columns == columns
    np.testing.assert_array_equal(reloaded.mean_, scaler.mean_)
    np.testing.assert_array_equal(reloaded.scale_, scaler.scale_)

    expected_path = tmp_path / "expected.parquet"
    actual_path = tmp_path / "actual.parquet"
    apply_scaler_streaming(featurized["test_unknown"], scaler, columns, expected_path)
    apply_scaler_streaming(featurized["test_unknown"], reloaded, columns, actual_path)

    import pandas as pd

    pd.testing.assert_frame_equal(pd.read_parquet(expected_path), pd.read_parquet(actual_path))
