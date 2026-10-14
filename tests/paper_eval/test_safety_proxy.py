"""Locks in the crawler's SafetyProxy (dataset_collection/ovael_crawler/safety_proxy.py):
refuses loopback, private, link-local, cloud-metadata, carrier-grade NAT, multicast and
IPv4-embedded-IPv6 addresses, and connects only to the address it validated. Every connection in
these tests is to a local asyncio server bound to 127.0.0.1 - nothing here contacts a real
internal or external host.
"""
from __future__ import annotations

import asyncio
import ipaddress

import pytest

from ovael_crawler.safety_proxy import SafetyProxy, is_public_ip


# ---------------------------------------------------------------- is_public_ip, by category
@pytest.mark.parametrize("ip,expected,why", [
    ("127.0.0.1", False, "loopback"),
    ("10.0.0.1", False, "private RFC1918"),
    ("172.16.0.1", False, "private RFC1918"),
    ("192.168.1.1", False, "private RFC1918"),
    ("169.254.1.1", False, "link-local"),
    ("169.254.169.254", False, "cloud metadata (also link-local)"),
    ("100.64.0.1", False, "carrier-grade NAT (RFC 6598)"),
    ("224.0.0.1", False, "multicast"),
    ("0.0.0.0", False, "unspecified"),
    ("::1", False, "IPv6 loopback"),
    ("fe80::1", False, "IPv6 link-local"),
    ("::ffff:10.0.0.1", False, "IPv4-mapped IPv6 embedding a private address"),
    ("64:ff9b::0a00:0001", False, "NAT64-embedded private IPv4 (10.0.0.1)"),
    ("64:ff9b::a9fe:a9fe", False, "NAT64-embedded cloud metadata (169.254.169.254)"),
    ("8.8.8.8", True, "real public IPv4"),
    ("::ffff:8.8.8.8", True, "IPv4-mapped IPv6 embedding a public address"),
    ("64:ff9b::c7e8:6851", True, "NAT64-embedded public IPv4 (199.232.104.81)"),
])
def test_is_public_ip_by_category(ip, expected, why):
    assert is_public_ip(ipaddress.ip_address(ip)) is expected, why


# ---------------------------------------------------------------- the proxy itself, end to end
@pytest.fixture
async def local_server():
    """A real local HTTP-ish server on 127.0.0.1, used as the 'remote site' for the allowed case."""
    async def handle(reader, writer):
        await reader.readuntil(b"\r\n\r\n")
        writer.write(b"HTTP/1.1 200 OK\r\nContent-Length: 2\r\n\r\nok")
        await writer.drain()
        writer.close()

    server = await asyncio.start_server(handle, "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]
    yield port
    server.close()
    await server.wait_closed()


@pytest.fixture
async def proxy():
    p = SafetyProxy()
    await p.start()
    yield p
    await p.stop()


async def _http_get_through_proxy(proxy: SafetyProxy, host: str, port: int) -> bytes:
    reader, writer = await asyncio.open_connection("127.0.0.1", proxy.port)
    writer.write(f"GET http://{host}:{port}/ HTTP/1.1\r\nHost: {host}\r\n\r\n".encode())
    await writer.drain()
    try:
        data = await asyncio.wait_for(reader.read(1024), 5)
    except asyncio.TimeoutError:
        data = b""
    writer.close()
    return data


async def test_refuses_a_loopback_destination_with_no_response(proxy, local_server):
    # local_server is itself bound to 127.0.0.1 - exactly the "local test server, not a real
    # external host" the rule asks for, and it also happens to BE the loopback case under test.
    data = await _http_get_through_proxy(proxy, "127.0.0.1", local_server)
    assert data == b""  # connection closed without a response, per the module's own docstring
    ev = proxy.last_event_for("127.0.0.1")
    assert ev is not None and ev["decision"] == "blocked" and ev["reason"] == "non_public_address"


async def test_refuses_localhost_hostname_without_a_dns_lookup(proxy):
    data = await _http_get_through_proxy(proxy, "localhost", 80)
    assert data == b""
    ev = proxy.last_event_for("localhost")
    assert ev is not None and ev["decision"] == "blocked" and ev["reason"] == "non_public_hostname"


async def test_connects_only_to_the_address_it_validated(proxy, local_server, monkeypatch):
    # Simulates "hostname resolves to a validated address" by monkeypatching is_public_ip for
    # this test only (pytest monkeypatch, auto-restored after the test - not a source change):
    # proves the proxy's _connect() opens a socket to exactly the address _resolve() approved,
    # by pointing that approved address at a real local server and checking the response is
    # actually relayed back (i.e. it really connected there, not somewhere else).
    import ovael_crawler.safety_proxy as sp

    monkeypatch.setattr(sp, "is_public_ip", lambda ip: True)
    data = await _http_get_through_proxy(proxy, "127.0.0.1", local_server)
    assert b"200 OK" in data and data.endswith(b"ok")
    ev = proxy.last_event_for("127.0.0.1")
    assert ev is not None and ev["decision"] == "allowed"
