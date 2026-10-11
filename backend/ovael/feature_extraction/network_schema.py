"""Network flow feature schema. The exact column names and order live here and nowhere else.

The features follow CICFlowMeter definitions where one exists, so a model trained on our sandbox
flows and one trained on a CICFlowMeter export use the same vocabulary. Two context features
(`src_*_10s`) are computed by the flow builder across a sliding window per source IP; without
them a single port-scan flow looks like an ordinary short TCP connection.
"""

from __future__ import annotations

NETWORK_FEATURES: list[str] = [
    "protocol",                # 6 TCP, 17 UDP, 1 ICMP
    "dst_port",
    "flow_duration",           # seconds
    "total_fwd_packets",
    "total_bwd_packets",
    "total_fwd_bytes",
    "total_bwd_bytes",
    "fwd_pkt_len_mean",
    "bwd_pkt_len_mean",
    "pkt_len_std",
    "flow_bytes_per_s",
    "flow_pkts_per_s",
    "flow_iat_mean",           # seconds between packets
    "flow_iat_std",
    "fwd_iat_mean",
    "syn_flag_count",
    "ack_flag_count",
    "fin_flag_count",
    "rst_flag_count",
    "psh_flag_count",
    "down_up_ratio",
    "init_win_bytes_fwd",
    "src_conn_rate_10s",       # flows started by this source in the last 10 s
    "src_distinct_dst_ports_10s",
]

# Flow metadata travels next to the features but is never a model input.
NETWORK_META = ["src_ip", "dst_ip", "src_port", "dst_port", "protocol", "started_at"]

NETWORK_FEATURE_DESCRIPTIONS: dict[str, str] = {
    "protocol": "IP protocol number",
    "dst_port": "Destination port",
    "flow_duration": "Flow duration",
    "total_fwd_packets": "Packets sent by the source",
    "total_bwd_packets": "Packets sent back by the destination",
    "total_fwd_bytes": "Bytes sent by the source",
    "total_bwd_bytes": "Bytes sent back",
    "fwd_pkt_len_mean": "Mean forward packet size",
    "bwd_pkt_len_mean": "Mean backward packet size",
    "pkt_len_std": "Packet size spread",
    "flow_bytes_per_s": "Byte rate",
    "flow_pkts_per_s": "Packet rate",
    "flow_iat_mean": "Mean gap between packets",
    "flow_iat_std": "Gap spread",
    "fwd_iat_mean": "Mean gap between forward packets",
    "syn_flag_count": "SYN flags",
    "ack_flag_count": "ACK flags",
    "fin_flag_count": "FIN flags",
    "rst_flag_count": "RST flags",
    "psh_flag_count": "PSH flags",
    "down_up_ratio": "Download/upload packet ratio",
    "init_win_bytes_fwd": "Initial TCP window",
    "src_conn_rate_10s": "Connections from this source in 10 s",
    "src_distinct_dst_ports_10s": "Distinct ports this source touched in 10 s",
}
