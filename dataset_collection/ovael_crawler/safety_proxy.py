"""Destination-validating forward proxy.

Every browser context is configured to send *all* traffic (top-level navigations, every redirect
hop, subresources, iframes, WebSockets) through its own instance of this proxy. Chromium does not
resolve proxied hostnames itself, so the proxy is the only component that resolves DNS. For each
connection it:

  1. resolves the hostname,
  2. rejects the connection if ANY resolved address is not globally routable
     (loopback, RFC1918 private, link-local, CGNAT, multicast, reserved, unspecified ...),
  3. connects to the address it validated (no second lookup => no DNS-rebinding window).

Playwright's request routing is not used for this because it is not invoked for redirect hops.
Blocked plain-HTTP requests get the connection closed without a response so a block page is never
recorded as a website response.
"""

from __future__ import annotations

import asyncio
import ipaddress
import socket
import time

from .domains import normalize_host

HEAD_LIMIT = 64 * 1024
DNS_TIMEOUT_S = 10.0
CONNECT_TIMEOUT_S = 15.0
HOP_HEADERS = {"proxy-connection", "proxy-authorization", "connection", "keep-alive"}


def is_public_ip(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    if isinstance(ip, ipaddress.IPv6Address):
        if ip.ipv4_mapped:
            return is_public_ip(ip.ipv4_mapped)
        if ip.sixtofour or ip.teredo:
            return False
    return ip.is_global and not ip.is_multicast and not ip.is_reserved and not ip.is_unspecified


class SafetyProxy:
    def __init__(self) -> None:
        self.events: list[dict] = []
        self.blocked: list[dict] = []
        self._server: asyncio.base_events.Server | None = None
        self._tasks: set[asyncio.Task] = set()
        self._writers: set[asyncio.StreamWriter] = set()
        self.port: int | None = None

    async def start(self) -> int:
        self._server = await asyncio.start_server(self._handle, "127.0.0.1", 0, limit=HEAD_LIMIT)
        self.port = self._server.sockets[0].getsockname()[1]
        return self.port

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.port}"

    async def stop(self) -> None:
        if self._server:
            self._server.close()
        for w in list(self._writers):
            w.close()
        for t in list(self._tasks):
            t.cancel()
        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)
        if self._server:
            try:
                await asyncio.wait_for(self._server.wait_closed(), 5)
            except (asyncio.TimeoutError, Exception):
                pass

    def last_event_for(self, host: str) -> dict | None:
        host = normalize_host(host)
        for ev in reversed(self.events):
            if ev["host"] == host:
                return ev
        return None

    def _log(self, host: str, port: int, decision: str, reason: str) -> None:
        ev = {"host": host, "port": port, "decision": decision, "reason": reason, "t": time.time()}
        self.events.append(ev)
        if decision == "blocked":
            self.blocked.append(ev)

    async def _resolve(self, host: str, port: int) -> tuple[list[str] | None, str]:
        """Return (validated addresses, reason). None => refuse."""
        try:
            literal = ipaddress.ip_address(host)
            return ([str(literal)], "ok") if is_public_ip(literal) else (None, "non_public_address")
        except ValueError:
            pass
        if host in ("localhost",) or host.endswith(".localhost") or host.endswith(".local"):
            return None, "non_public_hostname"
        loop = asyncio.get_running_loop()
        try:
            infos = await asyncio.wait_for(
                loop.getaddrinfo(host, port, type=socket.SOCK_STREAM), DNS_TIMEOUT_S)
        except asyncio.TimeoutError:
            return None, "dns_timeout"
        except socket.gaierror:
            return None, "dns_failure"
        addrs: list[str] = []
        for info in infos:
            ip = ipaddress.ip_address(info[4][0].split("%")[0])
            if not is_public_ip(ip):
                return None, "non_public_address"
            if str(ip) not in addrs:
                addrs.append(str(ip))
        # Prefer IPv4: many networks lack IPv6 connectivity.
        addrs.sort(key=lambda a: ":" in a)
        return (addrs, "ok") if addrs else (None, "dns_failure")

    async def _connect(self, host: str, port: int):
        addrs, reason = await self._resolve(host, port)
        if addrs is None:
            decision = "blocked" if reason.startswith("non_public") else "failed"
            self._log(host, port, decision, reason)
            return None
        last = "connect_failed"
        for addr in addrs[:4]:
            try:
                r, w = await asyncio.wait_for(asyncio.open_connection(addr, port, limit=HEAD_LIMIT),
                                              CONNECT_TIMEOUT_S)
                self._log(host, port, "allowed", "ok")
                return r, w
            except asyncio.TimeoutError:
                last = "connect_timeout"
            except ConnectionRefusedError:
                last = "connect_refused"
            except OSError:
                last = "connect_failed"
        self._log(host, port, "failed", last)
        return None

    async def _handle(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        task = asyncio.current_task()
        self._tasks.add(task)
        self._writers.add(writer)
        upstream_writer = None
        try:
            try:
                head = await asyncio.wait_for(reader.readuntil(b"\r\n\r\n"), 30)
            except (asyncio.IncompleteReadError, asyncio.LimitOverrunError, asyncio.TimeoutError):
                return
            lines = head.decode("latin-1").split("\r\n")
            try:
                method, target, version = lines[0].split(" ", 2)
            except ValueError:
                return
            if method.upper() == "CONNECT":
                host, port = _split_hostport(target, 443)
                conn = await self._connect(host, port)
                if conn is None:
                    writer.write(b"HTTP/1.1 403 Forbidden\r\nContent-Length: 0\r\n\r\n")
                    await writer.drain()
                    return
                up_r, upstream_writer = conn
                writer.write(b"HTTP/1.1 200 Connection Established\r\n\r\n")
                await writer.drain()
            else:
                if not target.lower().startswith("http://"):
                    return
                rest = target[7:]
                hostport, _, path = rest.partition("/")
                host, port = _split_hostport(hostport, 80)
                conn = await self._connect(host, port)
                if conn is None:
                    return  # close without response
                up_r, upstream_writer = conn
                headers = [h for h in lines[1:] if h and h.split(":", 1)[0].strip().lower() not in HOP_HEADERS]
                headers.append("Connection: close")
                req = f"{method} /{path} {version}\r\n" + "\r\n".join(headers) + "\r\n\r\n"
                upstream_writer.write(req.encode("latin-1"))
                await upstream_writer.drain()
            self._writers.add(upstream_writer)
            await asyncio.gather(_pipe(reader, upstream_writer), _pipe(up_r, writer))
        except (ConnectionError, OSError, asyncio.CancelledError):
            pass
        finally:
            for w in (writer, upstream_writer):
                if w is not None:
                    self._writers.discard(w)
                    try:
                        w.close()
                    except Exception:
                        pass
            self._tasks.discard(task)


def _split_hostport(value: str, default_port: int) -> tuple[str, int]:
    value = value.strip()
    if value.startswith("["):
        host, _, rest = value[1:].partition("]")
        port = int(rest[1:]) if rest.startswith(":") and rest[1:].isdigit() else default_port
        return normalize_host(host), port
    host, sep, port = value.rpartition(":")
    if sep and port.isdigit():
        return normalize_host(host), int(port)
    return normalize_host(value), default_port


async def _pipe(src: asyncio.StreamReader, dst: asyncio.StreamWriter) -> None:
    try:
        while True:
            chunk = await src.read(65536)
            if not chunk:
                break
            dst.write(chunk)
            await dst.drain()
    except (ConnectionError, OSError):
        pass
    finally:
        try:
            if dst.can_write_eof():
                dst.write_eof()
        except (OSError, RuntimeError):
            pass
