"""Flow sensor for the protected host: sniff -> 5-tuple flows -> POST /api/flows.

Runs on the host being protected, inside the lab network. Packets are read on the lab interface
only (the one whose address is in OVAEL_SANDBOX_SUBNET), so control traffic to the API and the
defense agent never becomes a flow.

Recording mode (OVAEL_RECORD_CSV set) also writes every finished flow with a label, which is how
the lab builds our own network training dataset. The lab's experiment runner writes the label of
the traffic it is currently generating to OVAEL_PHASE_FILE; flows from OVAEL_LABELLED_SOURCE_IP
during that phase get that label, everything else is labelled benign.
"""

from __future__ import annotations

import csv
import ipaddress
import logging
import os
import queue
import threading
import time
from pathlib import Path

import httpx
from scapy.all import IP, TCP, UDP, AsyncSniffer, get_if_list, get_if_addr  # type: ignore

from ovael.feature_extraction.flow_builder import FlowBuilder, Packet
from ovael.feature_extraction.network_schema import NETWORK_FEATURES

API_URL = os.environ.get("OVAEL_API_URL", "http://nginx/api/flows")
TOKEN = os.environ.get("OVAEL_SENSOR_TOKEN") or None
SANDBOX = ipaddress.ip_network(os.environ.get("OVAEL_SANDBOX_SUBNET", "172.28.0.0/16"))
LABELLED_SOURCE_IP = os.environ.get("OVAEL_LABELLED_SOURCE_IP", "")
RECORD = os.environ.get("OVAEL_RECORD_CSV")
PHASE_FILE = Path(os.environ.get("OVAEL_PHASE_FILE", "/shared/phase"))
BATCH_S = 1.0

logging.basicConfig(level=logging.INFO, format="%(asctime)s sensor: %(message)s")
log = logging.getLogger("sensor")
packets: queue.Queue = queue.Queue(maxsize=200_000)


def sandbox_iface() -> str:
    for iface in get_if_list():
        try:
            if ipaddress.ip_address(get_if_addr(iface)) in SANDBOX:
                return iface
        except ValueError:
            continue
    raise SystemExit("no interface on the sandbox network")


def on_packet(pkt) -> None:
    if IP not in pkt:
        return
    ip = pkt[IP]
    sport = dport = 0
    flags, window = "", 0
    if TCP in pkt:
        t = pkt[TCP]
        sport, dport, flags, window = t.sport, t.dport, str(t.flags), t.window
    elif UDP in pkt:
        sport, dport = pkt[UDP].sport, pkt[UDP].dport
    try:
        packets.put_nowait(Packet(float(pkt.time), ip.src, ip.dst, sport, dport, ip.proto, len(pkt), flags, window))
    except queue.Full:
        pass  # under a heavy flood we shed packets rather than fall behind


def current_phase() -> str:
    try:
        return PHASE_FILE.read_text().strip() or "idle"
    except FileNotFoundError:
        return "idle"


def main() -> None:
    iface = sandbox_iface()
    log.info("sniffing on %s, posting to %s", iface, API_URL)
    AsyncSniffer(iface=iface, prn=on_packet, store=False).start()
    builder = FlowBuilder()
    headers = {"Authorization": f"Bearer {TOKEN}"} if TOKEN else {}
    client = httpx.Client(timeout=10.0, headers=headers)
    writer = None
    if RECORD:
        new = not Path(RECORD).exists()
        fh = open(RECORD, "a", newline="")
        writer = csv.DictWriter(fh, fieldnames=[*NETWORK_FEATURES, "src_ip", "dst_ip", "label"])
        if new:
            writer.writeheader()

    while True:
        deadline = time.monotonic() + BATCH_S
        finished = []
        while time.monotonic() < deadline:
            try:
                finished += builder.add(packets.get(timeout=0.1))
            except queue.Empty:
                pass
        finished += builder.expire(time.time())
        if not finished:
            continue
        if writer:
            phase = current_phase()
            for f in finished:
                label = phase if (f.meta["src_ip"] == LABELLED_SOURCE_IP and phase not in ("idle", "")) else "benign"
                writer.writerow({**f.features, "src_ip": f.meta["src_ip"], "dst_ip": f.meta["dst_ip"], "label": label})
        for i in range(0, len(finished), 1000):
            chunk = finished[i:i + 1000]
            body = {"flows": [{"features": f.features, **{k: f.meta[k] for k in
                               ("src_ip", "dst_ip", "src_port", "dst_port", "protocol")}} for f in chunk]}
            try:
                r = client.post(API_URL, json=body)
                r.raise_for_status()
                res = r.json()
                if res.get("alerts"):
                    log.info("%d flows, %d alerts, blocked=%s", res["accepted"], res["alerts"], res["blocked_sources"])
            except Exception as exc:
                log.warning("post failed: %s", exc)


if __name__ == "__main__":
    threading.current_thread().name = "sensor"
    main()
