"""
Maps the KDD Cup 1999 benchmark dataset (same loader as
scripts/phase0_validate_pipeline.py) onto feature_extraction.schema so
it can be mixed with mock data for training. This is an APPROXIMATION:
KDD99 predates our schema and doesn't record ports or true packet
counts, so those fields are backfilled from the closest KDD99 column
and clearly flagged below. Real captured data (once the networking
teammate's pipeline exists) won't need this adapter at all.
"""

import random

import numpy as np
from sklearn.datasets import fetch_kddcup99

from feature_extraction.schema import FeatureVector

# KDD99 attack labels don't line up with our 4 categories 1:1. This
# mapping groups them by behavioural similarity:
#   - flooding/DoS attacks        -> ddos
#   - probing/reconnaissance      -> port_scan
#   - unauthorized access/theft   -> exfiltration
# U2R privilege-escalation labels (buffer_overflow, loadmodule, perl,
# rootkit) don't resemble any of our 4 categories and are dropped rather
# than force-mapped.
LABEL_MAP = {
    "normal.": "normal",
    "back.": "ddos",
    "land.": "ddos",
    "neptune.": "ddos",
    "pod.": "ddos",
    "smurf.": "ddos",
    "teardrop.": "ddos",
    "ipsweep.": "port_scan",
    "nmap.": "port_scan",
    "portsweep.": "port_scan",
    "satan.": "port_scan",
    "ftp_write.": "exfiltration",
    "guess_passwd.": "exfiltration",
    "imap.": "exfiltration",
    "multihop.": "exfiltration",
    "phf.": "exfiltration",
    "spy.": "exfiltration",
    "warezclient.": "exfiltration",
    "warezmaster.": "exfiltration",
}

# KDD99 has no port numbers, only a "service" name. Approximate a
# destination port from well-known services; unmapped services get
# DEFAULT_PORT. Source port isn't recoverable at all, so it's randomized
# like an ephemeral client port.
SERVICE_TO_PORT = {
    "http": 80,
    "ftp": 21,
    "ftp_data": 20,
    "smtp": 25,
    "domain": 53,
    "domain_u": 53,
    "telnet": 23,
    "pop_3": 110,
    "imap4": 143,
    "ssh": 22,
}
DEFAULT_PORT = 0


def _row_to_feature_vector(row) -> FeatureVector | None:
    raw_label = row["labels"].decode() if isinstance(row["labels"], bytes) else row["labels"]
    label = LABEL_MAP.get(raw_label)
    if label is None:
        return None

    service = row["service"].decode() if isinstance(row["service"], bytes) else row["service"]
    protocol = row["protocol_type"].decode() if isinstance(row["protocol_type"], bytes) else row["protocol_type"]

    duration = float(row["duration"])
    byte_count = float(row["src_bytes"]) + float(row["dst_bytes"])
    # "count" = connections to the same host in the last 2s; used here as
    # a rough packet-rate/packet-count proxy since KDD99 has neither.
    connection_count = float(row["count"])
    # Many KDD99 rows have duration=0 (sub-second flows). Dividing by the
    # true duration there produces packet-rate outliers in the millions
    # that would poison both models' notion of "normal". Floor the
    # divisor at 10ms — an approximation, not a measured value.
    duration_floor = max(duration, 0.01)

    return FeatureVector(
        src_ip="0.0.0.0",  # not present in KDD99
        dst_ip="0.0.0.0",  # not present in KDD99
        src_port=random.randint(1024, 65535),
        dst_port=SERVICE_TO_PORT.get(service, DEFAULT_PORT),
        protocol=protocol.upper() if protocol.upper() in ("TCP", "UDP", "ICMP") else "TCP",
        byte_count=byte_count,
        duration=duration,
        packet_rate=connection_count / duration_floor,
        packet_count=int(connection_count),
        label=label,
    )


def load_kddcup99_as_feature_vectors(seed: int = 42) -> list[FeatureVector]:
    """Fetch KDD Cup 1999 (SA subset, 10%) and map every row whose label
    is in LABEL_MAP onto our schema. Rows with unmapped labels are
    dropped (see LABEL_MAP docstring)."""
    random.seed(seed)
    data = fetch_kddcup99(subset="SA", percent10=True, as_frame=True)
    df = data.frame

    rows = []
    for _, row in df.iterrows():
        fv = _row_to_feature_vector(row)
        if fv is not None:
            rows.append(fv)
    return rows
