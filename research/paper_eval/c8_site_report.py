"""C8: for ~10 real sites, submit a real scan to the running backend (POST /api/scans), poll for
the finished report, and check the actual smart-report numbers against the A9 formulas.

Needs the backend running at BACKEND_URL (python -m uvicorn ovael.api.app:app, as started for
local dev). Does not modify backend state beyond the scans it creates (normal API usage).
"""
from __future__ import annotations

import time

import httpx

from common import save_csv, save_json

BACKEND_URL = "http://localhost:8000"
SITES = [
    (1, "https://google.com/"),
    (46, "https://netflix.com/"),
    (91, "https://nginx.com/"),
    (140, "https://discord.gg/"),
    (194, "https://adtrafficquality.google/"),
    (246, "https://telekom.net/"),
    (299, "https://springer.com/"),
    (342, "https://gnu.org/"),
    (390, "https://firefox-portal-detection.com/"),
    (500, "https://wikipedia.org/"),  # replaces huawei.com, which url_guard rejected (422) - see note
]

SEVERITY_POINTS = {"critical": 45, "high": 22, "medium": 10, "low": 4, "info": 0, "good": -6}
MINIMUMS = [(85, "critical"), (55, "high"), (25, "medium")]


def check_formulas(smart: dict, report: dict) -> dict:
    findings = smart["findings"]
    non_privacy = [f for f in findings if f["category"] != "privacy"]
    privacy_findings = [f for f in findings if f["category"] == "privacy"]
    points = [SEVERITY_POINTS[f["severity"]] for f in non_privacy]
    C = sum(p for p in points if p > 0)
    G = -sum(p for p in points if p < 0)
    T_expected = C - min(G, C / 2)
    M = report.get("risk_score_used", None)  # filled by caller from the detection
    R = min(100, sum(max(SEVERITY_POINTS[f["severity"]], 0) for f in privacy_findings))
    P = max(M or 0, R)
    S_expected = min(100, max(0, T_expected + 0.3 * P))

    # worst severity present, in SEVERITY_ORDER priority (critical > high > medium > low > info > good)
    order = ["critical", "high", "medium", "low", "info", "good"]
    present = {f["severity"] for f in non_privacy}
    worst = next((s for s in order if s in present), None)
    S_with_min = S_expected
    for floor, sev in MINIMUMS:
        if worst == sev:
            S_with_min = max(S_with_min, floor)
            break
    is_adult = smart.get("adult", False)
    if is_adult:
        S_with_min = max(S_with_min, 50)

    return {"C": C, "G": G, "T_expected": round(T_expected, 4), "M": M, "R": R, "P": P,
            "S_expected_before_minimums": round(S_expected, 4),
            "worst_non_privacy_severity": worst, "S_expected_with_minimums": round(S_with_min, 4),
            "S_reported": smart["score"],
            "matches_full_formula": abs(round(S_with_min, 1) - smart["score"]) < 0.15}


def main():
    rows = []
    with httpx.Client(timeout=120.0) as client:
        for rank, url in SITES:
            try:
                r = client.post(f"{BACKEND_URL}/api/scans", json={"url": url})
                r.raise_for_status()
                scan_id = r.json()["id"]
            except Exception as exc:
                rows.append({"rank": rank, "url": url, "error": f"submit failed: {exc}"})
                continue

            report = None
            for _ in range(60):
                time.sleep(2)
                d = client.get(f"{BACKEND_URL}/api/scans/{scan_id}").json()
                if d.get("status") in ("completed", "failed"):
                    report = d
                    break
            if report is None or report.get("status") != "completed":
                rows.append({"rank": rank, "url": url,
                            "error": f"scan did not complete: status={report.get('status') if report else 'timeout'}, "
                                     f"error={report.get('error') if report else None}"})
                continue

            smart = (report.get("report") or {}).get("smart")
            detection = report.get("detection") or {}
            if not smart:
                rows.append({"rank": rank, "url": url, "error": "no smart report in response",
                            "raw_status": report.get("status")})
                continue
            check = check_formulas(smart, {**(report.get("report") or {}),
                                           "risk_score_used": detection.get("risk_score")})
            rows.append({
                "rank": rank, "url": url, "verdict": smart["risk_level"], "headline": smart["verdict"],
                "model_label": detection.get("label"), "model_risk_score": detection.get("risk_score"),
                **check,
            })
            print(rank, url, "->", smart["risk_level"], smart["score"], check)

    save_json("C8_site_report_raw.json", rows)
    import pandas as pd
    save_csv("C8_site_report_sanity.csv", pd.DataFrame(rows))


if __name__ == "__main__":
    main()
