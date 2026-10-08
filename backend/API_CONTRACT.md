# API Contract — ovael-ai-backend ↔ ovael-ai-frontend

Source of truth for the frontend repo. Shapes below are frozen; additive
fields are allowed, removals/renames need a version bump. Status column
says what is actually implemented in the backend today.

## REST

| Method | Path | Purpose | Status |
|---|---|---|---|
| POST | `/detections` | submit a feature vector, run detection, return the detection | implemented |
| GET | `/detections?limit=50` | list recent detections, newest first | implemented |
| GET | `/detections/{id}` | single detection (`explanation` is `null` until SHAP exists) | implemented |
| POST | `/simulations` | start an attacker/victim pair | not built |
| DELETE | `/simulations/{id}` | stop a running simulation | not built |
| GET | `/review/queue` | pending hard examples | not built |
| POST | `/review/{id}` | review decision: `known_attack` / `new_attack` / `false_positive` | not built |
| GET | `/models/versions` | model versions + validation scores | not built |
| GET | `/health` | liveness, returns `{"status": "ok"}` | implemented |

Storage is in-memory today: detections do not survive a backend restart.

### POST /detections

Request (`Content-Type: application/json`):

```json
{
  "src_ip": "10.0.0.5", "dst_ip": "10.0.0.9",
  "src_port": 51234, "dst_port": 80,
  "protocol": "TCP",
  "byte_count": 200000, "duration": 0.5,
  "packet_rate": 2000, "packet_count": 1500,
  "simulation_id": "sim-abc123"
}
```

- `protocol`: `"TCP"` | `"UDP"` | `"ICMP"`.
- Ports 0–65535; `byte_count`, `duration`, `packet_rate`, `packet_count` must be ≥ 0.
- `simulation_id` optional.
- Invalid input returns `422`.

Response `201`: a detection object (below).

## Detection object

```json
{
  "id": "uuid",
  "simulation_id": "sim-abc123",
  "timestamp": "2026-09-20T12:00:00+00:00",
  "multiclass": { "label": "ddos", "confidence": 0.85 },
  "novelty": { "score": 0.62 },
  "risk_score": 78,
  "severity": "high",
  "explanation": null,
  "verdict": "known_attack",
  "is_hard_example": false
}
```

| Field | Type | Notes |
|---|---|---|
| `id` | string | uuid |
| `simulation_id` | string \| null | echoes the request |
| `timestamp` | string | ISO 8601, UTC |
| `multiclass.label` | string | `normal` \| `ddos` \| `port_scan` \| `exfiltration` |
| `multiclass.confidence` | number | 0–1 |
| `novelty.score` | number | 0–1 percentile vs. known-normal traffic; higher = more anomalous |
| `risk_score` | integer | 0–100 |
| `severity` | string | `low` (<30) \| `medium` (30–59) \| `high` (60–84) \| `critical` (≥85) |
| `explanation` | object \| null | on-demand SHAP, currently always `null` |
| `verdict` | string | **additive**: `benign` \| `known_attack` \| `confirmed_attack` \| `suspicious_unknown` \| `low_confidence` |
| `is_hard_example` | boolean | **additive**: `true` when the models disagree (classifier confident "normal", novelty anomalous); the flow is queued for review |

`verdict` and `is_hard_example` are additive relative to the original
contract; clients that ignore them keep working.

## WebSocket — `/ws/live` (not built)

Two event types, JSON messages of the form `{"type": ..., "data": ...}`:

- `new_detection` — `data` is a detection object (same shape as above).
- `model_retrained` — drives the before/after view; payload shape TBD when the retraining loop exists.

## Thresholds behind the numbers

Decision-table buckets (confidence ≥0.80 high, ≥0.50 medium; novelty ≥0.95
anomalous, ≥0.90 elevated) and the risk weights are unvalidated starting
points and may change as real precision/recall data arrives. The response
shapes above will not.
