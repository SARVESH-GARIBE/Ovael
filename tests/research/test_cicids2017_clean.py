"""No NaN/infinite values remain after cleaning; no duplicate rows.
Checked directly against the on-disk cleaned file, streamed in chunks
(matching clean_dataset()'s own discipline) rather than loaded whole."""

import numpy as np
import pandas as pd

from _helpers import count_rows, iter_chunks, label_counts


def test_no_nan_or_infinite_values_remain(cleaned_result):
    cleaned_path, _ = cleaned_result
    for chunk in iter_chunks(cleaned_path):
        numeric_cols = chunk.select_dtypes(include=[np.number]).columns
        assert chunk[numeric_cols].isna().sum().sum() == 0
        for col in numeric_cols:
            if pd.api.types.is_float_dtype(chunk[col]):
                assert not np.isinf(chunk[col].to_numpy()).any(), col


def test_no_duplicate_rows_remain(cleaned_result):
    cleaned_path, _ = cleaned_result
    hashes = [
        pd.util.hash_pandas_object(chunk.drop(columns=["flow_id"]), index=False).to_numpy()
        for chunk in iter_chunks(cleaned_path)
    ]
    all_hashes = np.concatenate(hashes)
    assert not pd.Series(all_hashes).duplicated().any()


def test_row_identifier_is_unique(cleaned_result):
    cleaned_path, _ = cleaned_result
    ids = [chunk["flow_id"].to_numpy() for chunk in iter_chunks(cleaned_path, columns=["flow_id"])]
    all_ids = np.concatenate(ids)
    assert len(np.unique(all_ids)) == len(all_ids)


def test_cleaning_stats_are_internally_consistent(cleaned_result):
    cleaned_path, stats = cleaned_result
    assert stats["output_rows"] == count_rows(cleaned_path)
    assert (
        stats["input_rows"] - stats["rows_with_nan_or_inf"] - stats["duplicate_rows_removed"]
        == stats["output_rows"]
    )


def test_held_out_and_benign_labels_present_and_normalized(cleaned_result):
    from ml.research.datasets.cicids2017.clean import BENIGN_LABEL, HELD_OUT_LABEL

    cleaned_path, _ = cleaned_result
    labels = set(label_counts(cleaned_path).keys())
    assert BENIGN_LABEL in labels
    assert HELD_OUT_LABEL in labels
    # Raw source spellings must not survive normalization.
    assert "BENIGN" not in labels
    assert "DoS slowloris" not in labels
