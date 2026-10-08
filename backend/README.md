# ovael-ai-backend

FastAPI backend for Ovael.ai — feature extraction, the Multiclass Model, the Novelty Detector, the orchestrator/risk engine, and the adaptive learning loop.

## Structure

- `backend/api/` — REST + WebSocket endpoints
- `feature_extraction/` — packet/flow → feature vector
- `ml/backend_models/multiclass/` — Multiclass Model (Random Forest, known attack categories)
- `ml/backend_models/novelty/` — Novelty Detector (Isolation Forest, unseen behaviour)
- `orchestrator/` — combines both model outputs, decision table, risk scoring
- `learning_loop/` — hard examples, human review, retraining
- `scripts/` — one-off validation and utility scripts (not part of the served app)

## Run

`ml/` lives at the repo root, shared with `ml/research/` (the dataset
pipeline) - so the repo root must also be on the import path alongside
`backend/` itself:

```
cd backend
pip install -r requirements.txt
PYTHONPATH=.. uvicorn main:app --reload
```
