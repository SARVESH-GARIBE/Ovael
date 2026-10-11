"""URL check before any scan (architecture section 4.2 step 2 and 7.1).

Rejects anything but http(s), over-long URLs, embedded credentials, unusual ports, and any host
that resolves to a non-public address (private, loopback, link-local, CGNAT, multicast, reserved,
cloud metadata). This is the first gate. The crawler's SafetyProxy is the second: it re-checks
every connection the browser makes, including redirects and subresources, and pins the address it
validated, so a DNS-rebinding trick between this check and the visit gets nowhere.
"""

from __future__ import annotations

import asyncio
import ipaddress
import socket
from dataclasses import dataclass
from urllib.parse import urlsplit, urlunsplit

import tldextract

ALLOWED_PORTS = {None, 80, 443, 8080, 8443}
_extract = tldextract.TLDExtract(suffix_list_urls=())  # bundled suffix list, no network fetch


class UnsafeURL(ValueError):
    pass


@dataclass(frozen=True)
class CheckedURL:
    url: str
    hostname: str
    domain: str  # registrable domain, used as the cache key


NAT64_PREFIX = ipaddress.ip_network("64:ff9b::/96")


def is_public_ip(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    if isinstance(ip, ipaddress.IPv6Address):
        if ip.ipv4_mapped:
            return is_public_ip(ip.ipv4_mapped)
        if ip in NAT64_PREFIX:  # NAT64 (RFC 6052): judge the IPv4 address embedded in the last 32 bits
            return is_public_ip(ipaddress.IPv4Address(int(ip) & 0xFFFFFFFF))
        if ip.sixtofour or ip.teredo:
            return False
    return ip.is_global and not ip.is_multicast and not ip.is_reserved and not ip.is_unspecified


def normalize(raw: str, max_length: int = 2048) -> CheckedURL:
    raw = (raw or "").strip()
    if not raw:
        raise UnsafeURL("enter a URL")
    if len(raw) > max_length:
        raise UnsafeURL(f"URL is longer than {max_length} characters")
    if "://" not in raw:
        raw = "https://" + raw
    parts = urlsplit(raw)
    if parts.scheme not in ("http", "https"):
        raise UnsafeURL("only http and https URLs can be scanned")
    if parts.username or parts.password:
        raise UnsafeURL("URLs with credentials are not allowed")
    host = (parts.hostname or "").rstrip(".").lower()
    if not host:
        raise UnsafeURL("URL has no host")
    try:
        port = parts.port
    except ValueError:
        raise UnsafeURL("invalid port")
    if port not in ALLOWED_PORTS:
        raise UnsafeURL(f"port {port} is not allowed")
    try:
        ip = ipaddress.ip_address(host.strip("[]"))
    except ValueError:
        ip = None
    if ip is not None:
        raise UnsafeURL("scan a domain name, not an IP address")
    ext = _extract(host)
    if not ext.suffix:
        raise UnsafeURL("host is not a public domain name")
    domain = f"{ext.domain}.{ext.suffix}"
    url = urlunsplit((parts.scheme, parts.netloc.lower(), parts.path or "/", parts.query, ""))
    return CheckedURL(url=url, hostname=host, domain=domain)


async def check(raw: str, max_length: int = 2048, resolve_timeout_s: float = 5.0) -> CheckedURL:
    checked = normalize(raw, max_length)
    loop = asyncio.get_running_loop()
    try:
        infos = await asyncio.wait_for(
            loop.getaddrinfo(checked.hostname, None, type=socket.SOCK_STREAM), resolve_timeout_s)
    except (socket.gaierror, asyncio.TimeoutError):
        raise UnsafeURL(f"{checked.hostname} does not resolve")
    addresses = {ipaddress.ip_address(info[4][0].split("%")[0]) for info in infos}
    if not addresses:
        raise UnsafeURL(f"{checked.hostname} does not resolve")
    bad = [str(a) for a in addresses if not is_public_ip(a)]
    if bad:
        raise UnsafeURL(f"{checked.hostname} resolves to a non-public address")
    return checked
