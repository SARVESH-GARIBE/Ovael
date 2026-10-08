"""Session-scoped fixtures so the expensive full-dataset clean/split/
featurize pass runs exactly once for the whole tests/research/ suite,
instead of once per test module.

Every fixture here produces an on-disk Parquet file (or a dict of
them), matching clean_dataset()/split_dataset()/featurize_file()'s own
streaming, file-based contract - not an in-memory dataframe. An
earlier version of this test suite held full splits in memory, which
was fine for a toy dataset but is exactly the pattern that caused an
actual OOM crash in the real pipeline; see
research/datasets/cicids2017/clean.py's module docstring. Test files
read these outputs back via tests/research/_helpers.py's chunked/
column-limited helpers, not by loading a full file into one dataframe.
"""

import pytest

from ml.research.datasets.cicids2017.clean import clean_dataset
from ml.research.datasets.cicids2017.featurize import featurize_file
from ml.research.datasets.cicids2017.split import split_dataset


@pytest.fixture(scope="session")
def cleaned_result(tmp_path_factory):
    tmp_dir = tmp_path_factory.mktemp("cleaned")
    cleaned_path, stats = clean_dataset(output_path=tmp_dir / "cleaned.parquet")
    return cleaned_path, stats


@pytest.fixture(scope="session")
def split_result(cleaned_result, tmp_path_factory):
    cleaned_path, _ = cleaned_result
    tmp_dir = tmp_path_factory.mktemp("splits")
    split_paths, split_info = split_dataset(cleaned_path, output_dir=tmp_dir)
    return split_paths, split_info


@pytest.fixture(scope="session")
def featurized_result(split_result, tmp_path_factory):
    """Runs the real featurize_file() over all three real splits once
    for the whole session - expensive (a few minutes, dominated by
    train's ~2.25M rows), but it means every test using it exercises
    the actual production-scale data through the actual streaming
    code path, not a toy subset or an in-memory shortcut."""
    split_paths, _ = split_result
    tmp_dir = tmp_path_factory.mktemp("featurized")
    featurized_paths = {}
    for name, path in split_paths.items():
        out_path = tmp_dir / f"{name}.parquet"
        featurize_file(path, out_path)
        featurized_paths[name] = out_path
    return featurized_paths
