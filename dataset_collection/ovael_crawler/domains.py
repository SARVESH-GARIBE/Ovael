"""Hostname / registrable-domain helpers and URL sanitisation."""

from __future__ import annotations

import ipaddress
from functools import lru_cache
from urllib.parse import urlsplit

import tldextract

# Bundled Public Suffix List snapshot only: no network fetch, reproducible results.
_EXTRACT = tldextract.TLDExtract(suffix_list_urls=(), cache_dir=None)
PSL_SOURCE = f"tldextract {tldextract.__version__} bundled Public Suffix List snapshot (ICANN section)"


def normalize_host(host: str | None) -> str:
    return (host or "").strip().strip(".").lower()


def is_ip_literal(host: str) -> bool:
    try:
        ipaddress.ip_address(host.strip("[]"))
        return True
    except ValueError:
        return False


@lru_cache(maxsize=200_000)
def registrable_domain(host: str | None) -> str | None:
    """eTLD+1 of a hostname (www.bbc.co.uk -> bbc.co.uk). None for IPs/unparseable hosts."""
    host = normalize_host(host)
    if not host or is_ip_literal(host):
        return None
    ext = _EXTRACT(host)
    if not ext.suffix or not ext.domain:
        return None
    return f"{ext.domain}.{ext.suffix}"


def hostname_of(url: str | None) -> str:
    try:
        return normalize_host(urlsplit(url or "").hostname)
    except ValueError:
        return ""


def sanitize_url(url: str | None, max_path_chars: int = 200) -> dict:
    """Split a URL into non-sensitive parts. Query strings, fragments and userinfo are dropped;
    only the number of query parameters is kept."""
    if not url:
        return {"url": None, "scheme": None, "hostname": None, "query_param_count": 0}
    try:
        parts = urlsplit(url)
        scheme = parts.scheme.lower()
        host = normalize_host(parts.hostname)
        port = parts.port
    except ValueError:
        return {"url": None, "scheme": None, "hostname": None, "query_param_count": 0}
    if scheme not in ("http", "https"):
        # data:, blob:, about:, chrome-error: ... keep only the scheme.
        return {"url": f"{scheme}:", "scheme": scheme, "hostname": None, "query_param_count": 0}
    path = parts.path or "/"
    if len(path) > max_path_chars:
        path = path[:max_path_chars] + "...[truncated]"
    netloc = f"[{host}]" if ":" in host else host
    if port and not ((scheme == "http" and port == 80) or (scheme == "https" and port == 443)):
        netloc += f":{port}"
    qcount = len([p for p in parts.query.split("&") if p]) if parts.query else 0
    return {"url": f"{scheme}://{netloc}{path}", "scheme": scheme, "hostname": host, "query_param_count": qcount}


def origin_of(url: str | None) -> str | None:
    try:
        p = urlsplit(url or "")
        if p.scheme not in ("http", "https") or not p.hostname:
            return None
        port = p.port or (443 if p.scheme == "https" else 80)
        return f"{p.scheme}://{normalize_host(p.hostname)}:{port}"
    except ValueError:
        return None
