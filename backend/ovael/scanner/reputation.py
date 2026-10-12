"""Reputation lookups for the smart report: popularity rank, bare-name resolution, lookalike
domains, the URLhaus malware host list, and domain age from RDAP.

The Tranco top-1M list (dataset_collection/top-1m.csv) is memory-mapped and searched with a
regex rather than loaded into a dict: a lookup costs ~30-150 ms and no memory per process.
"""

from __future__ import annotations

import logging
import mmap
import re
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path

import httpx

log = logging.getLogger(__name__)

LOOKALIKE_TOP_N = 5000  # brands worth impersonating
_HOMOGLYPHS = (("rn", "m"), ("vv", "w"), ("0", "o"), ("1", "l"), ("3", "e"), ("5", "s"), ("@", "a"))


def _crawler_path() -> Path:
    from ..config import get_settings  # noqa: PLC0415

    return get_settings().crawler_path


class Tranco:
    def __init__(self, path: Path):
        self.path = path
        self._mm: mmap.mmap | None = None
        self._top: dict[str, tuple[int, list[str]]] | None = None

    @property
    def available(self) -> bool:
        return self.path.exists()

    def _map(self) -> mmap.mmap | None:
        if self._mm is None and self.available:
            with open(self.path, "rb") as f:
                self._mm = mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ)
        return self._mm

    @lru_cache(maxsize=4096)
    def rank(self, domain: str) -> int | None:
        mm = self._map()
        if mm is None or not domain:
            return None
        m = re.search(rb"^(\d+)," + re.escape(domain.encode()) + rb"\r?$", mm, re.M)
        return int(m.group(1)) if m else None

    @lru_cache(maxsize=4096)
    def best_match_for_name(self, label: str) -> str | None:
        """Highest-ranked domain whose first label is `label` ('rummycircle' -> 'rummycircle.com')."""
        mm = self._map()
        if mm is None or not re.fullmatch(r"[a-z0-9-]{1,63}", label):
            return None
        m = re.search(rb"^\d+,(" + re.escape(label.encode()) + rb"\.[^\r\n]+?)\r?$", mm, re.M)
        return m.group(1).decode() if m else None

    def top_labels(self) -> dict[str, tuple[int, list[str]]]:
        """First label -> (best rank, domains), for the top LOOKALIKE_TOP_N sites."""
        if self._top is None:
            self._top = {}
            if self.available:
                with open(self.path, encoding="ascii", errors="replace") as f:
                    for i, line in enumerate(f):
                        if i >= LOOKALIKE_TOP_N:
                            break
                        domain = line.strip().split(",", 1)[-1]
                        label = domain.split(".", 1)[0]
                        if len(label) >= 4:
                            self._top.setdefault(label, (i + 1, []))[1].append(domain)
        return self._top


@lru_cache(maxsize=1)
def tranco() -> Tranco:
    return Tranco(_crawler_path() / "top-1m.csv")


def resolve_name(name: str) -> str:
    """A bare site name typed without a TLD: pick the most popular matching domain, else .com."""
    label = re.sub(r"[\s_]+", "", name.lower())
    try:
        found = tranco().best_match_for_name(label)
    except Exception as exc:  # the list is an aid, never a reason to fail the scan
        log.warning("tranco lookup failed: %s", exc)
        found = None
    return found or f"{label}.com"


def _distance(a: str, b: str, limit: int) -> int:
    """Levenshtein distance with an early exit once it exceeds `limit`."""
    if abs(len(a) - len(b)) > limit:
        return limit + 1
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        if min(cur) > limit:
            return limit + 1
        prev = cur
    return prev[-1]


def lookalike_of(domain: str, rank: int | None) -> dict | None:
    """Is this domain imitating a popular one? Popular domains themselves never are."""
    if rank is not None and rank <= 50_000:
        return None
    label = domain.split(".", 1)[0]
    top = tranco().top_labels()
    if not top or len(label) < 4:
        return None
    if label in top:  # same name, different ending: instagram.co vs instagram.com
        targets = [d for d in top[label][1] if d != domain]
        if targets:
            return {"target": targets[0], "kind": "same_name_other_tld"}
    unglyphed = label
    for a, b in _HOMOGLYPHS:
        unglyphed = unglyphed.replace(a, b)
    if unglyphed != label and unglyphed in top:
        return {"target": top[unglyphed][1][0], "kind": "lookalike_characters"}
    parts = [p for p in re.split(r"[-.]", label) if len(p) >= 5]
    for brand, (brand_rank, domains) in top.items():
        # Generic words ("store", "online") rank too, so only distinctive names from the very top count.
        if len(brand) < 6 or brand == label or brand_rank > 1000:
            continue
        if brand in parts or (brand in label and len(label) - len(brand) >= 3):
            return {"target": domains[0], "kind": "contains_brand"}
        limit = 1 if len(brand) < 9 else 2
        if _distance(label, brand, limit) <= limit:
            return {"target": domains[0], "kind": "typo"}
    return None


@lru_cache(maxsize=1)
def urlhaus_hosts() -> frozenset[str]:
    path = _crawler_path() / "reference" / "urlhaus-hostfile.txt"
    if not path.exists():
        return frozenset()
    hosts = set()
    for line in path.read_text(errors="replace").splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            hosts.add(line.split()[-1].strip(".").lower())
    return frozenset(hosts)


@lru_cache(maxsize=1)
def adult_domains() -> frozenset[str]:
    path = Path(__file__).parent / "lists" / "adult_domains.txt"
    lines = (l.strip().lower() for l in path.read_text().splitlines())
    return frozenset(l for l in lines if l and not l.startswith("#"))


def is_adult_domain(host: str) -> bool:
    """True if `host` or any parent domain is on the curated adult-site list."""
    listed = adult_domains()
    labels = host.strip(".").lower().split(".")
    return any(".".join(labels[i:]) in listed for i in range(len(labels) - 1))


def malware_listed(hosts: list[str]) -> list[str]:
    bad = urlhaus_hosts()
    return sorted({h for h in hosts if h in bad})


async def rdap(domain: str, timeout_s: float = 8.0) -> dict | None:
    """Registration date, expiry and registrar from RDAP (the successor of WHOIS)."""
    try:
        async with httpx.AsyncClient(timeout=timeout_s, follow_redirects=True,
                                     headers={"Accept": "application/rdap+json"}) as client:
            r = await client.get(f"https://rdap.org/domain/{domain}")
        if r.status_code != 200:
            return None
        data = r.json()
    except Exception as exc:
        log.info("rdap lookup for %s failed: %s", domain, exc)
        return None
    events = {e.get("eventAction"): e.get("eventDate") for e in data.get("events", []) if isinstance(e, dict)}
    registrar = None
    for ent in data.get("entities", []):
        if "registrar" in (ent.get("roles") or []):
            for item in (ent.get("vcardArray") or [None, []])[1]:
                if item and item[0] == "fn":
                    registrar = item[3]
    created = events.get("registration")
    age_days = None
    if created:
        try:
            dt = datetime.fromisoformat(created.replace("Z", "+00:00"))
            age_days = (datetime.now(timezone.utc) - dt).days
        except ValueError:
            pass
    return {"registered": created, "expires": events.get("expiration"), "updated": events.get("last changed"),
            "registrar": registrar, "age_days": age_days}
