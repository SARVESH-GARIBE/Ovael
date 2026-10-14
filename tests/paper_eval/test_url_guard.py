"""Locks in the backend's pre-scan URL checker (ovael/scanner/url_guard.py): rejects private,
loopback and metadata addresses (after DNS resolution), unusual ports, and raw IPs. DNS is
monkeypatched to controlled values - no real resolution or connection happens.
"""
from __future__ import annotations

import socket

import pytest

from ovael.scanner.url_guard import UnsafeURL, check, normalize


@pytest.mark.parametrize("url", [
    "http://127.0.0.1/", "http://[::1]/", "http://10.0.0.1/", "http://192.168.1.1/",
])
def test_rejects_raw_ips_regardless_of_address_class(url):
    with pytest.raises(UnsafeURL, match="domain name, not an IP"):
        normalize(url)


@pytest.mark.parametrize("url", ["https://example.com:22/", "https://example.com:9999/"])
def test_rejects_unusual_ports(url):
    with pytest.raises(UnsafeURL, match="port"):
        normalize(url)


@pytest.mark.parametrize("url", ["https://example.com:80/", "https://example.com:443/",
                                 "https://example.com:8080/", "https://example.com:8443/"])
def test_allows_the_permitted_ports(url):
    normalize(url)  # must not raise


def _fake_getaddrinfo(answers: dict[str, list[str]]):
    async def fn(host, port, type=None):
        if host not in answers:
            raise socket.gaierror("no such host")
        return [(socket.AF_INET, type, 0, "", (ip, port or 0)) for ip in answers[host]]
    return fn


@pytest.mark.parametrize("host,ip,why", [
    ("private-test.com", "10.0.0.5", "private RFC1918"),
    ("loopback-test.com", "127.0.0.1", "loopback"),
    ("metadata-test.com", "169.254.169.254", "cloud metadata"),
    ("linklocal-test.com", "169.254.1.1", "link-local"),
])
async def test_check_rejects_hosts_resolving_to_non_public_addresses(monkeypatch, host, ip, why):
    import asyncio

    loop = asyncio.get_running_loop()
    monkeypatch.setattr(loop, "getaddrinfo", _fake_getaddrinfo({host: [ip]}))
    with pytest.raises(UnsafeURL, match="non-public address"):
        await check(f"https://{host}/")


async def test_check_accepts_a_host_resolving_to_a_public_address(monkeypatch):
    import asyncio

    loop = asyncio.get_running_loop()
    monkeypatch.setattr(loop, "getaddrinfo", _fake_getaddrinfo({"public-test.com": ["93.184.216.34"]}))
    out = await check("https://public-test.com/")
    assert out.hostname == "public-test.com"


async def test_check_rejects_a_host_that_does_not_resolve(monkeypatch):
    import asyncio

    loop = asyncio.get_running_loop()
    monkeypatch.setattr(loop, "getaddrinfo", _fake_getaddrinfo({}))
    with pytest.raises(UnsafeURL, match="does not resolve"):
        await check("https://nowhere-test.com/")
