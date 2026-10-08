"""
Produces the 3-way split used by the held-out/novelty-recovery
experiment:

- train:        every class EXCEPT the held-out class (clean.HELD_OUT_LABEL
                 = "DoS Slowloris"). Zero held-out-class rows.
- test:         every class, held-out class included - a realistic,
                 proportionally-sampled test set where a chunk of the
                 held-out class's rows are mixed in with everything else.
- test_unknown: a controlled open-set probe: the REMAINING held-out-class
                 rows, paired with an equal number of randomly sampled
                 Benign rows that appear nowhere else.

One rule applied uniformly to every class (including the held-out one):
a fixed fraction (TEST_FRACTION) of its rows goes to "test", shuffled
with a fixed seed (SEED) so the split is exactly reproducible. The
difference for the held-out class is only where its OTHER fraction
goes: for every other class that's "train"; for the held-out class
there is no train allocation at all, so that fraction goes to
test_unknown instead, alongside a matching, disjointly-carved-out slice
of Benign.

This guarantees, by construction:
- Zero held-out-class rows in train.
- No row belongs to more than one split (every row is drawn from a
  one-time random permutation of its own class's rows and assigned to
  exactly one destination array slice; nothing is sampled twice).

On-disk, two-pass implementation (this replaces an earlier in-memory
version that did the same thing via pandas .groupby()/.sample() over
one big dataframe, which required holding the full ~2.8M-row cleaned
dataset in memory):

  Pass 1 (light): read ONLY the flow_id and label columns from the
  cleaned Parquet file - a couple of small columns, not the 79 feature
  columns - and compute the identical sequence of random decisions the
  original in-memory algorithm made. This works because
  rng.permutation(n) only depends on a class's ROW COUNT and the rng's
  position in its call sequence, not on the feature values themselves;
  reading flow_id/label in the file's natural row order and grouping
  by first-seen label (matching pandas' groupby(sort=False) order)
  reproduces that exact call sequence, so for the SAME seed this
  produces the SAME flow_id -> split assignment as the original
  algorithm, bit for bit.

  Pass 2 (heavy data, streamed): read the full cleaned file again in
  chunks, look up each row's precomputed destination via a sorted-array
  search (vectorized, not a per-row Python loop), and append it to the
  corresponding train/test/test_unknown output Parquet file. No full
  split, or the full cleaned dataset, is ever held in memory - only the
  int64 flow_id arrays from pass 1 (tens of MB) and one chunk's worth
  of rows at a time in pass 2.

One documented behavior change from the in-memory version, called out
rather than silently dropped: the in-memory version additionally
shuffled each split's final ROW ORDER (`.sample(frac=1, ...)`) after
assembling it. That was never part of the split's actual guarantees
(which are about which rows land in which split, not what order they
appear in) - its own comment said as much - but reproducing it exactly
here would mean either buffering a whole split in memory to shuffle
it, or random-access rereads of the source file, both of which defeat
the point of this rewrite. Rows within a split now appear in the
cleaned file's own chunk order, filtered down to that split - every
leakage/stratification/reproducibility guarantee below is about SET
membership, and is unaffected.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq

from ml.research.datasets.cicids2017.clean import BENIGN_LABEL, DEFAULT_CLEANED_PATH, HELD_OUT_LABEL
from ml.research.datasets.cicids2017.download import REPO_ROOT

SEED = 42
TEST_FRACTION = 0.2
SPLIT_NAMES = ("train", "test", "test_unknown")
DEFAULT_SPLIT_DIR = REPO_ROOT / "data" / "processed" / "cicids2017" / "_intermediate"


def _shuffle_split_indices(
    n: int, rng: np.random.Generator, test_fraction: float
) -> tuple[np.ndarray, np.ndarray]:
    """Same algorithm as the original in-memory version: a single
    rng.permutation(n) call, split at round(n * test_fraction). Returns
    POSITION indices into whatever length-n array the caller applies
    them to, rather than slicing a dataframe - this is what lets the
    identical decision be computed from just a class's row count."""
    idx = rng.permutation(n)
    n_test = round(n * test_fraction)
    return idx[:n_test], idx[n_test:]


def _collect_flow_ids_by_label(cleaned_path: Path) -> dict[str, np.ndarray]:
    """Lightweight pass: reads only flow_id and label (not the 79
    feature columns) and groups flow_ids by label, preserving each
    label's first-seen order across the file - matching pandas'
    groupby(sort=False) semantics, which the random-decision sequence
    depends on."""
    parquet_file = pq.ParquetFile(cleaned_path)
    by_label: dict[str, list[np.ndarray]] = {}
    for record_batch in parquet_file.iter_batches(batch_size=200_000, columns=["flow_id", "label"]):
        chunk = record_batch.to_pandas()
        for label, group in chunk.groupby("label", sort=False, observed=True):
            by_label.setdefault(str(label), []).append(group["flow_id"].to_numpy())
    return {label: np.concatenate(arrays) for label, arrays in by_label.items()}


def _compute_split_assignment(
    flow_ids_by_label: dict[str, np.ndarray],
    seed: int,
    test_fraction: float,
) -> tuple[dict[str, np.ndarray], dict]:
    """Runs the exact same sequence of rng calls as the original
    in-memory algorithm - held-out class first, then Benign, then
    every other class in first-seen order - and returns the resulting
    {"train"/"test"/"test_unknown": flow_id array}, plus the same
    split_info shape the old in-memory split_dataset() returned."""
    rng = np.random.default_rng(seed)

    heldout_ids = flow_ids_by_label.get(HELD_OUT_LABEL, np.array([], dtype=np.int64))
    benign_ids = flow_ids_by_label[BENIGN_LABEL]
    other_labels = [l for l in flow_ids_by_label if l not in (HELD_OUT_LABEL, BENIGN_LABEL)]

    class_counts: dict[str, dict[str, int]] = {name: {} for name in SPLIT_NAMES}
    assignment: dict[str, list[np.ndarray]] = {name: [] for name in SPLIT_NAMES}

    def _record(name: str, label: str, ids: np.ndarray) -> None:
        assignment[name].append(ids)
        class_counts[name][label] = class_counts[name].get(label, 0) + len(ids)

    test_idx, unknown_idx = _shuffle_split_indices(len(heldout_ids), rng, test_fraction)
    _record("test", HELD_OUT_LABEL, heldout_ids[test_idx])
    _record("test_unknown", HELD_OUT_LABEL, heldout_ids[unknown_idx])
    n_pair = len(unknown_idx)

    unknown_idx_b, remaining_idx_b = _shuffle_split_indices(
        len(benign_ids), rng, n_pair / len(benign_ids)
    )
    benign_remaining_ids = benign_ids[remaining_idx_b]
    _record("test_unknown", BENIGN_LABEL, benign_ids[unknown_idx_b])

    test_idx_b, train_idx_b = _shuffle_split_indices(len(benign_remaining_ids), rng, test_fraction)
    _record("train", BENIGN_LABEL, benign_remaining_ids[train_idx_b])
    _record("test", BENIGN_LABEL, benign_remaining_ids[test_idx_b])

    for label in other_labels:
        ids = flow_ids_by_label[label]
        test_idx_o, train_idx_o = _shuffle_split_indices(len(ids), rng, test_fraction)
        _record("test", label, ids[test_idx_o])
        _record("train", label, ids[train_idx_o])

    flow_id_assignment = {
        name: (np.concatenate(parts) if parts else np.array([], dtype=np.int64))
        for name, parts in assignment.items()
    }

    split_info = {
        "seed": seed,
        "test_fraction": test_fraction,
        "held_out_label": HELD_OUT_LABEL,
        "benign_label": BENIGN_LABEL,
        "test_unknown_pair_count": n_pair,
        "row_counts": {name: len(ids) for name, ids in flow_id_assignment.items()},
        "class_counts": class_counts,
    }
    return flow_id_assignment, split_info


def _route_rows_to_splits(
    cleaned_path: Path, flow_id_assignment: dict[str, np.ndarray], output_dir: Path
) -> dict[str, Path]:
    """Streams the cleaned file in chunks and appends each row to the
    Parquet file for its precomputed destination split. Destination
    lookup is a single vectorized sorted-array search per chunk, not a
    per-row Python loop."""
    all_ids = np.concatenate([flow_id_assignment[name] for name in SPLIT_NAMES])
    dest_codes = np.concatenate(
        [np.full(len(flow_id_assignment[name]), code, dtype=np.int8) for code, name in enumerate(SPLIT_NAMES)]
    )
    order = np.argsort(all_ids)
    sorted_ids = all_ids[order]
    sorted_codes = dest_codes[order]

    output_dir.mkdir(parents=True, exist_ok=True)
    output_paths = {name: output_dir / f"{name}_clean.parquet" for name in SPLIT_NAMES}
    writers: dict[str, pq.ParquetWriter] = {}

    try:
        parquet_file = pq.ParquetFile(cleaned_path)
        for record_batch in parquet_file.iter_batches(batch_size=200_000):
            table = pa.Table.from_batches([record_batch])
            chunk_ids = table.column("flow_id").to_numpy(zero_copy_only=False)
            positions = np.searchsorted(sorted_ids, chunk_ids)
            codes = sorted_codes[positions]

            for code, name in enumerate(SPLIT_NAMES):
                subset = table.filter(pa.array(codes == code))
                if subset.num_rows == 0:
                    continue
                if name not in writers:
                    writers[name] = pq.ParquetWriter(str(output_paths[name]), subset.schema)
                writers[name].write_table(subset)
    finally:
        for writer in writers.values():
            writer.close()

    return output_paths


def split_dataset(
    cleaned_path: Path = DEFAULT_CLEANED_PATH,
    seed: int = SEED,
    test_fraction: float = TEST_FRACTION,
    output_dir: Path = DEFAULT_SPLIT_DIR,
) -> tuple[dict[str, Path], dict]:
    """Returns ({"train": path, "test": path, "test_unknown": path}, split_info)."""
    flow_ids_by_label = _collect_flow_ids_by_label(cleaned_path)
    flow_id_assignment, split_info = _compute_split_assignment(
        flow_ids_by_label, seed, test_fraction
    )
    output_paths = _route_rows_to_splits(cleaned_path, flow_id_assignment, output_dir)
    return output_paths, split_info
