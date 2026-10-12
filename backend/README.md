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
# optional but recommended: real network data (see "Data and labels")
.venv/bin/python -m ovael.cli dataset import-cicids data/cicids2017
.venv/bin/python -m ovael.cli train all          # trains + promotes a network and a website model
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
.venv/bin/python -m pytest -q                    # 45 tests
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
sandbox/               victim (sensor), normal client; ovael/replay.py replays real flows
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
* The Isolation Forest sees the features on a log scale (rates and byte counts span many orders
  of magnitude). On CIC-IDS2017 this raised its AUROC from 0.82 to 0.87 for known attacks.

| Classifier | Anomaly detector | risk_level | score band | Network | Website |
|---|---|---|---|---|---|
| attack | unusual | high | 75-100 | alert + auto-defense | known tracker, unusual |
| attack | normal | medium | 50-74 | alert | typical tracker |
| normal | unusual | suspicious | 25-49 | alert + review | possible unknown tracker |
| normal | normal | low | 0-24 | nothing | nothing |

**Persistence rule.** On real traffic most known attacks are confidently recognised but not
"unusual" per flow (brute force, web attacks and port scans almost never are), so the table alone
would never block them. When one source produces `OVAEL_PERSISTENCE_ALERTS` (default 20) confident
known-attack alerts inside the 60 s incident window, the incident is escalated to high and becomes
eligible for auto-defense. The action is logged with the reason "persistent".

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
cp .env.example .env                              # then set real tokens and passwords
docker compose up -d --build                      # http://localhost:8088
docker compose up -d --scale api=4 --scale scan-worker=3
docker compose --profile sandbox up -d            # victim + sensor, defense agent, normal client
docker compose --profile sandbox run --rm replayer   # replay real CIC-IDS2017 attack flows
docker compose --profile monitoring up -d         # Prometheus :9090, Grafana :3000
```

Verified on 2026-10-12 (Docker 29.7, Compose 2.32, Fedora with SELinux):

* all 9 images build;
* nginx split requests evenly over 2 replicas, and a third replica joined with no restart;
* a WebSocket held by one replica received events produced by both;
* the victim's sensor captured live client traffic (58 real flows, all scored low);
* the replayer sent 578 real flood flows, and the defense agent added a real iptables DROP rule in
  the victim's network namespace; undo (admin token) removed it, and was refused without a token;
* a website scan ran through Celery and the isolated scanner;
* `/metrics` is refused from outside.

## Sandbox

The `sandbox` profile is the defensive half of a lab, on an internal network (172.28.0.0/16):

| Container | Role |
|---|---|
| `victim` | nginx web server plus `sandbox/victim/sensor.py`, which sniffs the sandbox interface, builds flows and posts them to `/api/flows` |
| `defense-agent` | shares the victim's network namespace with NET_ADMIN; applies and removes iptables rules for the API |
| `client` | browses the victim with random think time: live normal traffic |
| `replayer` | `ovael replay`: sends real recorded attack flows (CIC-IDS2017) through the sensor endpoint |

There are no live attack generators. Attack traffic enters as real recorded flows, which also
makes every run reproducible. The sensor can record labelled flows from your own lab
(`OVAEL_RECORD_CSV`); import them with `ovael dataset import capture.csv --source lab-1`.

## Research lab (`/lab` in the dashboard)

* **Does it learn?** Show the network model a class it never trained on (real botnet flows),
  label those flows, retrain (promoted only if not worse on the fixed held-out set), then show it
  fresh flows of the same class. On CIC-IDS2017: before, 0 of 40 botnet flows recognised (all
  "benign"); after one round of 40 labelled flows, 28 of 40 fresh flows recognised as botnet, with
  held-out macro F1 0.9986 -> 0.9988.
* **Can it be fooled?** Modify an attack's features step by step (slow down, pad packets, spread
  over sources, mimic normal) and chart how often the classifier recognises it, the anomaly
  detector flags it, and Ovael raises any alert. Feature-space only; no traffic is sent.

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

### Network: CIC-IDS2017 (real traffic)

CIC-IDS2017 (Sharafaldin, Lashkari and Ghorbani, ICISSP 2018; Canadian Institute for
Cybersecurity) is five working days of real lab traffic, with flows labelled per attack. The
official site requires registration; the same labelled-flow files are mirrored on Hugging Face
(`bvsam/cic-ids-2017`, `traffic_labels/*.parquet`). Put them in `data/cicids2017/` (git-ignored)
and run `ovael dataset import-cicids`. The converter (`ml/cicids.py`):

* maps CICFlowMeter columns to our 24 features (microseconds converted to seconds);
* rebuilds the two "same source in the last 10 s" features from source IP and timestamp. CIC
  timestamps have one-minute resolution, so these are estimated from per-minute windows. This is
  an approximation, and it differs from the sensor's exact 10 s window;
* maps labels to our families, drops Infiltration (36 rows) and Heartbleed (11 rows), and caps
  classes (benign 80k, attacks 15k each, spread over sub-labels);
* holds **Bot** out of training entirely (1,966 flows). It is the real "unknown attack" for the
  Unknown scenario, the learning-loop experiment and the novelty metrics.

Results on 27,462 held-out flows (`network-v5`):

| Metric | Value |
|---|---|
| Classifier macro F1 | 0.9986 |
| Anomaly false alarms on normal traffic (threshold 0.99) | 0.83% |
| Anomaly AUROC, known attacks vs normal | 0.865 |
| Anomaly AUROC, held-out botnet vs normal | 0.709 |
| Held-out botnet flagged unusual at 0.99 | 0% |

Read these with care:
* CIC-IDS2017 is known to be easy for flow classifiers, and our held-out split is from the same
  capture days. Near-perfect F1 does not mean the model will transfer to another network.
* Per-flow features miss botnet traffic almost completely: the classifier calls it benign at
  99.8% confidence, and the anomaly detector cannot separate it at a usable false-alarm rate.
  Botnets show up as patterns across many flows (regular beacons), which per-flow features cannot
  see. The learning loop is what closes the gap.

Without `data/network_flows.csv` the network model falls back to the synthetic set
(`ml/synthetic.py`) and is labelled `synthetic_bootstrap` everywhere.

### Website: the crawler dataset, with leakage-free training

`../dataset_collection/output/website_features.csv` has no ground-truth labels, so rows get
documented weak labels from tracker-list and fingerprinting rules (`ml/labeling.py`). To stop the
model from simply copying those rules, every feature the rules read, and everything derived from
the same tracker list, is **excluded from the model** (`LABEL_RULE_FEATURES` in
`feature_extraction/website_schema.py`). The model has to infer tracking from general page
behaviour: request mix, third-party requests, cookies, storage use, iframes and redirects.

| 5-fold CV, 336 sites | Macro F1 |
|---|---|
| Majority-class baseline | 0.35 |
| With the rule features (copies the rules) | 0.94 |
| **Leakage-free (shipped)** | **0.85** |

The report card still lists the actual trackers and fingerprinting calls the scanner observed,
as evidence. Labels confirmed in the review queue, and any `manual_review_label` /
`security_label` in the CSV, override the weak label.

### Remaining limitations

* The website labels are still rule-derived. Leakage-free training proves the behaviour signal is
  real, but a human-labelled test set would be the next step.
* Live attack traffic is replayed from a public dataset, not generated in our own lab.
* No Postgres read replica or Grafana dashboards are provisioned; the settings and Prometheus
  scrape config are there.
