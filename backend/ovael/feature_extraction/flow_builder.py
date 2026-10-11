"""Groups packets into bidirectional 5-tuple flows and turns each finished flow into a feature vector.

A flow is emitted when it closes (FIN from both sides, or RST), when it hits the packet limit, when
it has been active longer than `active_timeout_s`, or when it has been idle for `idle_timeout_s`.
The packet-limit and active-timeout exits matter for floods and slow attacks: without them a flood
is one endless flow and Slowloris never produces a verdict.

This module has no packet-capture dependency. The sandbox sensor feeds it packets from Scapy; tests
and the simulator feed it plain `Packet` objects.
"""

from __future__ import annotations

import math
import statistics
from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import datetime, timezone

from .network_schema import NETWORK_FEATURES


@dataclass(slots=True)
class Packet:
    ts: float
    src_ip: str
    dst_ip: str
    src_port: int
    dst_port: int
    protocol: int  # 6 TCP, 17 UDP, 1 ICMP
    size: int
    flags: str = ""  # TCP flags as letters, e.g. "S", "SA", "PA", "F", "R"
    window: int = 0


@dataclass
class _Flow:
    key: tuple
    src_ip: str
    dst_ip: str
    src_port: int
    dst_port: int
    protocol: int
    first_ts: float
    last_ts: float
    fwd_sizes: list[int] = field(default_factory=list)
    bwd_sizes: list[int] = field(default_factory=list)
    times: list[float] = field(default_factory=list)
    fwd_times: list[float] = field(default_factory=list)
    flags: dict[str, int] = field(default_factory=lambda: defaultdict(int))
    init_win_fwd: int = 0
    fin_fwd: bool = False
    fin_bwd: bool = False
    rst: bool = False
    src_conn_rate_10s: int = 0
    src_distinct_dst_ports_10s: int = 0

    @property
    def packet_count(self) -> int:
        return len(self.times)


@dataclass
class FinishedFlow:
    features: dict[str, float]
    meta: dict


def _mean(xs: list[float]) -> float:
    return float(statistics.fmean(xs)) if xs else 0.0


def _std(xs: list[float]) -> float:
    return float(statistics.pstdev(xs)) if len(xs) > 1 else 0.0


def _gaps(ts: list[float]) -> list[float]:
    return [b - a for a, b in zip(ts, ts[1:])]


class FlowBuilder:
    def __init__(self, idle_timeout_s: float = 5.0, active_timeout_s: float = 15.0,
                 packet_limit: int = 200, context_window_s: float = 10.0):
        self.idle_timeout_s = idle_timeout_s
        self.active_timeout_s = active_timeout_s
        self.packet_limit = packet_limit
        self.context_window_s = context_window_s
        self._flows: dict[tuple, _Flow] = {}
        self._src_history: dict[str, deque] = defaultdict(deque)  # src_ip -> (ts, dst_port)

    @staticmethod
    def _key(p: Packet) -> tuple:
        a, b = (p.src_ip, p.src_port), (p.dst_ip, p.dst_port)
        return (p.protocol, *(a + b if a <= b else b + a))

    def _context(self, src_ip: str, ts: float, dst_port: int) -> tuple[int, int]:
        hist = self._src_history[src_ip]
        hist.append((ts, dst_port))
        while hist and ts - hist[0][0] > self.context_window_s:
            hist.popleft()
        return len(hist), len({port for _, port in hist})

    def add(self, p: Packet) -> list[FinishedFlow]:
        done = self.expire(p.ts)
        key = self._key(p)
        flow = self._flows.get(key)
        if flow is None:
            flow = _Flow(key=key, src_ip=p.src_ip, dst_ip=p.dst_ip, src_port=p.src_port,
                         dst_port=p.dst_port, protocol=p.protocol, first_ts=p.ts, last_ts=p.ts,
                         init_win_fwd=p.window)
            flow.src_conn_rate_10s, flow.src_distinct_dst_ports_10s = self._context(p.src_ip, p.ts, p.dst_port)
            self._flows[key] = flow
        forward = p.src_ip == flow.src_ip and p.src_port == flow.src_port
        (flow.fwd_sizes if forward else flow.bwd_sizes).append(p.size)
        flow.times.append(p.ts)
        if forward:
            flow.fwd_times.append(p.ts)
        flow.last_ts = p.ts
        for letter, name in (("S", "syn"), ("A", "ack"), ("F", "fin"), ("R", "rst"), ("P", "psh")):
            if letter in p.flags:
                flow.flags[name] += 1
        if "F" in p.flags:
            if forward:
                flow.fin_fwd = True
            else:
                flow.fin_bwd = True
        if "R" in p.flags:
            flow.rst = True

        if (flow.rst or (flow.fin_fwd and flow.fin_bwd) or flow.packet_count >= self.packet_limit
                or flow.last_ts - flow.first_ts >= self.active_timeout_s):
            done.append(self._finish(self._flows.pop(key)))
        return done

    def expire(self, now: float) -> list[FinishedFlow]:
        stale = [k for k, f in self._flows.items() if now - f.last_ts >= self.idle_timeout_s]
        return [self._finish(self._flows.pop(k)) for k in stale]

    def flush(self) -> list[FinishedFlow]:
        flows = [self._finish(f) for f in self._flows.values()]
        self._flows.clear()
        return flows

    def _finish(self, f: _Flow) -> FinishedFlow:
        duration = max(f.last_ts - f.first_ts, 1e-6)
        sizes = f.fwd_sizes + f.bwd_sizes
        fwd_bytes, bwd_bytes = sum(f.fwd_sizes), sum(f.bwd_sizes)
        gaps = _gaps(f.times)
        features = {
            "protocol": f.protocol,
            "dst_port": f.dst_port,
            "flow_duration": duration,
            "total_fwd_packets": len(f.fwd_sizes),
            "total_bwd_packets": len(f.bwd_sizes),
            "total_fwd_bytes": fwd_bytes,
            "total_bwd_bytes": bwd_bytes,
            "fwd_pkt_len_mean": _mean(f.fwd_sizes),
            "bwd_pkt_len_mean": _mean(f.bwd_sizes),
            "pkt_len_std": _std(sizes),
            "flow_bytes_per_s": (fwd_bytes + bwd_bytes) / duration,
            "flow_pkts_per_s": len(sizes) / duration,
            "flow_iat_mean": _mean(gaps),
            "flow_iat_std": _std(gaps),
            "fwd_iat_mean": _mean(_gaps(f.fwd_times)),
            "syn_flag_count": f.flags["syn"],
            "ack_flag_count": f.flags["ack"],
            "fin_flag_count": f.flags["fin"],
            "rst_flag_count": f.flags["rst"],
            "psh_flag_count": f.flags["psh"],
            "down_up_ratio": len(f.bwd_sizes) / max(len(f.fwd_sizes), 1),
            "init_win_bytes_fwd": f.init_win_fwd,
            "src_conn_rate_10s": f.src_conn_rate_10s,
            "src_distinct_dst_ports_10s": f.src_distinct_dst_ports_10s,
        }
        features = {k: (0.0 if isinstance(v, float) and not math.isfinite(v) else v)
                    for k, v in features.items()}
        assert list(features) == NETWORK_FEATURES
        meta = {
            "src_ip": f.src_ip, "dst_ip": f.dst_ip, "src_port": f.src_port, "dst_port": f.dst_port,
            "protocol": f.protocol,
            "started_at": datetime.fromtimestamp(f.first_ts, tz=timezone.utc).isoformat(),
        }
        return FinishedFlow(features=features, meta=meta)
