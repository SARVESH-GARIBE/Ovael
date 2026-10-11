"""Output consistency and privacy checks."""

from __future__ import annotations

import csv
import json
from collections import Counter
from pathlib import Path

from .reference import TrackerReference
from .schema import compute_features, csv_columns

FORBIDDEN_KEYS = {"value", "values", "headers", "authorization", "cookie_value", "set-cookie", "set_cookie",
                  "post_data", "postdata", "body", "request_body", "response_body"}
SENSITIVE_HEADER_NAMES = ("authorization:", "set-cookie:", "proxy-authorization:")


def _walk(obj, path=""):
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield path + "/" + k, k, v
            yield from _walk(v, path + "/" + k)
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            yield from _walk(v, f"{path}[{i}]")


def _jsonl(path: Path) -> list[dict]:
    return [json.loads(l) for l in path.read_text().splitlines() if l.strip()] if path.exists() else []


def validate(out: Path, secret_audit: Path | None = None) -> bool:
    results: list[tuple[str, bool, str]] = []

    def check(name, ok, detail=""):
        results.append((name, bool(ok), detail))

    manifest = json.loads((out / "crawl_manifest.json").read_text())
    recs = _jsonl(out / "website_observations.jsonl")
    reqs = _jsonl(out / "request_observations.jsonl")
    cookies = _jsonl(out / "cookie_metadata.jsonl")
    with open(out / "website_features.csv", newline="") as f:
        rows = list(csv.DictReader(f))
    with open(out / "tracker_matches.csv", newline="") as f:
        trows = list(csv.DictReader(f))
    ref = TrackerReference()

    sel = manifest["selected"]
    sel_ids = [e["website_id"] for e in sel]
    regds = [e["initial_registrable_domain"] or e["original_domain"] for e in sel]
    check("selection: website_ids unique", len(set(sel_ids)) == len(sel_ids))
    dup = [d for d, c in Counter(regds).items() if c > 1]
    check("selection: registrable domains unique (www/apex counted once)", not dup, f"duplicates={dup}")
    if manifest["run_type"] == "tranco":
        check("selection: no more than 500 domains", len(sel) <= 500, f"{len(sel)} selected")

    rec_ids = [r["website_id"] for r in recs]
    check("records: one record per website (no duplicates)", len(set(rec_ids)) == len(rec_ids),
          f"{len(rec_ids)} records, {len(set(rec_ids))} unique")
    check("records: all belong to the selection", set(rec_ids) <= set(sel_ids))

    # CSV <-> JSONL agreement
    by_id = {r["website_id"]: r for r in recs}
    csv_ids = [r["website_id"] for r in rows]
    check("csv: same websites as JSONL", sorted(csv_ids) == sorted(rec_ids), f"csv={len(csv_ids)} jsonl={len(rec_ids)}")
    cols = csv_columns(ref.categories)
    check("csv: header matches schema", rows == [] or list(rows[0].keys()) == cols)
    mismatches = []
    for row in rows:
        rec = by_id.get(row["website_id"])
        if rec is None:
            continue
        exp = compute_features(rec, ref.categories)
        for k in cols:
            ev = exp.get(k)
            ev = "" if ev is None else str(int(ev) if isinstance(ev, bool) else ev)
            if ev != row[k]:
                mismatches.append((row["website_id"], k, ev, row[k]))
    check("csv: every cell equals the value recomputed from JSONL", not mismatches, str(mismatches[:5]))

    req_counts = Counter(q["website_id"] for q in reqs)
    bad = [i for i, r in by_id.items() if r.get("request_summary")
           and req_counts[i] != r["request_summary"]["total_requests"] + r["request_summary"]["non_http_requests"]]
    check("requests: request_observations count matches each website record", not bad, str(bad[:5]))
    check("requests: no orphan request lines", set(req_counts) <= set(rec_ids))
    ck_counts = Counter(c["website_id"] for c in cookies)
    bad = [i for i, r in by_id.items() if r.get("cookie_summary") and ck_counts[i] != r["cookie_summary"]["total_cookies"]]
    check("cookies: cookie_metadata count matches each website record", not bad, str(bad[:5]))
    tr_expected = sum(len((r.get("tracker_summary") or {}).get("matched_hosts", [])) for r in recs)
    check("trackers: tracker_matches.csv rows match records", len(trows) == tr_expected, f"{len(trows)} vs {tr_expected}")

    observed = [r for r in recs if r["crawl"]["status"] in ("success", "http_error")]
    check("observations: observed visits have request events and a final URL",
          all(r["request_summary"]["total_requests"] > 0 and r["final"].get("url") for r in observed),
          f"{len(observed)} observed")
    failed = [r for r in recs if r["crawl"]["status"] in ("failed", "blocked_unsafe")]
    check("failures: every failed visit has a recorded reason",
          all(r["crawl"]["failure_reason"] and r["crawl"]["attempts"] for r in failed), f"{len(failed)} failed")
    for r in observed:
        if r["instrumentation"]["status"] != "ok":
            continue
        row = next(x for x in rows if x["website_id"] == r["website_id"])
        if row["canvas_api_calls"] == "":
            check("missing values: instrumented sites have numeric fingerprinting fields", False, r["website_id"])
            break
    for r in failed:
        row = next(x for x in rows if x["website_id"] == r["website_id"])
        if row["total_requests"] != "":
            check("missing values: failed visits have empty (not zero) features", False, r["website_id"])
            break

    # privacy
    bad_keys, bad_urls = [], []
    for name, items in (("website_observations", recs), ("request_observations", reqs), ("cookie_metadata", cookies)):
        for item in items:
            for path, k, v in _walk(item):
                if k.lower() in FORBIDDEN_KEYS:
                    bad_keys.append(f"{name}:{path}")
                if (k == "url" or k == "src") and isinstance(v, str) and ("?" in v or "#" in v):
                    bad_urls.append(f"{name}:{path}")
    check("privacy: no value/header/body fields saved", not bad_keys, str(bad_keys[:5]))
    check("privacy: saved URLs contain no query strings or fragments", not bad_urls, str(bad_urls[:5]))
    blob = "\n".join(p.read_text(errors="replace") for p in out.iterdir()
                     if p.suffix in (".jsonl", ".csv", ".json", ".log"))
    low = blob.lower()
    check("privacy: no sensitive header lines in outputs", not any(h in low for h in SENSITIVE_HEADER_NAMES))
    if secret_audit is not None and secret_audit.exists():
        values = {v for v in secret_audit.read_text().splitlines() if len(v) >= 8}
        leaked = [v for v in values if v in blob]
        where = []
        for v in leaked:
            for p in out.iterdir():
                if p.suffix in (".jsonl", ".csv", ".json", ".log"):
                    txt = p.read_text(errors="replace")
                    i = txt.find(v)
                    if i >= 0:
                        ctx = txt[max(0, i - 60):i].replace(v, "*")
                        where.append(f"{p.name}: len={len(v)} after ...{ctx!r}")
        check("privacy: none of the real cookie values observed appear in any output file",
              not leaked, f"{len(values)} distinct cookie values (>=8 chars) checked, {len(leaked)} found {where[:5]}")

    st = manifest["status"]
    check("manifest: status counts agree with records",
          st["attempted"] == len(recs) and st["pending"] == len(sel) - len(recs))

    docx = out / "dataset_documentation.docx"
    try:
        from docx import Document
        d = Document(str(docx))
        heads = [p.text for p in d.paragraphs if p.style.name.startswith("Heading")]
        check("docx: report opens and has the required sections", len(heads) >= 12, f"{len(heads)} headings")
    except Exception as e:
        check("docx: report opens", False, repr(e))

    width = max(len(n) for n, _, _ in results)
    print("\nValidation of", out)
    for name, ok, detail in results:
        print(f"  [{'PASS' if ok else 'FAIL'}] {name:<{width}}  {detail}")
    allok = all(ok for _, ok, _ in results)
    print("  RESULT:", "ALL CHECKS PASSED" if allok else "SOME CHECKS FAILED")
    return allok
