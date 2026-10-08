"""DoS Slowloris has ZERO rows in train; it appears only in test and
test_unknown; no row appears in more than one split; class distribution
in train/test matches the configured stratification within tolerance;
test_unknown contains ONLY DoS Slowloris + Benign.

These guarantees are about SET MEMBERSHIP (which flow_ids land in
which split), so they're checked the same way regardless of whether
the splits are in-memory dataframes or on-disk files: flow_id_set()
reads only the flow_id column (a few tens of MB at this dataset's
scale), and label_counts() only the label column - neither loads a
split's 79 feature columns."""

from ml.research.datasets.cicids2017.clean import BENIGN_LABEL, HELD_OUT_LABEL
from ml.research.datasets.cicids2017.split import TEST_FRACTION
from _helpers import count_rows, flow_id_set, label_counts


def test_held_out_class_has_zero_rows_in_train(split_result):
    split_paths, _ = split_result
    assert label_counts(split_paths["train"]).get(HELD_OUT_LABEL, 0) == 0


def test_held_out_class_appears_in_test_and_test_unknown(split_result):
    split_paths, _ = split_result
    assert label_counts(split_paths["test"]).get(HELD_OUT_LABEL, 0) > 0
    assert label_counts(split_paths["test_unknown"]).get(HELD_OUT_LABEL, 0) > 0


def test_no_row_appears_in_more_than_one_split(split_result):
    split_paths, _ = split_result
    ids = {name: flow_id_set(path) for name, path in split_paths.items()}
    names = list(ids)
    for i, a in enumerate(names):
        for b in names[i + 1 :]:
            assert ids[a].isdisjoint(ids[b]), f"{a} and {b} share rows"


def test_splits_partition_the_cleaned_dataset_exactly(cleaned_result, split_result):
    cleaned_path, _ = cleaned_result
    split_paths, _ = split_result
    union: set[int] = set()
    total = 0
    for name, path in split_paths.items():
        ids = flow_id_set(path)
        total += len(ids)
        union |= ids
    assert total == len(union)  # no row double-counted across splits
    assert total == count_rows(cleaned_path)
    assert union == flow_id_set(cleaned_path)


def test_test_unknown_contains_only_held_out_and_benign(split_result):
    split_paths, _ = split_result
    labels = set(label_counts(split_paths["test_unknown"]).keys())
    assert labels == {HELD_OUT_LABEL, BENIGN_LABEL}


def test_test_unknown_is_an_equal_pairing(split_result):
    split_paths, info = split_result
    counts = label_counts(split_paths["test_unknown"])
    assert counts[HELD_OUT_LABEL] == counts[BENIGN_LABEL] == info["test_unknown_pair_count"]


def test_stratification_matches_test_fraction_within_tolerance(cleaned_result, split_result):
    cleaned_path, _ = cleaned_result
    split_paths, _ = split_result
    tolerance = 0.02  # absolute, e.g. 0.20 +/- 0.02

    cleaned_counts = label_counts(cleaned_path)
    test_counts = label_counts(split_paths["test"])

    # Held-out and Benign have test_unknown carve-outs on top of the
    # ordinary test_fraction, so only ordinary classes are checked here.
    ordinary_labels = set(cleaned_counts) - {HELD_OUT_LABEL, BENIGN_LABEL}
    for label in ordinary_labels:
        observed_fraction = test_counts.get(label, 0) / cleaned_counts[label]
        assert abs(observed_fraction - TEST_FRACTION) <= tolerance, label


def test_split_is_reproducible_with_the_same_seed(cleaned_result, tmp_path_factory):
    from ml.research.datasets.cicids2017.split import split_dataset

    cleaned_path, _ = cleaned_result
    paths_a, _ = split_dataset(
        cleaned_path, seed=123, output_dir=tmp_path_factory.mktemp("repro_a")
    )
    paths_b, _ = split_dataset(
        cleaned_path, seed=123, output_dir=tmp_path_factory.mktemp("repro_b")
    )
    for name in paths_a:
        assert flow_id_set(paths_a[name]) == flow_id_set(paths_b[name])
