# Stage 2 — CICIDS2017 Dataset Integration

An offline research pipeline that downloads, cleans, and splits CIC-IDS-2017
into a 3-way split (train / test / test_unknown) for the planned held-out
novelty experiment: DoS Slowloris is held out of training, so a later
novelty mechanism's recall on it can be measured against the reported
baseline on the same class.

This stage does not select or train any Detection or Novelty algorithm.

## Running it

```bash
pip install -e ".[research]"   # huggingface_hub, pandas, pyarrow, scikit-learn, pyyaml
PYTHONPATH=. python -m research.datasets.cicids2017.pipeline
```

The raw file is downloaded to `data/raw/cicids2017/` on first run and reused
afterwards. Outputs are written to `data/processed/cicids2017/`:

```
train.parquet            train_scaled.parquet
test.parquet             test_scaled.parquet
test_unknown.parquet     test_unknown_scaled.parquet
scaler.json
manifest.yaml
```

Scratch files (`_intermediate/`: the cleaned dataset and the per-split
pre-featurization files) are deleted once the run succeeds. None are kept.
Nothing under `data/` is committed (`.gitignore` covers it).

## How data moves through the pipeline

Every stage streams through on-disk Parquet in bounded chunks. No stage
holds the full dataset (or a full split) in memory.

1. **clean** (`clean.py`) reads the raw source in 200k-row batches, drops NaN/Inf
   rows, and writes survivors to `_intermediate/cleaned.parquet` through an
   incremental `ParquetWriter`. Duplicate detection uses an int64 content hash
   plus an int64 flow_id per row, which is tens of MB for the full dataset.
2. **split** (`split.py`) runs two passes over the cleaned file. Pass 1 reads
   only `flow_id` and `label` to decide each row's split. Pass 2 streams the
   full file and appends each row to its split's file.
3. **featurize** (`featurize.py`) streams each split file in 20k-row chunks.
   Each row becomes a `RawTraffic` (with its flow statistics in
   `flow_features`), which is passed to the real
   `ovael.ingestion.feature_extraction.extract_features()`.
4. **scale** (`scale.py`) fits a `StandardScaler` on the train file via
   `partial_fit` over chunks, then applies it chunk by chunk to all three
   splits.

## Feature set (79 features)

`RawTraffic.flow_features` carries these 79 values per row. Stage 1's
`extract_features()` passes them through to `FeatureVector.features` unchanged.

**Kept (79).** Every numeric CICFlowMeter column in the source except the
exclusions below, snake_cased by rule rather than from a hand-picked list:
packet count and length statistics (forward and backward), inter-arrival-time
statistics, flag counts, window sizes, subflow statistics, idle and active
time statistics, `source_port`, `destination_port`, and `protocol_num`. Protocol
is re-encoded numerically (`tcp`=6, `udp`=17, `other`=0), since this source
already decodes it to strings.

**Excluded.**
- `flow_id`: an identifier, used only for dedup and leakage checks.
- `source_ip`, `destination_ip`: non-numeric identifiers.
- raw `Timestamp`: not a feature. It is kept as a separate parsed
  `timestamp` (epoch seconds) for ordering and debugging.
- `attack_label`: handled by the split routing and never fed to a model.
- raw `protocol` string: replaced by the numeric `protocol_num` feature.

The `RawTraffic` identity fields (`source_port`, `destination_port`,
`payload_size`, `protocol`, `timestamp`) are still set from the row. `source_port`
and `destination_port` also appear among the 79 features, as the same values.
`payload_size` is `total_length_of_fwd_packets + total_length_of_bwd_packets`.

## Label normalization

The raw source spells the held-out class `"DoS slowloris"`. It is normalized to
`"DoS Slowloris"` (and `BENIGN` to `Benign`) during cleaning, so the split logic
matches the canonical name.

## The 3-way split and its guarantees

- **train**: every class except DoS Slowloris. Zero held-out rows.
- **test**: every class, DoS Slowloris included, each class split at the fixed
  `TEST_FRACTION = 0.2` using the fixed `SEED = 42`.
- **test_unknown**: the held-out class's remaining rows, paired 1:1 with an equal
  number of Benign rows that appear nowhere else.

Split membership is identical to the earlier in-memory algorithm. It was
verified by reconstructing that algorithm and comparing flow_id sets exactly
for all three splits. The on-disk version replays the same sequence of random
draws, so the same seed gives the same assignment.

One intentional change: the in-memory version shuffled each split's final row
order. The streaming version keeps rows in source-chunk order. The guarantees
are about set membership, so they are unaffected.

Verified by the tests in `tests/research/`:
- No row (by `flow_id`) is in more than one split.
- The splits together cover the cleaned dataset exactly.
- Stratification is within tolerance, and test_unknown is an equal Slowloris/Benign pairing.
- Reproducibility with the same seed.
- Zero held-out rows in train.
- The scaler's mean and scale match an independent streamed recomputation from
  train alone. The same fitted parameters are applied to test and test_unknown.

## Memory

Measured on this machine (~7 GB RAM, shared with other processes):

| Run | Result |
|---|---|
| Earlier all-in-memory pipeline (full run) | OOM kill |
| Streaming pipeline (full run) | completed; RSS sampled every 10 s stayed roughly 0.8–1.5 GB |
| clean alone (streaming) | ~1.4 GB peak RSS |
| featurize, 1M rows | ~1.9 GB peak (earlier in-memory per-row version was far higher) |

## Interim source, pending the official dataset

The current source is the Hugging Face mirror `rdpahalavan/CIC-IDS2017`
(Apache-2.0), Network-Flows table, pinned to commit
`eee96b6abc2c4bb621fd67679a4aa24bddc4be6a` (recorded in `manifest.yaml`). It is
interim. Switching to the official UNB/CIC CSVs is a config change
(`DataSourceConfig(source="official_unb")`, files in
`data/raw/cicids2017/official/`). That path is untested against real files
because none are available here.

## What this stage does NOT do

No Detection or Novelty algorithm is selected or trained. No validation,
learning, adversarial, or orchestrator/risk work is included.
