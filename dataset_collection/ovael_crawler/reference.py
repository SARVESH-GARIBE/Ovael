"""Reference data: DuckDuckGo Tracker Data Set (built from Tracker Radar), URLhaus host list,
and Tranco list identification. Downloads are stored under reference/ with metadata sidecars."""

from __future__ import annotations

import csv
import hashlib
import json
import re
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from . import config
from .domains import normalize_host, registrable_domain

TDS_SOURCE_NAME = "DuckDuckGo Tracker Data Set (extension-tds.json, built from DuckDuckGo Tracker Radar)"


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _download(url: str, dest: Path, meta_path: Path) -> dict:
    dest.parent.mkdir(parents=True, exist_ok=True)
    req = urllib.request.Request(url, headers={"User-Agent": "ovael-dataset-collection/1.0"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        data = resp.read()
        headers = {k.lower(): v for k, v in resp.headers.items()}
    tmp = dest.with_suffix(dest.suffix + ".tmp")
    tmp.write_bytes(data)
    tmp.replace(dest)
    meta = {
        "url": url,
        "retrieved_at": utcnow(),
        "http_last_modified": headers.get("last-modified"),
        "http_etag": headers.get("etag"),
        "sha256": sha256_file(dest),
        "bytes": len(data),
    }
    meta_path.write_text(json.dumps(meta, indent=2))
    return meta


def fetch_tds() -> dict:
    meta = _download(config.TDS_URL, config.TDS_PATH, config.TDS_META_PATH)
    tds = json.loads(config.TDS_PATH.read_text())
    meta["built_with"] = tds.get("_builtWith")
    meta["tracker_count"] = len(tds.get("trackers", {}))
    meta["entity_count"] = len(tds.get("entities", {}))
    config.TDS_META_PATH.write_text(json.dumps(meta, indent=2))
    return meta


def fetch_urlhaus() -> dict:
    return _download(config.URLHAUS_URL, config.URLHAUS_PATH, config.URLHAUS_META_PATH)


def identify_tranco(csv_path: Path) -> dict:
    """Identify which Tranco list the local CSV is by comparing its first 1000 rows with the
    published lists for the file date and the two preceding days."""
    import time
    from datetime import timedelta
    from urllib.error import HTTPError
    sha = sha256_file(csv_path)
    prev = load_json(config.TRANCO_META_PATH)
    if prev and prev.get("verified") and prev.get("source_file_sha256") == sha:
        return prev

    def get(url: str) -> bytes:
        for i in range(4):
            try:
                with urllib.request.urlopen(url, timeout=60) as r:
                    return r.read()
            except HTTPError as e:
                if e.code != 429 or i == 3:
                    raise
                time.sleep(15 * (i + 1))  # Tranco API rate limit
        raise RuntimeError("unreachable")

    mtime = datetime.fromtimestamp(csv_path.stat().st_mtime, timezone.utc)
    with open(csv_path, newline="") as f:
        local = [",".join(r) for _, r in zip(range(1000), csv.reader(f))]
    tried = []
    result = {"source_file": csv_path.name, "source_file_sha256": sha,
              "source_file_mtime_utc": mtime.isoformat(timespec="seconds"), "list_id": None,
              "verified": False, "verification_method": "first 1000 rows identical to tranco-list.eu download"}
    for delta in (0, 1, -1, -2):
        d = (mtime.date() + timedelta(days=delta)).isoformat()
        try:
            info = json.loads(get(f"https://tranco-list.eu/api/lists/date/{d}"))
            list_id = info["list_id"]
            remote = [ln.strip() for ln in get(f"https://tranco-list.eu/download/{list_id}/1000").decode().splitlines()
                      if ln.strip()]
        except Exception as e:  # network problems are recorded, not hidden
            tried.append({"date": d, "error": repr(e)})
            continue
        match = remote == [ln.strip() for ln in local]
        tried.append({"date": d, "list_id": list_id, "match": match})
        if match:
            result.update(list_id=list_id, verified=True, list_date=d, list_created_on=info.get("created_on"),
                          list_configuration=info.get("configuration"),
                          list_permalink=f"https://tranco-list.eu/list/{list_id}/1000000")
            break
    result["candidates_checked"] = tried
    result["checked_at"] = utcnow()
    config.TRANCO_META_PATH.parent.mkdir(parents=True, exist_ok=True)
    config.TRANCO_META_PATH.write_text(json.dumps(result, indent=2))
    return result


def load_json(path: Path) -> dict | None:
    return json.loads(path.read_text()) if path.exists() else None


def load_urlhaus_hosts() -> set[str] | None:
    if not config.URLHAUS_PATH.exists():
        return None
    hosts = set()
    for line in config.URLHAUS_PATH.read_text(errors="replace").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split()
        hosts.add(normalize_host(parts[-1]))
    return hosts


def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")


class TrackerReference:
    """Domain-level matcher over the DuckDuckGo TDS.

    A hostname matches when it, or any parent domain of it, is a key in `trackers`.
    Absence from the list means "not in reference", never "benign"."""

    def __init__(self, path: Path = config.TDS_PATH, meta_path: Path = config.TDS_META_PATH):
        if not path.exists():
            raise FileNotFoundError(f"{path} missing - run: python -m ovael_crawler fetch-references")
        tds = json.loads(path.read_text())
        self.trackers: dict = tds.get("trackers", {})
        self.domain_entity: dict = tds.get("domains", {})
        self.meta = load_json(meta_path) or {}
        self.version = {
            "source": TDS_SOURCE_NAME,
            "url": self.meta.get("url", config.TDS_URL),
            "retrieved_at": self.meta.get("retrieved_at"),
            "http_last_modified": self.meta.get("http_last_modified"),
            "sha256": self.meta.get("sha256") or sha256_file(path),
            "built_with": tds.get("_builtWith"),
            "tracker_entries": len(self.trackers),
        }
        self.categories = sorted({c for t in self.trackers.values() for c in t.get("categories", [])})
        self._cache: dict[str, dict] = {}

    def entity_of(self, host: str) -> str | None:
        host = normalize_host(host)
        labels = host.split(".")
        for i in range(len(labels) - 1):
            ent = self.domain_entity.get(".".join(labels[i:]))
            if ent:
                return ent
        return None

    def match(self, host: str) -> dict:
        host = normalize_host(host)
        if host in self._cache:
            return self._cache[host]
        labels = host.split(".")
        entry, key = None, None
        for i in range(len(labels) - 1):
            cand = ".".join(labels[i:])
            if cand in self.trackers:
                entry, key = self.trackers[cand], cand
                break
        if entry is None:
            res = {"match_status": "not_in_reference", "matched_tracker_domain": None,
                   "entity": self.entity_of(host)}
        else:
            owner = entry.get("owner") or {}
            res = {
                "match_status": "matched",
                "matched_tracker_domain": key,
                "entity": self.entity_of(host) or owner.get("name"),
                "owner_name": owner.get("name"),
                "owner_display_name": owner.get("displayName"),
                "owned_by": owner.get("ownedBy"),
                "categories": list(entry.get("categories", [])),
                "categories_available": bool(entry.get("categories")),
                "fingerprinting_metadata_available": "fingerprinting" in entry,
                "fingerprinting_score": entry.get("fingerprinting"),
                "cookies_prevalence": entry.get("cookies"),
                "prevalence": entry.get("prevalence"),
                "default_action": entry.get("default"),
            }
        self._cache[host] = res
        return res

    def same_entity(self, host_a: str, host_b: str) -> bool | None:
        a, b = self.entity_of(host_a), self.entity_of(host_b)
        if a is None or b is None:
            return None
        return a == b


def registrable_or_host(host: str) -> str:
    return registrable_domain(host) or normalize_host(host)
