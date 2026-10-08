# ml/ — Multiclass Model & Novelty Detector

Owned by the ML lead. Scope: `ml/backend_models/multiclass/`, `ml/backend_models/novelty/`, and the
shared schema contract in `feature_extraction/schema.py`. Does not
touch Docker, traffic simulation, backend API routes, the database
schema, or the frontend — those are the networking and backend/frontend
teammates' territory.

## The schema contract

`feature_extraction/schema.py` defines `FeatureVector` — the one shape
both models and feature extraction must agree on. It is the interface
boundary between this teammate's ML code and the networking teammate's
real capture pipeline.

```python
@dataclass
class FeatureVector:
    src_ip: str
    dst_ip: str
    src_port: int
    dst_port: int
    protocol: str        # "TCP" | "UDP" | "ICMP"
    byte_count: float
    duration: float       # seconds
    packet_rate: float    # packets/sec
    packet_count: int
    label: str | None = None   # training/mock only, absent at inference
```

`LABELS = ("normal", "ddos", "port_scan", "exfiltration")` is the
canonical category set both the Multiclass Model and the mock generator
use. `NUMERIC_FEATURE_ORDER` fixes the exact column order fed into both
models via `to_vector()` — **do not reorder it without retraining both
models.**

Real feature-extraction code must produce `FeatureVector` instances (or
dicts with the same fields) satisfying `schema.validate()`. Once that
exists, nothing in `ml/` needs to change — only the data source does
(see "Swapping mock data for real data" below).

## Mock data (until real feature extraction is ready)

`ml/backend_models/mock_feature_generator.generate_mock_dataset(n_per_class, seed)`
returns a balanced, shuffled list of synthetic `FeatureVector`s, one
generator function per label, with hand-picked distributions that are
directionally realistic (e.g. DDoS = high packet rate + short duration,
port scan = tiny packets + near-zero duration). This is what both
models train and self-validate against today.

`ml/backend_models/benchmark_adapter.load_kddcup99_as_feature_vectors()` additionally
maps the real KDD Cup 1999 dataset onto the schema (used by the
Multiclass Model only — see below for why the Novelty Detector doesn't
use it).

## Multiclass Model — `ml/backend_models/multiclass/model.py`

Predicts all four `schema.LABELS` (`TARGET_LABELS` in `model.py`). It was
briefly binary (normal/ddos), which mislabeled exfiltration as ddos; that
is fixed and covered by tests.

RandomForestClassifier trained on mock data **plus** the KDD Cup 1999
benchmark (adapted onto the schema — an approximation, since KDD99 has
no port numbers and predates this schema; see
`benchmark_adapter.py`'s docstring for the exact label/field mapping),
filtered down to `TARGET_LABELS`.

```python
from ml.multiclass.model import MulticlassModel

model = MulticlassModel.load()                  # loads the saved .joblib
label, confidence = model.predict_one(feature_vector)  # label: one of schema.LABELS, confidence: float in [0,1]
```

`feature_vector` must be a `feature_extraction.schema.FeatureVector`
(or anything with the same attributes) — see "The schema contract"
above for the exact fields.

Train and save a fresh model: `python -m ml.multiclass.model` (prints
accuracy, precision/recall per class, and a confusion matrix; saves to
`ml/backend_models/models/multiclass_model.joblib`).

Last training run: 99.98% accuracy on held-out data, confusion matrix
`[[729 ddos→ddos, 0 ddos→normal], [4 normal→ddos, 19512 normal→normal]]`.

## Novelty Detector — `ml/backend_models/novelty/model.py`

IsolationForest trained **only on mock-normal data**, deliberately not
mixed with the KDD99 benchmark. That was tried first — at 97k benchmark
rows vs a few hundred mock rows, the benchmark's KDD99-unit scale
completely swamped the learned "normal" region, so genuinely normal
mock-schema traffic scored as anomalous ~52% of the time. Since real
captured data will match the mock schema's scale, not KDD99's,
mock-only is the correct call here (unlike the Multiclass Model, this
was never a hard requirement to mix benchmark data in).

```python
from ml.novelty.model import NoveltyModel

model = NoveltyModel.load()                     # loads the saved .joblib + calibrator
anomaly_score = model.predict_one(feature_vector)  # float in [0,1], higher = more anomalous
```

`anomaly_score` is a calibrated percentile (`ml/backend_models/novelty/score_calibration.py`):
"what fraction of normal training flows looked at least this
anomalous?" 0.99 means this flow is more unusual than 99% of known-normal
traffic. It is not a probability of being an attack — that combination
is the orchestrator's job, not this module's.

Train and save a fresh model: `python -m ml.novelty.model` (prints
held-out normal vs. mock-attack separation stats, saves to
`ml/backend_models/models/novelty_model.joblib` + `ml/backend_models/models/novelty_calibrator.joblib`).

Last training run: held-out mock-normal scored mean 0.52 (as expected —
a held-out point from the same distribution as training should land
near the 50th percentile), mock attacks scored mean 1.00, giving 100%
detection / 4.5% false-positive rate at a 0.95 threshold.

## Validating both together

`scripts/validate_models.py` loads both saved models and runs them
against one mock `FeatureVector` per class — the same call pattern
shown above, run end to end. `python -m scripts.validate_models`.
Prints multiclass label/confidence and novelty score for each class.

## Mock data for backend integration testing

`scripts/generate_backend_mock_data.py` writes
`scripts/mock_feature_vectors.json` — 200 mock `FeatureVector`s (50
50 per label) as a JSON fixture,
so the backend teammate can wire up and test the API/database/dashboard
against realistic-looking output before real traffic capture is ready.
Each object includes `"label"` as ground truth (real inference-time
input won't have it). Regenerate: `python -m scripts.generate_backend_mock_data`.

## Swapping mock data for real data

When the networking teammate's real feature extraction is ready:

1. In `ml/backend_models/multiclass/model.py` and `ml/backend_models/novelty/model.py`, replace the
   `generate_mock_dataset(...)` call with the real pipeline's output —
   as long as it's a list of `FeatureVector`s (or satisfies
   `schema.to_vector()`), nothing else changes.
2. Re-run `python -m ml.multiclass.model` and `python -m ml.novelty.model`
   to retrain and re-save both models.
3. `ml/backend_models/benchmark_adapter.py` becomes optional at that point — it exists
   to unblock training before real data exists, not as a permanent data
   source.

## Model artifacts

`ml/backend_models/models/*.joblib` are generated, not committed (see `.gitignore`).
Run the training commands above to regenerate them locally.
