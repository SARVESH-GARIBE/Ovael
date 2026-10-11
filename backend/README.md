# ovael.ai backend

One FastAPI backend for both features in the architecture document
(`Ovael Documentation/ovael_updated_architecture.pdf`):

| | Network protection | Website analysis |
|---|---|---|
| Trigger | Always on: the sensor posts flows | On demand: `POST /api/scans` |
| Features | 24 flow features (`feature_extraction/network_schema.py`) | 44 browser-behaviour features (`feature_extraction/website_schema.py`) |
| Models | Random Forest + Isolation Forest | Random Forest + Isolation Forest |
| Output | Live alert, risk score, auto-defense with undo | Risk report with SHAP reasons |

Both go through the same `detect(module, features)` call and the same four-row decision table.

## Quick start (one process, no Docker)

```bash
cd backend
python3.12 -m venv .venv && .venv/bin/pip install -r requirements-dev.txt
.venv/bin/python -m ovael.cli train all          # trains + promotes network-v1 and website-v1
.venv/bin/uvicorn ovael.api.app:app --reload     # http://localhost:8000/api/docs
```

Then run the frontend (`cd ../frontend && npm run dev`) and open http://localhost:5173.
Without Redis/Postgres/Celery the backend uses SQLite, an in-process event bus and in-process
jobs. Same code paths, one machine.

Try it:

```bash
curl -XPOST localhost:8000/api/simulate -H 'content-type: application/json' \
     -d '{"scenario":"full_demo","duration_s":30}'
curl -XPOST localhost:8000/api/scans -H 'content-type: application/json' -d '{"url":"example.com"}'
.venv/bin/python -m pytest -q                    # 32 tests
```

Website scans need Chromium: `.venv/bin/playwright install chromium`.

## Layout (module names follow section 4.6 of the architecture)

```
ovael/
  feature_extraction/  network + website schemas, 5-tuple flow builder
  ml/                  training, model bundle (RF + IF + calibration + SHAP), registry, labels
  orchestrator/        decision table, risk score, attack taxonomy
  core/                detect() engine, event bus, cache/rate limit, jobs, metrics, context
  services/            live pipeline, scans, review + retrain
  defense/             auto-defense policy (engine.py) and the privileged agent (agent.py)
  learning_loop/       retrain -> evaluate on fixed held-out set -> promote if not worse
  scanner/             SSRF guard, crawler-backed scanner, isolated scanner service
  simulator/           synthetic flows through the real pipeline (demo)
  api/                 REST routes, WebSocket /ws, schemas (= OpenAPI contract)
  workers/             Celery app (scans + training queues)
sensor/sensor.py       packet capture on the protected host -> POST /api/flows
deploy/                nginx load balancer, Prometheus
```

## The detection contract

```
detect(module, features) -> {label, confidence, anomaly_score, risk_level, top_features, model_version}
```

* `anomaly_score` is the Isolation Forest score as a percentile of normal training traffic
  (0.99 = more unusual than 99% of normal). Above `OVAEL_ANOMALY_THRESHOLD` it counts as "unusual".
* A classifier attack label below 50% confidence is treated as *not recognised*. Its family
  becomes `unknown`, and it goes to review instead of auto-defense.

| Classifier | Anomaly detector | risk_level | score band | Network | Website |
|---|---|---|---|---|---|
| attack | unusual | high | 75-100 | alert + auto-defense | known tracker, unusual |
| attack | normal | medium | 50-74 | alert | typical tracker |
| normal | unusual | suspicious | 25-49 | alert + review | possible unknown tracker |
| normal | normal | low | 0-24 | nothing | nothing |

Inside a band, the position is `severity_weight × confidence` for attacks and `anomaly_score`
otherwise. Severity weights per attack family live in `orchestrator/taxonomy.py`, together with
"how it works" steps, indicators, MITRE IDs and mitigations. The UI reads them from
`GET /api/taxonomy`.

## API

| Endpoint | Purpose |
|---|---|
| `POST /api/flows` (sensor token) | Batch of flows from the sensor |
| `GET /api/detections?module=network&alerts_only=true` | Alert feed (cursor: `before`) |
| `GET /api/detections/{id}` | Detail; SHAP computed on demand and stored |
| `GET /api/incidents` | Detections grouped by source + family (a flood = 1 incident) |
| `POST /api/scans` / `GET /api/scans/{id}` | Submit URL / status + report |
| `GET /api/actions`, `POST /api/actions/{id}/undo` | Defense log, undo a block |
| `GET /api/review-queue`, `POST .../{id}/confirm`, `.../reject` | Hard examples |
| `GET /api/models`, `POST /api/models/{m}/retrain`, `POST /api/models/{m}/{v}/promote` | Registry, rollback = promote |
| `GET /api/taxonomy`, `GET /api/stats/summary`, `GET /api/system` | Dashboard data |
| `POST/GET/DELETE /api/simulate` | Synthetic traffic through the real pipeline |
| `GET /api/health/live`, `/api/health/ready`, `/metrics` | Probes, Prometheus |
| `WS /ws` | `new_detection`, `incident_update`, `defense_action`, `scan_update`, `scan_complete`, `review_item`, `model_retrained`, `simulation` |

Full schema: `/api/docs` (OpenAPI at `/api/openapi.json`).

## Scaling and load distribution

```
                   browser
                      │
                 nginx (LB, rate limits, static frontend)
                least_conn │ ws upgrade
        ┌─────────────┬────┴────────┐
      api-1         api-2   ...   api-N        stateless; scale with --scale api=N
        └──────┬──────┴──────┬──────┘
           Redis pub/sub   PostgreSQL (+ optional read replica)
        (events, cache,        │
         rate limits, locks)   │
               │               │
        Celery queues ── scan-worker(s) ── scanner (isolated, Chromium)
                      └─ train-worker
```

* **Stateless API.** State lives in Postgres, Redis and the shared model volume. Any instance
  serves any request, so the load balancer needs no sticky sessions.
* **Live events cross instances.** Each instance holds one Redis subscription and fans out to its
  own WebSocket clients through bounded queues. A slow browser drops old events instead of slowing
  everyone else.
* **Detection stays synchronous** (section 6). It runs in a thread pool, and flows are batched
  into one vectorised predict call: about 60 ms for 500 flows on one core.
* **Push volume is controlled.** Alerts are grouped into incidents and pushed at most twice a
  second per incident; normal traffic is sampled. Everything is still stored.
* **Slow work is queued.** Scans and retraining run on separate Celery queues, and Chromium
  concurrency is capped per worker. Add workers when queue depth grows.
* **Shared state is safe across instances.** The scan cache, rate limits and the
  "block once" lock live in Redis.
* **Hot model swap.** Promoting rewrites `model_store/<module>/ACTIVE`; every instance notices
  the change and reloads without a restart.
* **Reads can be offloaded.** Set `OVAEL_DATABASE_READ_URL` to send dashboard reads to a replica.
  Read-after-write paths stay on the primary.

```bash
cp .env.example .env
docker compose up -d --build                      # http://localhost
docker compose up -d --scale api=4 --scale scan-worker=3
docker compose --profile monitoring up -d         # Prometheus :9090, Grafana :3000
```

## Safety

* **Website scans:** the URL guard rejects anything except http(s), credentials in the URL, odd
  ports, IP literals, and hosts that resolve to private, loopback, link-local or metadata
  addresses. The crawler's SafetyProxy then re-checks every connection, including redirects. The
  scanner container sits on its own networks, with no route to Postgres or Redis.
* **Auto-defense** fires only for high risk where both models agree, the family allows it, and
  the source is inside `OVAEL_SANDBOX_SUBNET`. The API never runs firewall commands. The
  separate defense agent (`defense/agent.py`, NET_ADMIN, inside the protected host's network
  namespace) does, and it refuses addresses outside the subnet or on its protected list. Every
  action is logged and can be undone. `OVAEL_DEFENSE_MODE=simulate` (the default) records actions
  without touching any firewall.
* **Auth:** bearer tokens for the admin and sensor roles. In dev, unset tokens leave those routes
  open and the backend logs a warning at startup.

## Data and labels (read this before quoting metrics)

* **Website:** `../dataset_collection/output/website_features.csv` (your crawler). It has no
  ground-truth labels, so rows get documented weak labels (`ml/labeling.py`): `invasive_tracker`,
  `tracker` or `benign`. The first model therefore largely reproduces those rules. Labels
  confirmed in the review queue, and any `manual_review_label` / `security_label` in the CSV,
  override the weak label.
* **Network:** if `data/network_flows.csv` exists (24 schema columns + `label`, e.g. recorded by
  `sensor/sensor.py` with `OVAEL_RECORD_CSV`), the model trains on it. Otherwise it trains on
  the synthetic bootstrap set (`ml/synthetic.py`). Models are tagged with their `label_source`,
  and the dashboard shows it. The near-perfect scores on the synthetic set say nothing about
  real traffic.
