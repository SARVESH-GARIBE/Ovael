# Website Behavioral Data Collection (Ovael)

Playwright/Chromium crawler that visits a fixed selection of websites from a Tranco ranking, records
real browser-observed privacy behaviour (requests, tracker-list matches, cookies, Web Storage use,
fingerprinting-related API calls, redirects, iframes), and writes a resumable, documented dataset for
the *AI-Based Website Behavioral Analysis and Tracker Detection System*.

This is a behavioural **feature** dataset. It contains no ground-truth security labels, and no model has
been trained or validated on it.

## Layout

```
dataset_collection/
├── top-1m.csv                 Tranco list 8PXYV (2026-10-10), verified against tranco-list.eu
├── smoke_sites.txt            smoke-test list (10 sites + failure/duplicate/unsafe fixtures)
├── requirements.txt
├── reference/                 downloaded reference data + metadata sidecars
│   ├── extension-tds.json     DuckDuckGo Tracker Data Set (built from Tracker Radar)
│   ├── urlhaus-hostfile.txt   URLhaus malware hosts (selection exclusion)
│   └── *.meta.json            URL, retrieval time, Last-Modified, SHA-256, Tranco verification
├── ovael_crawler/             the pipeline (python -m ovael_crawler ...)
│   ├── cli.py                 commands
│   ├── selection.py           Tranco / smoke-list selection and de-duplication
│   ├── crawler.py             visits, retries, resumable output store
│   ├── safety_proxy.py        destination-validating proxy (blocks non-public addresses)
│   ├── instrumentation.js     in-page API counters (init script)
│   ├── schema.py              CSV schema, definitions, missing-value rules, feature computation
│   ├── reference.py           tracker matching, reference downloads, Tranco identification
│   ├── report.py              dataset_documentation.docx generator
│   ├── validate.py            consistency + privacy checks
│   └── selftest.py            offline instrumentation self-test
├── output/                    the 500-domain run
└── output_smoke/              the smoke-test run
```

## Setup

Python 3.11+ (tested with 3.14).

```bash
cd dataset_collection
python3 -m pip install -r requirements.txt
python3 -m playwright install chromium
python3 -m ovael_crawler fetch-references     # tracker list, URLhaus list, Tranco list identification
```

`fetch-references` downloads the DuckDuckGo tracker list and URLhaus host list into `reference/` and
checks which Tranco list `top-1m.csv` is: it compares the first 1000 rows with the lists published on
tranco-list.eu. The reference files used for the current dataset are already in `reference/`. Re-running
the command replaces them, and the new version is recorded in the manifest.

## Commands

| Task | Command |
|---|---|
| Instrumentation self-test (offline) | `python3 -m ovael_crawler selftest` |
| Smoke test (self-test + crawl `smoke_sites.txt` + report + validation) | `python3 -m ovael_crawler smoke --force` |
| Resume an interrupted smoke test | `python3 -m ovael_crawler smoke --resume` |
| Select the 500 Tranco domains | `python3 -m ovael_crawler select --n 500 --output output` |
| Launch the full crawl | `python3 -m ovael_crawler crawl --output output` |
| Resume after interruption (same command) | `python3 -m ovael_crawler crawl --output output` |
| Crawl only the next N pending sites | `python3 -m ovael_crawler crawl --output output --limit 50` |
| Progress / counts | `python3 -m ovael_crawler status --output output` |
| Regenerate the DOCX report | `python3 -m ovael_crawler report --output output` |
| Validate outputs | `python3 -m ovael_crawler validate --output output` |

Crawl options: `--workers 3`, `--settle-s 5`, `--navigation-timeout-s 30`, `--load-event-timeout-s 15`,
`--overall-timeout-s 150`, `--max-retries 2`, `--headed`. The values used are stored in
`crawl_manifest.json`.

### Resumption

`website_observations.jsonl` is the commit log. A website is finished once its record has been appended,
and that record is written last, after its request and cookie lines. To stop a crawl, press Ctrl-C or send
SIGTERM: websites still being visited are left *pending*. Re-running `crawl` then does the following:

1. drops a truncated trailing line, if any;
2. removes request/cookie lines from visits that never committed;
3. rebuilds both CSVs from the JSONL, so the CSV and JSONL always agree;
4. visits only the pending websites.

The run also stops by itself, leaving the remaining sites pending, when network connectivity is lost (the
site's failure is not recorded) or after 20 consecutive websites return HTTP 5xx.

`select` refuses to overwrite a directory that already holds crawl records.

## How a website is visited

* A fresh browser context per attempt. Service workers are blocked, downloads are refused, and the context
  uses the default headless Chromium user agent. There is no interaction: no clicks, scrolling, consent
  handling, forms, logins or CAPTCHAs.
* URL order: `https://<domain>/`, then `https://www.<domain>/`, then `http://<domain>/`. The next URL is
  tried when the host is unreachable (DNS failure, connection refused, TLS error). Transient errors
  (timeouts, resets, HTTP 429/503) are retried up to 2 times with exponential backoff (3 s, 6 s;
  `Retry-After` is honoured up to 30 s).
* Timing: `goto` waits for DOMContentLoaded (30 s limit), then up to 15 s for `load`, then a fixed
  **5 s settling period**. Cookies, DOM iframes and instrumentation counters are read once, at the end of
  that period. The hard cap is 150 s per website. 3 workers run in parallel, and each worker pauses 1 s
  between sites.
* **Safety proxy.** Every browser connection goes through a per-context local proxy, including every
  redirect hop, subresource, iframe and WebSocket. The proxy resolves DNS itself. It refuses the
  connection if any resolved address is loopback, private, link-local, CGNAT, multicast or reserved.
  Otherwise it connects to the address it just validated, so there is no DNS-rebinding window. QUIC is
  disabled and WebRTC is restricted to proxied UDP. Playwright request routing is *not* used for this,
  because it is not invoked for redirect hops (verified during development).
* **Instrumentation.** `instrumentation.js` runs before page scripts in every frame. It counts calls to
  Canvas (toDataURL, toBlob, getImageData, fillText, strokeText, measureText, isPointInPath,
  getContext), WebGL 1/2 (getParameter, including UNMASKED_VENDOR/RENDERER queries, getExtension,
  getSupportedExtensions, getShaderPrecisionFormat, readPixels), Audio (AudioContext/OfflineAudioContext
  construction, oscillator/compressor/analyser, startRendering, getChannelData), fonts.check, getBattery,
  enumerateDevices, RTCPeerConnection, permissions.query, Storage (setItem/removeItem/clear/getItem/key),
  document.cookie get/set, indexedDB.open, caches.open and navigator.storage. It never stores values.
  `selftest` checks the counters against a page with known calls.

## Output files (`output/`)

| File | Content |
|---|---|
| `website_features.csv` | One row per attempted website: metadata, `crawl_status`, numerical features, empty label columns |
| `website_observations.jsonl` | Full structured record per website: attempts and errors, redirect chain, request/tracker/cookie summaries, third-party hosts with match status, frames, instrumentation counters and evidence, safety blocks |
| `request_observations.jsonl` | One line per request: sanitised URL (no query/fragment), hostname, registrable domain, party, resource type, frame, status, failure, tracker match. No headers or bodies |
| `cookie_metadata.jsonl` | One line per cookie: name (identifiers redacted), domain, path, expiry, Secure, HttpOnly, SameSite, party. **No values** |
| `tracker_matches.csv` | One row per (website, matched third-party hostname) with owner, categories, fingerprinting score and reference version |
| `crawl_manifest.json` | Tranco list ID and verification, selection method, the 500 selected domains, reference version, config, environment, run history, status counts |
| `dataset_documentation.docx` | Technical report generated from the files above |
| `crawl.log` | Structured JSON log; `console.log` holds the terminal progress |

### Status values

`crawl_status` takes one of these values:

* `success`: the page was observed.
* `http_error`: the main document returned HTTP status ≥ 400. The page was still observed, but the
  features describe the error or challenge page.
* `failed`: no page was observed. `navigation_outcome` holds the error class, for example `dns_failure`,
  `tls_error`, `timeout` or `connect_refused`.
* `blocked_unsafe`: the destination resolved to a non-public address.

The manifest's `status` block reports these counts:

| Count | Meaning |
|---|---|
| `selected` | websites in the selection |
| `attempted` | websites with a final record |
| `completed_observed` | `success` + `http_error` |
| `failed` | `failed` |
| `blocked_unsafe` | `blocked_unsafe` |
| `pending` | websites not yet recorded |

### Missing values

An empty cell means *not measured*: the visit failed, or the relevant instrumentation returned nothing
(see `instrumentation_status`). `0` means *measured, nothing observed*. Unknown values are never filled
with 0. A hostname missing from the tracker list is `not_in_reference`, not benign. The definition, type
and missing-value rule of every column are in `ovael_crawler/schema.py` and in the DOCX report.

### Labels

`security_label`, `manual_review_label`, `label_source`, `label_confidence` and `labeled_at` exist but are
empty. `has_tracker_reference_match` is a reference-list observation, not a maliciousness label. Do not
use tracker-list matches both as a label and as a predictive feature in an evaluation that claims
independent predictive performance.

## Known limitations

* One visit per site, landing page only, pre-consent, from a single vantage point and time.
* Headless Chromium is detectable. Some sites return challenge or blank pages, which appear as
  `http_error`, or as `success` with a tiny `dom_element_count`/`visible_text_length`.
* Tranco's top 500 includes CDN/API/infrastructure domains with no website (e.g. `gstatic.com`,
  `akamai.net`). These appear as failures or minimal pages.
* The tracker list is DuckDuckGo's curated ~1,000-domain blocking list. Matching is domain-level and does
  not apply DDG's path rules or exceptions. `same_entity_as_site` and `default_action` are recorded.
* Instrumentation does not cover Web/Service Workers, property-style storage writes
  (`localStorage.x = 1`), or documents removed before reporting. Wrapped functions are detectable by
  scripts.
* Cookies are read once, at the end of the visit. Hidden-iframe classification covers only top-document
  iframes.
