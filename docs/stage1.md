# Stage 1 — Foundation

Stage 1 proves the *shape* of the Ovael pipeline — that a sample can flow
end-to-end through the architecture's module boundaries — before any real
ML work begins. It proves nothing about detection quality: every component
except the contracts and the pipeline wiring is a deliberately obvious
stub or placeholder.

## Running it

```bash
python scripts/run_pipeline.py
```

Builds one hardcoded sample `RawTraffic`, runs it through the full
pipeline, and prints every intermediate artifact plus the final
`FinalAssessment`. Stub/placeholder values are visually obvious in the
output (`predicted_class="unknown-placeholder"`, `confidence=0.0`, etc.)
and each section is labeled with what it is.

## Running the tests

```bash
pip install -e ".[dev]"   # or: pip install pytest
pytest
```

(`ovael` is also importable without installing — `conftest.py` and
`scripts/run_pipeline.py` both add the repo root to `sys.path`
themselves.)

## Architecture diagram

```
RawTraffic
    |
    v
Feature Extraction (STUB: pass-through)
    |
    v
FeatureVector
    |
    +----------------------+
    v                      v
Detection Agent (STUB)   Novelty Agent (STUB)
    |                      |
    v                      v
DetectionResult        NoveltyResult
    |                      |
    +----------+-----------+
               v
          Orchestrator (bundling only)
               |
               v
      OrchestrationContext
               |
               v
    Risk Analysis (PLACEHOLDER)
               |
               v
         RiskAssessment
               |
               v
         FinalAssessment
```

Detection and Novelty run in parallel on the same `FeatureVector`; neither
gates the other. This mirrors the eventual real architecture — a real
classifier model and a real novelty/anomaly model both always run, and
the Orchestrator sees both outputs every time — even though Stage 1's
versions of all three (Detection, Novelty, Orchestrator) are stubs.

## What each component is

| Module | What it is | Status |
|---|---|---|
| `ovael/contracts/schemas.py` | The frozen dataclasses passed between every stage: `RawTraffic`, `FeatureVector`, `DetectionResult`, `NoveltyResult`, `OrchestrationContext`, `RiskAssessment`, `FinalAssessment` | **Real** — this is the actual contract, not a stub |
| `ovael/ingestion/feature_extraction.py` | `extract_features()` | **Stub** — pass-through copy of fields, plus one fake `placeholder_feature` |
| `ovael/agents/detection/interface.py` | `DetectionModel` ABC | **Real interface**, no implementation decided |
| `ovael/agents/detection/stub.py` | `StubDetectionModel` | **Stub** — always returns `("unknown-placeholder", 0.0)` |
| `ovael/agents/novelty/interface.py` | `NoveltyDetector` ABC | **Real interface**, no implementation decided |
| `ovael/agents/novelty/stub.py` | `StubNoveltyDetector` | **Stub** — always returns `(is_novel=False, novelty_score=0.0)` |
| `ovael/orchestration/orchestrator.py` | `orchestrate()` | **Bundling only** — combines both results into one context, no agreement/disagreement/weighting logic |
| `ovael/risk/risk_analysis.py` | `assess_risk()` | **Placeholder** — fixed output, not a function of its input, not a real risk formula |
| `ovael/validation/interface.py` | `Validator` ABC | **Architectural placeholder only** — not wired into the pipeline |
| `ovael/learning/interface.py` | `Learner` ABC | **Architectural placeholder only** — not wired into the pipeline |
| `ovael/pipeline/pipeline.py` | `run()` | **Real wiring** — the only module that imports from every component package above |

## What is explicitly NOT implemented in Stage 1

- No real feature extraction (flow assembly, statistical features, windowing).
- No real Detection Agent algorithm (no Random Forest, XGBoost, neural net,
  or anything else).
- No real Novelty Agent algorithm (no Isolation Forest, OCSVM, LOF,
  autoencoder, or anything else).
- No Orchestrator decision logic — the real combination strategy
  (agreement/disagreement handling, weighting, etc.) is an open research
  decision, deliberately not made here.
- No real risk-scoring formula.
- No Validation implementation, and Validation is not called anywhere in
  the pipeline.
- No Learning implementation, and Learning is not called anywhere in the
  pipeline.
- No Adversarial Evaluation in any form.
- No infrastructure: no Docker, no CI, no database, no queue, no API.
- No datasets, no `research/`, `data/`, `models/`, `configs/`, `services/`,
  or `knowledge/` directories — Stage 1 does not need them.

## Where Stage 2+ is expected to plug in

- A real `DetectionModel` and `NoveltyDetector` implement the same
  interfaces in `agents/detection/interface.py` and
  `agents/novelty/interface.py` and can be passed into
  `pipeline.run(detection_model=..., novelty_detector=...)` without
  changing the wiring.
- A real decision strategy replaces the body of
  `orchestration/orchestrator.py`'s bundling (or sits in a new module the
  orchestrator calls into) — this is an open research decision, not
  pre-empted here.
- A real `risk_analysis.py` reads `OrchestrationContext` instead of
  ignoring it.
- `Validator`/`Learner` get concrete implementations and get wired into
  `pipeline.py` (or a learning-loop module built around them) once that
  design is decided.
