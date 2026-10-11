"""Select the websites for a run (Tranco top-N by rank, or the smoke-test list)."""

from __future__ import annotations

import csv
from pathlib import Path
from urllib.parse import urlsplit

from .domains import is_ip_literal, normalize_host, registrable_domain
from .reference import load_urlhaus_hosts

SELECTION_METHOD = (
    "Iterate the Tranco list in ascending rank order; normalise each hostname (lower-case, strip "
    "trailing dot); compute its registrable domain (eTLD+1, Public Suffix List). Skip entries whose "
    "registrable domain was already selected (so www.example.com and example.com count once), "
    "IP literals/unparseable hosts, and hosts listed in the URLhaus malware host list. Take the "
    "first N remaining entries."
)


def _entry(website_id: str, rank: int | None, domain: str, url: str | None, regd: str | None) -> dict:
    if url:
        candidates = [url]
    else:
        candidates = [f"https://{domain}/"]
        if not domain.startswith("www."):
            candidates.append(f"https://www.{domain}/")
        candidates.append(f"http://{domain}/")
    return {"website_id": website_id, "tranco_rank": rank, "original_domain": domain,
            "original_url": candidates[0], "candidate_urls": candidates,
            "initial_registrable_domain": regd}


def _malicious_check(host: str, bad: set[str] | None) -> bool:
    if bad is None:
        return False
    return host in bad or f"www.{host}" in bad or host.removeprefix("www.") in bad


def select_tranco(csv_path: Path, n: int) -> tuple[list[dict], list[dict], bool]:
    bad = load_urlhaus_hosts()
    selected, skipped, seen = [], [], set()
    with open(csv_path, newline="") as f:
        for row in csv.reader(f):
            if len(selected) >= n:
                break
            if len(row) < 2 or not row[0].strip().isdigit():
                continue
            rank, host = int(row[0]), normalize_host(row[1])
            regd = registrable_domain(host)
            if not host or is_ip_literal(host) or regd is None:
                skipped.append({"tranco_rank": rank, "domain": host, "reason": "unparseable_or_ip"})
            elif regd in seen:
                skipped.append({"tranco_rank": rank, "domain": host, "reason": f"duplicate_registrable_domain:{regd}"})
            elif _malicious_check(host, bad):
                skipped.append({"tranco_rank": rank, "domain": host, "reason": "listed_in_urlhaus"})
            else:
                seen.add(regd)
                selected.append(_entry(f"T{rank:07d}", rank, host, None, regd))
    return selected, skipped, bad is not None


def select_list(path: Path) -> tuple[list[dict], list[dict], bool]:
    """Smoke-test list: one hostname or full URL per line; '#' starts a comment."""
    bad = load_urlhaus_hosts()
    selected, skipped, seen = [], [], set()
    for i, line in enumerate(path.read_text().splitlines(), 1):
        line = line.split("#", 1)[0].strip()
        if not line:
            continue
        url = line if "://" in line else None
        host = normalize_host(urlsplit(line).hostname if url else line)
        regd = registrable_domain(host)
        key = regd or host
        if key in seen:
            skipped.append({"line": i, "domain": host, "reason": f"duplicate_registrable_domain:{key}"})
            continue
        if _malicious_check(host, bad):
            skipped.append({"line": i, "domain": host, "reason": "listed_in_urlhaus"})
            continue
        seen.add(key)
        selected.append(_entry(f"S{len(selected) + 1:04d}", None, host, url, regd))
    return selected, skipped, bad is not None
