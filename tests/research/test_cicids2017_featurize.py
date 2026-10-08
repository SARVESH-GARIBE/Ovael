"""The row -> RawTraffic -> FeatureVector path actually calls
ovael.ingestion.extract_features() - not a reimplementation."""

import ovael.ingestion.feature_extraction as real_module
import ml.research.datasets.cicids2017.featurize as featurize_module
from ovael.ingestion.feature_extraction import extract_features as real_extract_features
from ml.research.datasets.cicids2017.featurize import (
    feature_columns,
    featurize_split,
    row_to_raw_traffic,
)
from _helpers import count_rows, label_counts, read_first_row


def test_featurize_module_imports_the_real_function_object():
    # Strongest possible proof of reuse rather than reimplementation:
    # the exact same function object, not a lookalike with the same name.
    assert featurize_module.extract_features is real_extract_features
    assert featurize_module.extract_features is real_module.extract_features


def test_featurized_output_matches_calling_extract_features_directly(split_result, featurized_result):
    split_paths, _ = split_result
    sample_row = read_first_row(split_paths["test_unknown"])

    feature_cols = [c for c in sample_row.index if c not in featurize_module.NON_FEATURE_COLUMNS]
    raw_traffic = row_to_raw_traffic(sample_row, feature_cols)
    direct_result = real_extract_features(raw_traffic)

    produced_row = read_first_row(featurized_result["test_unknown"])
    assert produced_row["source_ip"] == direct_result.source_ip
    assert produced_row["destination_ip"] == direct_result.destination_ip
    assert produced_row["source_port"] == direct_result.source_port
    assert produced_row["destination_port"] == direct_result.destination_port
    assert produced_row["protocol"] == direct_result.protocol
    assert produced_row["payload_size"] == direct_result.payload_size
    assert produced_row["timestamp"] == direct_result.timestamp
    for name, value in direct_result.features.items():
        assert produced_row[f"feature_{name}"] == value


def test_feature_columns_match_extract_features_output_keys(split_result):
    split_paths, _ = split_result
    sample_row = read_first_row(split_paths["test_unknown"])
    feature_cols = [c for c in sample_row.index if c not in featurize_module.NON_FEATURE_COLUMNS]
    direct_result = real_extract_features(row_to_raw_traffic(sample_row, feature_cols))

    import pandas as pd

    small_input = pd.read_parquet(split_paths["test_unknown"]).iloc[:5]
    out = featurize_split(small_input)
    assert feature_columns(out) == [f"feature_{k}" for k in direct_result.features]


def test_featurized_split_retains_label_and_row_count(split_result, featurized_result):
    split_paths, _ = split_result
    for name in split_paths:
        assert count_rows(featurized_result[name]) == count_rows(split_paths[name])
        assert label_counts(featurized_result[name]) == label_counts(split_paths[name])
